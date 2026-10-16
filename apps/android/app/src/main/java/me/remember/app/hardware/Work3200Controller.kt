package me.remember.app.hardware

import android.content.Context
import android.media.MediaPlayer
import android.net.Uri
import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.UUID

data class NearbyRecorder(val name: String, val product: String, val mac: String, val uuid: String, val advertisedBound: Boolean = false) {
    val key: String get() = MessageDigest.getInstance("SHA-256").digest("$mac/$uuid".toByteArray()).joinToString("") { "%02x".format(it) }
}
data class RecorderUi(
    val message: String = "开启手机蓝牙，然后准备连接录音豆。", val busy: String = "",
    val authorized: Boolean = false, val nearby: List<NearbyRecorder> = emptyList(),
    val device: NearbyRecorder? = null, val connected: Boolean = false,
    val deviceInfo: String = "", val files: List<DeviceRecording> = emptyList(), val listComplete: Boolean = false,
    val progress: String = "", val downloads: List<HardwareDownloadReceipt> = emptyList(), val playing: Boolean = false,
    val needsGrant: Boolean = false, val bound: Boolean = false,
    val recordPhase: DeviceRecordPhase = DeviceRecordPhase.IDLE, val recordingFileId: Int? = null,
    val elapsedMs: Long = 0, val recordMarks: List<RecorderMark> = emptyList(),
    val savedMarks: Map<String, List<RecorderMark>> = emptyMap(), val percent: Int? = null,
    val preparingId: String? = null, val realtimeMarked: Boolean = false
)

/** Identity-scoped session; UI composition never owns the SDK lifetime. */
class Work3200Controller(context: Context, val identity: HardwareScope,
    private val getGrant: suspend (HardwareScope, String) -> JSONObject,
    private val onPrepared: (HardwareDownloadReceipt, HardwareUploadCandidate) -> Unit = { _, _ -> },
    private val transportFactory: (HardwareEvents) -> HardwareTransport = HardwareTransportFactory::create) : AutoCloseable {
    private val app = context.applicationContext
    private val jobs = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val handler = Handler(Looper.getMainLooper())
    private val mutable = MutableStateFlow(RecorderUi())
    val ui = mutable.asStateFlow()
    private val grants = HardwareGrantStore(app, identity)
    private val journal = Work3200ImportJournal(File(app.filesDir, "work3200-imports"))
    private val session = Work3200Session()
    private var ticket: HardwareSessionTicket? = null
    private var listing: HardwareOperationTicket? = null
    private var transport: HardwareTransport? = null
    private var epoch = 0L
    private var deadline: Job? = null
    private var scanTimeout: Job? = null
    private var player: MediaPlayer? = null
    private var closed = false
    private var timeline = RecorderTimeline()
    private var lastDevice: NearbyRecorder? = null
    private var nextFile: Job? = null
    private val listAttempts = mutableMapOf<Int, Int>()
    private var realtimeFile: Int? = null
    private var deviceTransferBusy = false
    private var drainDeadline: Job? = null
    private var drainTimedOut = false
    private data class Download(val recording: DeviceRecording, val device: NearbyRecorder, val directory: File)
    private var downloading: Download? = null
    private val log = ArrayDeque<String>()
    init {
        refreshDownloads()
        jobs.launch { while (isActive) { delay(250); publishTimeline() } }
        jobs.launch { while (isActive) {
            delay(8000)
            if (mutable.value.connected && mutable.value.busy.isEmpty()) runCatching { transport?.refreshInfo() }
        } }
    }
    private fun publishTimeline() {
        mutable.value = mutable.value.copy(recordPhase = timeline.phase, recordingFileId = timeline.fileId,
            elapsedMs = timeline.elapsedMs(), recordMarks = timeline.marks)
    }

    fun notice(message: String) { mutable.value = mutable.value.copy(message = message) }
    private fun record(message: String) {
        log.addLast("${java.time.Instant.now()} $message")
        while (log.size > 150) log.removeFirst()
    }
    private fun timeout(ms: Long, message: String, connectionFatal: Boolean = true) {
        deadline?.cancel()
        deadline = jobs.launch { delay(ms); if (connectionFatal) disconnect(message) else operationFailed(message) }
    }
    private fun refreshDownloads() { jobs.launch {
        val (files, marks) = withContext(Dispatchers.IO) {
            val files = journal.downloaded(identity)
            files to files.associate { it.importId to journal.markers(it.importId, identity) }
        }
        if (!closed) mutable.value = mutable.value.copy(downloads = files, savedMarks = marks)
    } }
    fun authorizationRequest(): String = JSONObject().put("version", 1).put("server", identity.server)
        .put("user_id", identity.actorId).put("device_id", grants.deviceId).toString(2)

    fun authorize() {
        if (mutable.value.busy.isNotEmpty()) return
        mutable.value = mutable.value.copy(busy = "auth", message = "正在获取录音豆授权…", needsGrant = false)
        val current = epoch
        jobs.launch {
            try {
                val value = try { getGrant(identity, grants.deviceId) }
                    catch (e: Exception) { if (e is CancellationException) throw e; withContext(Dispatchers.IO) { grants.load() } ?: throw e }
                val credentials = HardwareGrant.parse(value, identity, grants.deviceId)
                withContext(Dispatchers.IO) { grants.save(value) }
                if (current != epoch) return@launch
                initialize(credentials)
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                if (current != epoch) return@launch
                mutable.value = mutable.value.copy(busy = "", needsGrant = true,
                    message = "尚未取得有效录音豆授权。可重试，或导出本机授权申请并导入管理员生成的授权文件。")
                record("authorization unavailable")
                RecorderConnectionService.release(app, this@Work3200Controller)
            }
        }
    }
    fun importGrant(uri: Uri) {
        if (mutable.value.busy.isNotEmpty()) return
        keepConnectedInBackground()
        val current = epoch
        mutable.value = mutable.value.copy(busy = "auth")
        jobs.launch {
            try {
                val value = withContext(Dispatchers.IO) {
                    val bytes = app.contentResolver.openInputStream(uri)!!.use { it.readBytesLimited(128 * 1024) }
                    JSONObject(bytes.toString(Charsets.UTF_8))
                }
                val credentials = HardwareGrant.parse(value, identity, grants.deviceId)
                withContext(Dispatchers.IO) { grants.save(value) }
                if (current == epoch) initialize(credentials)
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                if (current == epoch) mutable.value = mutable.value.copy(busy = "", needsGrant = true,
                    message = "授权文件无效、已过期，或不属于当前账号与手机。请重新生成。")
            }
        }
    }
    private fun initialize(credentials: Work3200Credentials) {
        stopTransport()
        val current = epoch
        ticket = session.begin(identity)
        mutable.value = mutable.value.copy(busy = "auth", message = "正在验证厂商授权…", needsGrant = false)
        try {
            transport = transportFactory(events(current))
            timeout(45_000, "厂商授权验证超时，请检查手机网络后重试。")
            transport!!.initialize(app, credentials)
        } catch (_: Exception) { disconnect("录音豆通信组件未能启动，请检查权限后重试，并导出连接记录。"); record("sdk initialization failed") }
    }
    private fun events(current: Long): HardwareEvents = object : HardwareEvents {
        private fun post(action: () -> Unit) { handler.post {
            if (current != epoch || closed) return@post
            try { action() } catch (_: Exception) { disconnect("设备数据处理未完成，请重新连接；已保存的文件仍在本机。"); record("callback rejected") }
        } }
        override fun auth(result: HardwareAuthResult) = post {
            if (!session.onAuth(ticket!!, result)) return@post
            record("auth success=${result.success} online=${result.isOnline} license=${result.licenseValid} code=${result.error?.code}")
            val ready = session.state.canUseDevice
            mutable.value = mutable.value.copy(authorized = ready)
            if (ready && mutable.value.busy == "auth") {
                deadline?.cancel()
                mutable.value = mutable.value.copy(busy = "", message = "录音豆授权成功。点击扫描附近设备。")
            } else if (!ready && result.isOnline) {
                disconnect("厂商授权未通过（${result.error?.code ?: -1}），请重新获取授权。")
            }
        }
        override fun found(productCode: String?, name: String?, mac: String?, uuid: String?) = post {
            if (mutable.value.busy != "scan" || mac.isNullOrBlank() || uuid.isNullOrBlank()) return@post
            val device = NearbyRecorder(name?.take(80).orEmpty().ifBlank { "录音豆" }, productCode.orEmpty(), mac, uuid)
            mutable.value = mutable.value.copy(nearby = (mutable.value.nearby.filterNot { it.key == device.key } + device).take(50))
        }
        override fun bindingAdvertisement(mac: String, uuid: String, bound: Boolean) = post {
            mutable.value = mutable.value.copy(nearby = mutable.value.nearby.map {
                if (it.mac == mac && it.uuid == uuid) it.copy(advertisedBound = bound) else it
            })
        }
        override fun recording(status: Int, durationMs: Int, fileId: Int) = post {
            if (!timeline.status(status, durationMs.toLong(), fileId)) return@post
            val activeFileId = timeline.fileId ?: return@post
            publishTimeline()
            record("recording status=$status file=$activeFileId reportedFile=$fileId durationMs=$durationMs")
            if (status != 1 && !deviceTransferBusy) realtimeFile = null
            if (status == 1) {
                stopPlayback()
                notice("录音豆正在采集声音，按设备按钮结束后会自动同步到手机。")
                if (realtimeFile != activeFileId && mutable.value.busy.isEmpty()) {
                    realtimeFile = activeFileId
                    val folder = File(journal.rawDirectory, "live-${UUID.randomUUID()}").apply { mkdirs() }
                    mutable.value = mutable.value.copy(realtimeMarked = false)
                    runCatching { transport?.realtime(folder) }.onFailure { realtimeFile = null; record("realtime unavailable file=$fileId") }
                }
            }
            if (status == 2) notice("录音豆已暂停，等待设备继续录音或结束。")
            if (status == 0) {
                notice("录音已结束，正在取得本段文件并同步到手机。")
                if (transferDraining()) waitForTransferDrain()
                scheduleNextFile()
            }
        }
        override fun recordingDuration(durationMs: Long) = post { timeline.duration(durationMs); publishTimeline() }
        override fun recordingSnapshot(recording: Int?, startedAt: Int) = post {
            // This timestamp is an identity hint, never an elapsed duration.
            if (recording == 1 && startedAt > 0 && timeline.phase in setOf(DeviceRecordPhase.IDLE, DeviceRecordPhase.UNKNOWN)) {
                this.recording(1, 0, startedAt)
                notice("设备正在录音，正在等待设备返回准确时长。")
            }
            if (recording == 0 && timeline.phase == DeviceRecordPhase.UNKNOWN && timeline.fileId != null) {
                this.recording(0, timeline.elapsedMs().coerceAtMost(Int.MAX_VALUE.toLong()).toInt(), timeline.fileId!!)
            }
        }
        override fun realtimeMarker(fileId: Int, sequence: Int) = post {
            if (timeline.fileId == fileId) {
                // Precise offsets come from the final marker callback. Don't infer packet indexing.
                mutable.value = mutable.value.copy(realtimeMarked = true)
                record("live marker file=$fileId sequence=$sequence")
            }
        }
        override fun connected() = post {
            val device = mutable.value.device ?: return@post
            if (mutable.value.busy != "connect" || !session.connected(ticket!!, device.key)) return@post
            deadline?.cancel()
            mutable.value = mutable.value.copy(connected = true, busy = "", message = "已连接录音豆。按设备按钮开始或结束录音，首页会显示状态。")
            record("connected device=${device.key.take(12)}")
            if (device.advertisedBound) listFiles()
        }
        override fun disconnected(systemCode: Int?) = post { disconnect("连接已断开（${systemCode ?: 0}）。已保存的录音仍在手机上，可重新连接。") }
        override fun info(battery: Int?, firmware: String?, freeKb: Int?, totalKb: Int?) = post {
            val percent = battery?.takeIf { it in 0..10 }?.times(10)?.let { "$it%" } ?: "未知"
            mutable.value = mutable.value.copy(deviceInfo = "电量 $percent · 固件 ${firmware ?: "未知"}\n剩余 ${freeKb ?: "?"} / ${totalKb ?: "?"} KB")
            record("device-info battery=$battery firmware=${firmware?.take(30)} freeKB=$freeKb totalKB=$totalKb")
        }
        override fun binding(confirmed: Boolean) = post {
            if (mutable.value.busy != "bind") return@post
            if (confirmed) { deadline?.cancel(); mutable.value = mutable.value.copy(busy = "", bound = true); record("binding confirmed") }
            notice(if (confirmed) "设备已确认绑定，可以读取录音列表。" else "请把录音豆放入充电盒，在闪灯时按充电盒按钮，等待设备确认。")
            if (confirmed) listFiles()
        }
        override fun files(files: List<DeviceRecording>, complete: Boolean) = post {
            val op = listing ?: return@post
            val device = mutable.value.device ?: return@post
            if (!session.onFiles(op, device.key, files, complete)) return@post
            mutable.value = mutable.value.copy(files = session.state.files.sortedByDescending { it.fileId }, listComplete = complete)
            if (complete) {
                deadline?.cancel(); listing = null
                mutable.value = mutable.value.copy(busy = "", bound = true, message = "设备已就绪，已读取 ${mutable.value.files.size} 段录音。")
                record("file-list complete count=${mutable.value.files.size}")
                downloadPendingFile()
            }
        }
        override fun transfer(fileId: Int, sdkStatus: Int) = post {
            if (sdkStatus == 1 && realtimeFile == fileId && downloading == null) deviceTransferBusy = true
            if (sdkStatus == 3 && realtimeFile == fileId) {
                realtimeFile = null
                deviceTransferBusy = false
                drainDeadline?.cancel(); drainTimedOut = false
                record("live transfer drained file=$fileId")
                scheduleNextFile()
            }
            if (downloading?.recording?.fileId != fileId) return@post
            record("transfer file=$fileId status=$sdkStatus")
            if (sdkStatus == 2 || sdkStatus == 4) notice("设备传输已进入文件处理阶段，正在等待本机文件校验。")
        }
        override fun transferIdle(idle: Boolean) = post {
            deviceTransferBusy = !idle
            if (idle && timeline.phase !in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED)) {
                realtimeFile = null; drainDeadline?.cancel(); drainTimedOut = false
                if (mutable.value.busy.isEmpty()) scheduleNextFile()
            }
        }
        override fun transferRejected(fileId: Int) = post {
            if (downloading?.recording?.fileId != fileId) return@post
            operationFailed("设备正在完成上一段传输，等待设备就绪后继续同步。")
            deviceTransferBusy = true
            waitForTransferDrain(); scheduleNextFile()
            record("download deferred file=$fileId")
        }
        override fun progress(fileId: Int, receivedBytes: Int, totalBytes: Int, sequenceNumber: Int, marked: Boolean) = post {
            if (downloading?.recording?.fileId != fileId || mutable.value.busy != "download") return@post
            val percent = transferPercent(receivedBytes.toLong(), totalBytes.toLong())
            mutable.value = mutable.value.copy(percent = percent, progress = "同步到手机 ${percent?.let { "$it% · " }.orEmpty()}$receivedBytes / $totalBytes 字节")
        }
        override fun receivedSdkFile(fileId: Int, rawFile: File) = post {
            val active = downloading ?: return@post
            if (active.recording.fileId != fileId || mutable.value.busy != "download") return@post
            require(rawFile.canonicalFile.toPath().startsWith(active.directory.canonicalFile.toPath()))
            deadline?.cancel()
            mutable.value = mutable.value.copy(busy = "verify", message = "正在校验已接收文件…")
            jobs.launch {
                try {
                    val receipt = withContext(Dispatchers.IO) {
                        val saved = journal.recordDownloaded(identity, active.device.key, active.recording, rawFile)
                        journal.rawReceipt(saved.importId, identity)
                    }
                    if (current != epoch) return@launch
                    downloading = null
                    timeline.completed(fileId)
                    mutable.value = mutable.value.copy(busy = "", percent = null, progress = "", message = "录音已保存到手机，正在准备试听和转写。")
                    record("download saved file=$fileId bytes=${receipt.bytes} sha256=${receipt.sha256}")
                    refreshDownloads()
                    prepareAudio(receipt)
                } catch (e: Exception) {
                    if (e is CancellationException) throw e
                    if (current == epoch) operationFailed("文件校验未通过，不能计为下载成功。请重试同步本段录音。")
                }
            }
        }
        override fun markers(fileId: Int, offsetsMs: IntArray) = post {
            storeMarks(fileId, offsetsMs.filter { it >= 0 }.map { RecorderMark(it.toLong(), "device") })
        }
        override fun error(operation: String, code: Int) = post {
            record("error operation=$operation code=$code")
            when (operation) {
                "binding" -> disconnect(when (code) {
                    3 -> "等待充电盒按键确认超时。重新连接后点绑定，将录音豆放入盒内，闪灯时按充电盒按钮。"
                    2 -> "设备未能确认绑定，请重新连接并完成充电盒上的按键确认。"
                    else -> "绑定请求未送达（$code），请重新连接后重试。"
                })
                "sync_time_binding", "device_info" -> record("nonfatal info error=$code")
                "file_list" -> operationFailed("读取设备录音列表未完成（$code）。连接保留，可点刷新或重试同步。")
                "file_transfer", "received_file_path" -> operationFailed("本段同步未完成（$code）。原录音仍在设备上，可重试同步。")
                else -> disconnect("设备操作未完成（$operation/$code）。请重新连接后重试。")
            }
        }
    }
    fun scan() {
        if (!mutable.value.authorized || mutable.value.busy.isNotEmpty() || mutable.value.connected) return
        runCatching {
            mutable.value = mutable.value.copy(busy = "scan", nearby = emptyList(), message = "正在扫描附近录音豆（20 秒）…")
            transport!!.scan()
            scanTimeout = jobs.launch { delay(20_000); stopScan() }
        }.onFailure { disconnect("扫描未能启动，请检查蓝牙和附近设备权限。") }
    }
    fun stopScan() {
        scanTimeout?.cancel()
        runCatching { transport?.stopScan() }
        if (mutable.value.busy == "scan") mutable.value = mutable.value.copy(busy = "", message = if (mutable.value.nearby.isEmpty()) "未发现录音豆。请靠近设备、确认有电并处于可发现状态后重试。" else "扫描结束，请选择自己的录音豆。")
    }
    fun connect(device: NearbyRecorder) {
        if (mutable.value.busy !in setOf("", "scan") || !mutable.value.authorized) return
        stopScan()
        if (lastDevice?.key != device.key) { timeline = RecorderTimeline(); listAttempts.clear() }
        lastDevice = device
        mutable.value = mutable.value.copy(busy = "connect", device = device, bound = false, deviceInfo = "", realtimeMarked = false, message = "正在连接 ${device.name}…")
        timeout(45_000, "连接超时。请检查录音豆是否正被其他 App 占用，再重新连接。")
        runCatching { transport!!.connect(device.mac, device.uuid) }.onFailure { disconnect("无法建立设备连接，请重新准备连接。") }
    }
    fun bind() {
        if (!mutable.value.connected || mutable.value.busy.isNotEmpty()) return
        mutable.value = mutable.value.copy(busy = "bind", message = "正在请求绑定，请把录音豆放入充电盒，闪灯时按盒上按钮。")
        timeout(90_000, "绑定确认超时，请重新连接后再按设备提示操作。")
        runCatching { transport!!.bind() }.onFailure { disconnect("绑定请求未完成。") }
    }
    fun listFiles() {
        if (!mutable.value.connected || mutable.value.busy.isNotEmpty()) return
        runCatching {
            listing = session.beginListing(ticket!!)
            mutable.value = mutable.value.copy(busy = "list", files = emptyList(), listComplete = false, message = "正在读取设备录音列表…")
            timeout(45_000, "读取录音列表超时，连接保留，可重试。", connectionFatal = false)
            transport!!.listFiles()
        }.onFailure { operationFailed("暂时无法读取录音列表，请重试。") }
    }
    fun download(file: DeviceRecording) {
        val device = mutable.value.device ?: return
        if (!mutable.value.connected || mutable.value.busy.isNotEmpty() || !mutable.value.listComplete || file.code != 0 || file.sizeBytes <= 0 ||
            timeline.phase in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED)) return
        if (transferDraining()) { waitForTransferDrain(); return }
        runCatching {
            val directory = File(journal.rawDirectory, UUID.randomUUID().toString()).apply { check(mkdirs()) }
            downloading = Download(file, device, directory)
            mutable.value = mutable.value.copy(busy = "download", percent = 0, progress = "同步到手机 0%", message = "正在同步录音到手机，可以切换 App 内页面。")
            record("download begin file=${file.fileId} expected=${file.sizeBytes}")
            timeout(10 * 60_000, "同步超时。未完成的文件不会标为已下载，请重试同步。", connectionFatal = false)
            transport!!.transfer(file, directory)
        }.onFailure { operationFailed("同步未能开始，请重试。") }
    }
    private fun operationFailed(message: String) {
        deadline?.cancel(); nextFile?.cancel(); listing = null; downloading = null
        mutable.value = mutable.value.copy(busy = "", percent = null, progress = "", preparingId = null, message = message)
    }
    private fun scheduleNextFile(delayMs: Long = 1000) {
        nextFile?.cancel()
        if (timeline.pendingFiles.isEmpty() || !mutable.value.connected) return
        nextFile = jobs.launch {
            delay(delayMs)
            if (timeline.phase in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED)) return@launch
            if (transferDraining()) { if (!drainTimedOut) scheduleNextFile(); return@launch }
            if (mutable.value.busy.isEmpty()) listFiles() else scheduleNextFile()
        }
    }
    // A realtime request can be cancelled by the SDK before it starts. Only an
    // observed active transfer blocks offline sync; request return is not proof.
    private fun transferDraining() = deviceTransferBusy
    private fun waitForTransferDrain() {
        notice("录音已结束，等待设备完成传输后自动同步到手机…")
        if (drainDeadline?.isActive == true) return
        drainTimedOut = false
        drainDeadline = jobs.launch {
            delay(60_000)
            if (transferDraining()) {
                drainTimedOut = true; nextFile?.cancel()
                notice("设备仍未结束传输。原录音保留在设备上，请断开后重新连接，再刷新录音列表同步。")
            }
        }
    }
    private fun downloadPendingFile() {
        val id = timeline.pendingFiles.firstOrNull() ?: return
        val device = mutable.value.device ?: return
        if (mutable.value.downloads.any { it.fileId == id && it.deviceKey == device.key }) {
            timeline.completed(id); scheduleNextFile(); return
        }
        val file = mutable.value.files.firstOrNull { it.fileId == id && it.code == 0 && it.sizeBytes > 0 }
        if (file != null) { listAttempts.remove(id); download(file); return }
        val attempts = (listAttempts[id] ?: 0) + 1
        listAttempts[id] = attempts
        notice(if (attempts < 8) "录音已结束，等待设备保存本段文件…" else "设备尚未提供本段文件。可稍后点“重试同步”，不会导入其他录音。")
        if (attempts < 8) scheduleNextFile(2000)
    }
    fun retrySync() { listAttempts.clear(); if (timeline.pendingFiles.isEmpty()) listFiles() else scheduleNextFile(0) }
    private fun storeMarks(fileId: Int, marks: List<RecorderMark>) {
        val device = mutable.value.device ?: return
        if (fileId <= 0 || marks.isEmpty()) return
        if (timeline.fileId == fileId) { marks.forEach { timeline.mark(it.offsetMs, it.origin) }; publishTimeline() }
        jobs.launch {
            try { withContext(Dispatchers.IO) { journal.saveMarkers(identity, device.key, fileId, marks) }; refreshDownloads() }
            catch (e: Exception) { if (e is CancellationException) throw e; notice("重点未能保存，请重试；原始录音不受影响。") }
        }
    }
    fun addMark() {
        val id = timeline.fileId ?: return
        if (timeline.phase !in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED)) return
        storeMarks(id, listOf(RecorderMark(timeline.elapsedMs(), "phone")))
    }
    fun keepConnectedInBackground() {
        try { RecorderConnectionService.start(app, this) }
        catch (_: Exception) { notice("后台连接服务暂未启动，请保持 App 在前台完成同步。") }
    }
    fun stopPlayback() { player?.release(); player = null; mutable.value = mutable.value.copy(playing = false) }
    fun prepareAudio(receipt: HardwareDownloadReceipt, playAfter: Boolean = false, seekMs: Long = 0) {
        if (mutable.value.busy.isNotEmpty()) return
        stopPlayback()
        mutable.value = mutable.value.copy(busy = "decode", preparingId = receipt.importId, percent = null, message = "正在准备可试听、可转写的录音…")
        val current = epoch
        jobs.launch {
            try {
                val candidate = withContext(Dispatchers.IO) {
                    val checked = journal.rawReceipt(receipt.importId, identity)
                    val output = File(journal.preparedDirectory, "${receipt.importId}.wav")
                    val decoded = DeviceOpusDecoder.decode(checked.rawFile, output) { received, total ->
                        handler.post { if (current == epoch && !closed && mutable.value.busy == "decode")
                            mutable.value = mutable.value.copy(percent = transferPercent(received, total), progress = "转换录音 ${transferPercent(received, total) ?: 0}%") }
                    }
                    journal.prepare(receipt.importId, identity, decoded, "android-mediacodec-fixed160-v1")
                    journal.uploadCandidate(receipt.importId, identity)
                }
                if (current != epoch) return@launch
                onPrepared(receipt, candidate)
                if (playAfter) player = MediaPlayer().apply {
                    setDataSource(candidate.file.path)
                    setOnCompletionListener { stopPlayback(); notice("播放结束，请确认是否能清楚听到这段录音。") }
                    setOnErrorListener { _, _, _ -> stopPlayback(); notice("手机播放器未能播放此文件。原始录音已保留。请导出原文件核对格式。"); true }
                    prepare(); seekTo(seekMs.coerceIn(0, candidate.audio.durationMs).toInt()); start()
                }
                mutable.value = mutable.value.copy(busy = "", percent = null, progress = "", preparingId = null, playing = playAfter,
                    message = if (playAfter) "正在试听录音豆的声音。" else "录音已保存在手机，可试听或确认上传转写。")
                record("audio ready file=${receipt.fileId} play=$playAfter")
                scheduleNextFile()
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                if (current == epoch) { operationFailed("原始录音已保存，但转换未完成。可重试准备或导出原文件与连接记录。尚未上传。"); record("decode failed file=${receipt.fileId}") }
            }
        }
    }
    fun play(receipt: HardwareDownloadReceipt, seekMs: Long = 0) = prepareAudio(receipt, true, seekMs)
    fun export(uri: Uri, receipt: HardwareDownloadReceipt? = null, request: Boolean = false) {
        jobs.launch {
            try {
                val report = if (request) authorizationRequest() else JSONObject().put("app_version", me.remember.app.BuildConfig.VERSION_NAME)
                    .put("events", JSONArray(log.toList())).put("download_count", mutable.value.downloads.size).toString(2)
                withContext(Dispatchers.IO) {
                    app.contentResolver.openOutputStream(uri, "wt")!!.use { out ->
                        if (receipt != null) journal.rawReceipt(receipt.importId, identity).rawFile.inputStream().use { it.copyTo(out) }
                        else out.write(report.toByteArray(Charsets.UTF_8))
                    }
                }
                notice("文件已导出到你选择的位置。")
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                notice("文件导出未完成，请选择可写入的位置重试。")
            }
        }
    }
    private fun stopTransport() {
        ++epoch; deadline?.cancel(); scanTimeout?.cancel(); nextFile?.cancel(); realtimeFile = null
        drainDeadline?.cancel(); drainTimedOut = false; deviceTransferBusy = false
        runCatching { transport?.close() }; transport = null
        session.close(); ticket = null; listing = null; downloading = null
    }
    fun disconnect(message: String = "连接已关闭，已下载的文件保留在本机。") {
        stopPlayback()
        stopTransport()
        timeline.disconnected(); publishTimeline()
        RecorderConnectionService.release(app, this)
        mutable.value = mutable.value.copy(busy = "", authorized = false, connected = false, device = null,
            bound = false, nearby = emptyList(), deviceInfo = "", files = emptyList(), listComplete = false, progress = "", percent = null,
            preparingId = null, message = message)
        record("session closed")
        refreshDownloads()
    }
    override fun close() { closed = true; stopPlayback(); stopTransport(); RecorderConnectionService.release(app, this); jobs.cancel() }
}

private fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    val buffer = ByteArray(4096)
    while (true) { val count = read(buffer); if (count < 0) break; require(out.size() + count <= limit); out.write(buffer, 0, count) }
    return out.toByteArray()
}

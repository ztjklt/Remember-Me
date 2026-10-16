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

data class NearbyRecorder(val name: String, val product: String, val mac: String, val uuid: String) {
    val key: String get() = MessageDigest.getInstance("SHA-256").digest("$mac/$uuid".toByteArray()).joinToString("") { "%02x".format(it) }
}
data class RecorderUi(
    val message: String = "开启手机蓝牙，然后准备连接录音豆。", val busy: String = "",
    val authorized: Boolean = false, val nearby: List<NearbyRecorder> = emptyList(),
    val device: NearbyRecorder? = null, val connected: Boolean = false,
    val deviceInfo: String = "", val files: List<DeviceRecording> = emptyList(), val listComplete: Boolean = false,
    val progress: String = "", val downloads: List<HardwareDownloadReceipt> = emptyList(), val playing: Boolean = false,
    val needsGrant: Boolean = false
)

/** Screen-scoped foreground session. It owns the SDK and invalidates queued callbacks on close. */
class Work3200Controller(context: Context, val identity: HardwareScope,
    private val getGrant: suspend (HardwareScope, String) -> JSONObject) : AutoCloseable {
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
    private data class Download(val recording: DeviceRecording, val device: NearbyRecorder, val directory: File)
    private var downloading: Download? = null
    private val log = ArrayDeque<String>()
    init { refreshDownloads() }

    fun notice(message: String) { mutable.value = mutable.value.copy(message = message) }
    private fun record(message: String) {
        log.addLast("${java.time.Instant.now()} $message")
        while (log.size > 150) log.removeFirst()
    }
    private fun timeout(ms: Long, message: String) {
        deadline?.cancel()
        deadline = jobs.launch { delay(ms); disconnect(message) }
    }
    private fun refreshDownloads() { jobs.launch {
        val files = withContext(Dispatchers.IO) { journal.downloaded(identity) }
        mutable.value = mutable.value.copy(downloads = files)
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
            }
        }
    }
    fun importGrant(uri: Uri) {
        if (mutable.value.busy.isNotEmpty()) return
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
            transport = HardwareTransportFactory.create(events(current))
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
        override fun connected() = post {
            val device = mutable.value.device ?: return@post
            if (mutable.value.busy != "connect" || !session.connected(ticket!!, device.key)) return@post
            deadline?.cancel()
            mutable.value = mutable.value.copy(connected = true, busy = "", message = "已建立设备连接。首次使用请完成绑定，再读取录音列表。")
            record("connected device=${device.key.take(12)}")
        }
        override fun disconnected(systemCode: Int?) = post { disconnect("连接已断开（${systemCode ?: 0}）。已保存的录音仍在手机上，可重新连接。") }
        override fun info(battery: Int?, firmware: String?, freeKb: Int?, totalKb: Int?) = post {
            val percent = battery?.takeIf { it in 0..10 }?.times(10)?.let { "$it%" } ?: "未知"
            mutable.value = mutable.value.copy(deviceInfo = "电量 $percent · 固件 ${firmware ?: "未知"}\n剩余 ${freeKb ?: "?"} / ${totalKb ?: "?"} KB")
            record("device-info battery=$battery firmware=${firmware?.take(30)} freeKB=$freeKb totalKB=$totalKb")
        }
        override fun binding(confirmed: Boolean) = post {
            if (mutable.value.busy != "bind") return@post
            if (confirmed) { deadline?.cancel(); mutable.value = mutable.value.copy(busy = ""); record("binding confirmed") }
            notice(if (confirmed) "设备已确认绑定，可以读取录音列表。" else "请把录音豆放入充电盒，在闪灯时按充电盒按钮，等待设备确认。")
        }
        override fun files(files: List<DeviceRecording>, complete: Boolean) = post {
            val op = listing ?: return@post
            val device = mutable.value.device ?: return@post
            if (!session.onFiles(op, device.key, files, complete)) return@post
            mutable.value = mutable.value.copy(files = session.state.files.sortedByDescending { it.fileId }, listComplete = complete)
            if (complete) { deadline?.cancel(); listing = null; mutable.value = mutable.value.copy(busy = "", message = "已读取 ${mutable.value.files.size} 段录音。选择一段下载到手机。"); record("file-list complete count=${mutable.value.files.size}") }
        }
        override fun transfer(fileId: Int, sdkStatus: Int) = post {
            if (downloading?.recording?.fileId != fileId) return@post
            record("transfer file=$fileId status=$sdkStatus")
            if (sdkStatus == 2 || sdkStatus == 4) notice("设备传输已进入文件处理阶段，正在等待本机文件校验。")
        }
        override fun progress(fileId: Int, receivedBytes: Int, totalBytes: Int, sequenceNumber: Int, marked: Boolean) = post {
            if (downloading?.recording?.fileId != fileId || mutable.value.busy != "download") return@post
            mutable.value = mutable.value.copy(progress = "$receivedBytes / $totalBytes 字节")
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
                    mutable.value = mutable.value.copy(busy = "", progress = "", message = "录音已保存到手机：${receipt.bytes} 字节，SHA-256 校验完成。可试听或导出原始文件。")
                    record("download saved file=$fileId bytes=${receipt.bytes} sha256=${receipt.sha256}")
                    refreshDownloads()
                } catch (e: Exception) {
                    if (e is CancellationException) throw e
                    if (current == epoch) disconnect("文件校验未通过，不能计为下载成功。请重新连接后再试。")
                }
            }
        }
        override fun markers(fileId: Int, offsetsMs: IntArray) { }
        override fun error(operation: String, code: Int) = post {
            record("error operation=$operation code=$code")
            if (operation in setOf("sync_time_binding", "device_info")) notice("设备连接保留，但读取信息未完成（$operation/$code）。")
            else disconnect("设备操作未完成（$operation/$code）。请重新连接后重试。")
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
        mutable.value = mutable.value.copy(busy = "connect", device = device, deviceInfo = "", message = "正在连接 ${device.name}…")
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
            timeout(45_000, "读取录音列表超时，请重新连接后重试。")
            transport!!.listFiles()
        }.onFailure { disconnect("暂时无法读取录音列表，请重新连接。") }
    }
    fun download(file: DeviceRecording) {
        val device = mutable.value.device ?: return
        if (!mutable.value.connected || mutable.value.busy.isNotEmpty() || !mutable.value.listComplete || file.code != 0 || file.sizeBytes <= 0) return
        runCatching {
            val directory = File(journal.rawDirectory, UUID.randomUUID().toString()).apply { check(mkdirs()) }
            downloading = Download(file, device, directory)
            mutable.value = mutable.value.copy(busy = "download", progress = "", message = "正在下载录音。请保持此页面和手机蓝牙开启。")
            record("download begin file=${file.fileId} expected=${file.sizeBytes}")
            timeout(10 * 60_000, "录音下载超时。未完成的文件不会标为已下载，请重新连接后重试。")
            transport!!.transfer(file, directory)
        }.onFailure { disconnect("下载未能开始，请重新连接后重试。") }
    }
    fun stopPlayback() { player?.release(); player = null; mutable.value = mutable.value.copy(playing = false) }
    fun play(receipt: HardwareDownloadReceipt) {
        if (mutable.value.busy.isNotEmpty()) return
        stopPlayback()
        mutable.value = mutable.value.copy(busy = "decode", message = "正在把设备音频转换为可试听文件…")
        val current = epoch
        jobs.launch {
            try {
                val audio = withContext(Dispatchers.IO) {
                    val checked = journal.rawReceipt(receipt.importId, identity)
                    val output = File(journal.preparedDirectory, "${receipt.importId}.wav")
                    val decoded = DeviceOpusDecoder.decode(checked.rawFile, output)
                    journal.prepare(receipt.importId, identity, decoded, "android-mediacodec-fixed160-v1")
                    decoded
                }
                if (current != epoch) return@launch
                player = MediaPlayer().apply {
                    setDataSource(audio.path)
                    setOnCompletionListener { stopPlayback(); notice("播放结束，请确认是否能清楚听到这段录音。") }
                    setOnErrorListener { _, _, _ -> stopPlayback(); notice("手机播放器未能播放此文件。原始录音已保留。请导出原文件核对格式。"); true }
                    prepare(); start()
                }
                mutable.value = mutable.value.copy(busy = "", playing = true, message = "正在试听下载的录音，声音由手机播放。")
                record("playback started file=${receipt.fileId}")
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                if (current == epoch) { mutable.value = mutable.value.copy(busy = ""); notice("文件已保存在手机，但当前格式未能解码。请导出原始文件核对；不会把它当作可上传的 WAV。"); record("decode failed file=${receipt.fileId}") }
            }
        }
    }
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
        ++epoch; deadline?.cancel(); scanTimeout?.cancel()
        runCatching { transport?.close() }; transport = null
        session.close(); ticket = null; listing = null; downloading = null
    }
    fun disconnect(message: String = "连接已关闭，已下载的文件保留在本机。") {
        stopPlayback()
        stopTransport()
        mutable.value = mutable.value.copy(busy = "", authorized = false, connected = false, device = null,
            nearby = emptyList(), deviceInfo = "", files = emptyList(), listComplete = false, progress = "", message = message)
        record("session closed")
        refreshDownloads()
    }
    override fun close() { closed = true; stopPlayback(); stopTransport(); jobs.cancel() }
}

private fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    val buffer = ByteArray(4096)
    while (true) { val count = read(buffer); if (count < 0) break; require(out.size() + count <= limit); out.write(buffer, 0, count) }
    return out.toByteArray()
}

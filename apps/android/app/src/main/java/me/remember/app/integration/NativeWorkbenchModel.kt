package me.remember.app.integration

import android.content.Context
import android.media.MediaPlayer
import android.util.AtomicFile
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.data.repository.AudioRecording
import me.remember.app.data.repository.RecordingMetadata
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import me.remember.app.hardware.*

data class NativeState(
    val actor: String = "", val actorName: String = "", val spaces: List<JSONObject> = emptyList(),
    val space: JSONObject? = null, val spaceChoiceRequired: Boolean = false, val stories: List<JSONObject> = emptyList(), val grants: List<JSONObject> = emptyList(),
    val revisions: List<JSONObject> = emptyList(), val requests: List<JSONObject> = emptyList(),
    val candidates: List<JSONObject> = emptyList(), val candidateJobs: List<JSONObject> = emptyList(),
    val profileUpdates: List<JSONObject> = emptyList(),
    val asrCapabilities: JSONObject? = null,
    val stepVoiceAvailable: Boolean = false,
    val fastVoiceAvailable: Boolean = false,
    val serviceInfo: ServiceInfo = ServiceInfo(),
    val connectionCheck: ConnectionCheck = ConnectionCheck(),
    val invitations: List<JSONObject> = emptyList(), val recipients: List<JSONObject> = emptyList(),
    val sharePreview: JSONObject? = null, val shareSelection: ShareSelection? = null,
    val issuedInvitation: JSONObject? = null,
    val portrait: JSONObject = JSONObject(),
    val companion: JSONObject = JSONObject(), val voiceProfile: JSONObject = JSONObject(), val voiceGrants: List<JSONObject> = emptyList(),
    val contributionOriginal: JSONObject? = null,
    val companionAudio: CompanionAudioDraft? = null, val companionRecording: String = "",
    val calibrations: List<JSONObject> = emptyList(), val calibrationId: String = "",
    val narrative: JSONObject = JSONObject(), val narrativeJobs: List<JSONObject> = emptyList(),
    val vocabulary: String = "", val reviewSupplement: String = "",
    val answer: JSONObject? = null, val search: List<JSONObject> = emptyList(), val searchQuery:String = "",
    val reviewEpisode: String? = null, val reviewText: String = "", val local: List<LocalCapture> = emptyList(),
    val reviewInitialText: String = "", val reviewWarnings: List<String> = emptyList(), val reviewParagraphPreview: String? = null,
    val reviewMachineText: String = "", val reviewCorrection: JSONObject? = null,
    val reviewHighlights: JSONObject? = null,
    val drafts: Map<String, CaptureDraft> = emptyMap(), val draftFocus: String = "",
    val captureErrors: Map<String, String> = emptyMap(), val savingEpisode: String = "",
    val draftSaveError: String? = null,
    val busy: Boolean = false, val error: String? = null, val notice: String = "", val recording: Boolean = false, val paused: Boolean = false,
    val operation: OperationFeedback = OperationFeedback(),
    val savedCaptureId: String = "",
    val captureFocusRequest: String = "",
    val elapsed: Long = 0, val player: SourcePlayback = SourcePlayback(), val dailyReminder: Boolean = false
    ,val uploadKey: String = "", val uploadPercent: Int? = null
) {
    val owner get() = space?.text("role") == "owner"
    val subject get() = space?.text("subject_id").orEmpty()
}
data class SourcePlayback(val episode: String = "", val playing: Boolean = false, val preparing: Boolean = false,
    val position: Long = 0, val duration: Long = 0)
internal fun sourcePlaybackLabel(player: SourcePlayback): String = when {
    player.episode.startsWith("answer:") -> "AI 分身回答"
    player.episode.startsWith("companion:") -> "亲友声音"
    else -> "完整原音"
}

internal fun NativeState.forSpaceFallback(spaces: List<JSONObject>, selected: JSONObject?) =
    NativeState(actor = actor, actorName = actorName, spaces = spaces, space = selected,
        spaceChoiceRequired = selected == null && spaces.size > 1, busy = busy, notice = "可访问空间已更新。")

/** Account sessions use Keystore; local originals are scoped to the authenticated identity. */
class NativeWorkbenchModel(context: Context, val audio: AndroidAudioCaptureService) : ViewModel() {
    private val gate = SessionGate()
    private val appContext=context.applicationContext
    private val callState=MutableStateFlow<VoiceCallEngine?>(null)
    val voiceCall=callState.asStateFlow()
    private val playbackGate = SourcePlaybackGate(gate)
    private val voiceStartGate = SourcePlaybackGate(gate)
    private val client = BackendClient(gate)
    private val reminders = LocalDailyReminder(context)
    private val savedSession = SavedSession(context)
    private val spacePreferences = context.getSharedPreferences("remember-spaces", Context.MODE_PRIVATE)
    private var session: BackendSession? = null
    private val state = MutableStateFlow(NativeState())
    val ui = state.asStateFlow()
    private var deviceController: Work3200Controller? = null
    fun recorder(): Work3200Controller {
        val scope = hardwareScope()
        if (deviceController?.identity != scope) {
            deviceController?.close()
            deviceController = Work3200Controller(appContext, scope, ::hardwareGrant, onPrepared = { receipt, candidate ->
                if (runCatching { hardwareScope() }.getOrNull() == scope) acceptRecorderAudio(receipt, candidate)
            })
        }
        return checkNotNull(deviceController)
    }
    private fun closeRecorder() { deviceController?.close(); deviceController = null }
    fun preferredCaptureSource(): String = spacePreferences.getString("capture-source:${state.value.actor}:${state.value.subject}", "recorder") ?: "recorder"
    fun selectCaptureSource(value: String) {
        require(value in setOf("recorder", "phone"))
        spacePreferences.edit().putString("capture-source:${state.value.actor}:${state.value.subject}", value).apply()
    }
    internal fun acceptRecorderAudio(receipt: HardwareDownloadReceipt, candidate: HardwareUploadCandidate) {
        val s = session ?: return
        val existing = state.value.local.firstOrNull { it.key == candidate.idempotencyKey }
        val recording = AudioRecording(audioPath = candidate.file.path, durationMillis = candidate.audio.durationMs,
            mimeType = candidate.audio.mimeType, byteSize = candidate.audio.byteSize, sampleRate = candidate.audio.sampleRate,
            channelCount = candidate.audio.channels, createdAt = java.time.Instant.ofEpochSecond(receipt.fileId.toLong()).toString(), title = "录音豆录音")
        viewModelScope.launch {
            try {
                saveCapture(s, existing ?: LocalCapture(recording, candidate.idempotencyKey, episode = candidate.episodeId.orEmpty(),
                    linked = candidate.episodeId != null, source = "WORK_3200", hardwareImportId = receipt.importId, autoProcess = true))
                if(existing==null && gate.accepts(s)) state.value=state.value.copy(captureFocusRequest="received:${candidate.idempotencyKey}")
                pumpCaptures()
            } catch(e: Exception) { if(e is CancellationException) throw e; if(gate.accepts(s)) report("录音已在设备导入记录中保存，加入转写队列失败，请重新打开 App。") }
        }
    }
    fun hardwareScope(): me.remember.app.hardware.HardwareScope {
        val current = checkNotNull(session) { "请先登录。" }
        check(state.value.owner) { "请进入本人空间连接录音豆。" }
        return me.remember.app.hardware.HardwareScope(current.server, state.value.actor, state.value.subject)
    }
    suspend fun hardwareGrant(scope: me.remember.app.hardware.HardwareScope, deviceId: String): JSONObject {
        val current = checkNotNull(session)
        check(hardwareScope() == scope)
        val result = withContext(Dispatchers.IO) {
            client.json(current, "/api/v1/hardware/work3200/credentials", "POST", JSONObject().put("device_id", deviceId))
        }
        gate.requireCurrent(current)
        check(hardwareScope() == scope)
        return result
    }
    private val companionFiles = File(context.filesDir, "companion-audio").apply { mkdirs() }
    private val companionLedger = AtomicFile(File(context.filesDir,"companion-drafts.json"))
    private val creationKeys = mutableMapOf<String, String>()
    private val ledger = AtomicFile(File(context.filesDir, "native-captures.json"))
    private val sources = File(context.cacheDir, "native-source-audio").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
    private var player: MediaPlayer? = null
    private var playerJob: Job? = null
    private var recordTarget: RevisionTarget? = null
    private var activeCapture: LocalCapture? = null
    private var ticker: Job? = null
    private var foreground = true
    private var polling: Job? = null
    private var serviceInfoJob: Job? = null
    private var operationSequence = 0L
    private val captureLedgerLock = Mutex()
    private val draftLock = Mutex()
    private val draftStore = CaptureDraftStore(File(context.filesDir, "capture-drafts"))
    private var captureJob: Job? = null
    private var feedJob: Job? = null
    private val captureAttempts = mutableMapOf<String, Int>()
    private val captureRetryAt = mutableMapOf<String, Long>()
    private var loadedDraftScope = ""
    private fun hasPendingCaptureWork() = state.value.local.any { it.needsAutomaticUpload() } ||
        state.value.stories.any { (!it.optBoolean("waiting_for_review") && it.text("status") !in setOf("ready", "failed")) ||
            it.optJSONObject("cumulative_analysis")?.text("status") in setOf("queued","running") }

    /** Durable intent is in LocalCapture. A single uploader prevents duplicate
     * requests; its HTTP idempotency key also survives a lost response/restart. */
    private fun pumpCaptures() {
        val s = session ?: return
        if(captureJob?.isActive == true || !state.value.owner || state.value.recording || state.value.asrCapabilities == null) return
        captureJob = viewModelScope.launch {
            while(gate.accepts(s) && state.value.owner && !state.value.recording) {
                val next = state.value.local.asReversed().firstOrNull { it.needsAutomaticUpload() &&
                    (captureAttempts[it.key] ?: 0) < 3 && (captureRetryAt[it.key] ?: 0) <= android.os.SystemClock.elapsedRealtime() } ?: break
                try {
                    state.value = state.value.copy(captureErrors = state.value.captureErrors - next.key)
                    uploadCapture(s, next)
                    captureAttempts.remove(next.key); captureRetryAt.remove(next.key)
                } catch(e: Exception) {
                    if(e is CancellationException) throw e
                    if(!gate.accepts(s)) break
                    val attempt = (captureAttempts[next.key] ?: 0) + 1
                    val permanent = if(e is BackendHttpException) e.status in 400..499 && e.status != 429 else e !is java.io.IOException
                    captureAttempts[next.key] = if(permanent) 3 else attempt
                    captureRetryAt[next.key] = android.os.SystemClock.elapsedRealtime() + attempt * 15_000L
                    state.value = state.value.copy(captureErrors = state.value.captureErrors +
                        (next.key to (if(attempt < 3 && !permanent) "连接暂时中断，稍后自动重试。" else "原音已保存。${e.message?.take(180) ?: "转写暂未完成，请重试。"}")))
                    if(e is BackendHttpException && e.status == 401) { report("登录已失效，请重新登录。录音和文字草稿已保留。"); break }
                }
            }
        }
    }
    private fun refreshCaptureFeed() {
        val s = session ?: return
        if(feedJob?.isActive == true || state.value.busy || state.value.subject.isBlank()) return
        val path = root()
        feedJob = viewModelScope.launch {
            try {
                val result = io { client.json(s, "$path/stories") }
                gate.requireCurrent(s)
                val wasReady = state.value.stories.filter { it.text("status")=="ready" }.map { it.text("episode_id") }.toSet()
                val analyzed = state.value.stories.filter { it.optJSONObject("cumulative_analysis")?.text("status")=="complete" }.map { it.text("episode_id") }.toSet()
                val remainsOwner=result.text("role")=="owner"
                val resolvedSpace=state.value.space?.let { JSONObject(it.toString()).put("role",result.text("role")) }
                if(state.value.owner && !remainsOwner) {
                    closeRecorder(); captureJob?.cancel(); endVoice(); stopSource(); audio.stopPlayback()
                    state.value=state.value.forSpaceFallback(state.value.spaces,resolvedSpace).copy(stories=result.rows())
                } else state.value=state.value.copy(stories=result.rows(),space=resolvedSpace)
                if(state.value.owner) syncDrafts(s)
                // The expensive person view refreshes when memories change,
                // rather than blocking every screen every eight seconds.
                if(result.rows().any { (it.text("status")=="ready" && it.text("episode_id") !in wasReady) ||
                        (it.optJSONObject("cumulative_analysis")?.text("status")=="complete" && it.text("episode_id") !in analyzed) }) {
                    refreshNow(s)
                }
            } catch(e: Exception) {
                if(e is CancellationException) throw e
                if(gate.accepts(s) && e is BackendHttpException && e.status in setOf(401,403,404)) {
                    closeRecorder(); captureJob?.cancel(); stopSource(); audio.stopPlayback()
                    state.value = state.value.copy(stories=emptyList(), drafts=emptyMap(), local=emptyList(),reviewEpisode=null)
                    report("访问状态已变化，请重新登录或刷新空间。")
                }
                // A transient network error retains the displayed draft/audio.
            }
        }
    }
    private suspend fun syncDrafts(s: BackendSession) {
        gate.requireCurrent(s)
        val key = scopeKey(s)
        if(loadedDraftScope != key) {
            val saved = draftLock.withLock { io { draftStore.read(key) } }
            gate.requireCurrent(s)
            state.value = state.value.copy(drafts = saved + state.value.drafts)
            loadedDraftScope = key
        }
        val reviewed = state.value.stories.filter { it.optBoolean("reviewed") }.map { it.text("episode_id") }.toSet()
        if(state.value.drafts.keys.any { it in reviewed }) {
            state.value = state.value.copy(drafts=state.value.drafts.filterKeys { it !in reviewed })
            persistDrafts(s)
        }
        for(story in state.value.stories.filter { it.optBoolean("waiting_for_review") }) {
            val id = story.text("episode_id")
            if(reviewLinkPending(id)) continue
            if(id in state.value.drafts) continue
            val result = io { client.json(s, "/api/v1/episodes/${segment(id)}/transcript-review") }
            gate.requireCurrent(s)
            if(result.text("state") == "reviewing") {
                val draft = CaptureDraft.fromReview(id,result)
                val newest=state.value.local.any {it.episode==id && state.value.captureFocusRequest=="received:${it.key}"}
                state.value = state.value.copy(drafts = state.value.drafts + (id to draft),draftFocus=if(newest)id else state.value.draftFocus)
                persistDrafts(s)
            }
        }
    }
    private suspend fun persistDrafts(s: BackendSession) {
        gate.requireCurrent(s)
        val key=scopeKey(s); val snapshot=state.value.drafts
        draftLock.withLock { io { draftStore.write(key,snapshot) } }
        if(gate.accepts(s)) state.value=state.value.copy(draftSaveError=null)
    }
    private fun saveDraftEdits() {
        val s=session ?: return
        // Capture the identity and snapshot before switching dispatchers. A
        // late write from a previous space can never enter the new space file.
        val key=scopeKey(s); val snapshot=state.value.drafts
        viewModelScope.launch {
            try {
                draftLock.withLock { io { draftStore.write(key,snapshot) } }
                if(gate.accepts(s)) state.value=state.value.copy(draftSaveError=null)
            } catch(e: Exception) { if(e is CancellationException) throw e
                if(gate.accepts(s)) state.value=state.value.copy(draftSaveError="草稿暂未保存到手机，请保留页面后重试。") }
        }
    }
    fun focusDraft(id: String) { state.value=state.value.copy(draftFocus=id) }
    private fun reviewLinkPending(id: String): Boolean = state.value.local.any { it.blocksReview &&
        (it.episode==id || (it.episode.isBlank() && it.autoProcess && state.value.local.none { row -> row.episode==id })) }
    fun editDraft(id: String, text: String, supplement: String? = null) {
        if(text.length > 100_000 || (supplement?.length ?: 0)>3000 || state.value.savingEpisode==id) return
        val draft=state.value.drafts[id] ?: return
        state.value=state.value.copy(drafts=state.value.drafts + (id to draft.copy(text=text, supplement=supplement ?: draft.supplement)))
        saveDraftEdits()
    }
    fun saveDraft(id: String) {
        val s=session ?: return; val draft=state.value.drafts[id] ?: return
        if(reviewLinkPending(id)) { report("正在完成这段录音与原记忆的关联，请稍后保存。"); return }
        if(state.value.savingEpisode.isNotBlank() || state.value.busy) return
        if(draft.text.isBlank()) { report("请先填写要保存的文字。"); return }
        state.value=state.value.copy(savingEpisode=id)
        operation(s) {
            try {
                val consent=io { client.consent(s,state.value.subject,"CLOUD_TWIN") }
                io { client.json(s,"/api/v1/episodes/${segment(id)}/transcript-review","PATCH",
                    JSONObject().put("transcript",draft.text.trim()).put("supplement",draft.supplement.trim())
                        .put("cloud_analysis_consent_id",consent)) }
                gate.requireCurrent(s)
                state.value=state.value.copy(drafts=state.value.drafts-id, draftFocus=id, notice="已保存，正在整理记忆。")
                persistDrafts(s)
                if(state.value.reviewEpisode==id) closeReview()
                refreshNow(s)
            } finally { if(gate.accepts(s)) state.value=state.value.copy(savingEpisode="") }
        }
    }
    private fun beginOperation(): Long {
        val id = ++operationSequence
        state.value = state.value.copy(busy = true, error = null, operation = OperationFeedback(id, ActionPhase.RUNNING))
        return id
    }
    private data class CaptureTransfer(val id: String, val session: BackendSession, val capture: LocalCapture, val importing: Boolean)
    private var pendingTransfer: CaptureTransfer? = null
    init { reminders.disable(); savedSession.load()?.let { connect(it.first, it.second, remember = true) } }

    fun signIn(server: String, username: String, password: String, name: String? = null) {
        if(state.value.busy) return
        val operationId = beginOperation()
        viewModelScope.launch {
            try {
                val body = JSONObject().put("username", username.trim()).put("password", password)
                if(name != null) body.put("display_name", name.trim())
                val result = withContext(Dispatchers.IO) { accountRequest(server, if(name == null) "login" else "register", body) }
                state.value = state.value.copy(busy = false)
                connect(server, result.getString("actor_token"), remember = true)
            } catch(error: Exception) {
                if(error is CancellationException) throw error
                state.value = state.value.copy(busy = false, error = error.message ?: "登录未完成。",
                    operation = OperationFeedback(operationId, ActionPhase.FAILED))
            }
        }
    }

    fun report(message: String) { state.value = state.value.copy(error = message) }
    fun dismissError(expected: String) {
        // Dismiss only the message currently displayed, not a different failure.
        if(state.value.error == expected) state.value = state.value.copy(error = null)
    }
    fun checkConnection() { session?.let { loadServiceInfo(it.server) } }
    fun loadServiceInfo(server: String) {
        serviceInfoJob?.cancel()
        serviceInfoJob = viewModelScope.launch {
            state.value = state.value.copy(serviceInfo = ServiceInfo(), connectionCheck = ConnectionCheck(ConnectionPhase.CHECKING, "正在检查服务连接…"))
            val result = runCatching { withContext(Dispatchers.IO) { serviceInfoRequest(server) } }
            ensureActive()
            result.onSuccess { state.value = state.value.copy(serviceInfo = it, connectionCheck = connectedService(it)) }
                .onFailure { state.value = state.value.copy(connectionCheck = failedConnection(it)) }
        }
    }
    fun clearSharePreview() { state.value = state.value.copy(sharePreview = null, shareSelection = null) }
    fun previewShare(selection: ShareSelection) {
        val s = session ?: return; val path = root()
        operation(s) {
            val result = io { client.json(s, "$path/sharing/preview", "POST", selection.json()) }
            state.value = state.value.copy(sharePreview = result, shareSelection = selection)
        }
    }
    fun createInvitation(audioConfirmed: Boolean, cloud: Boolean, recipient: String?) {
        val s = session ?: return; val path = root()
        val selection = state.value.shareSelection ?: return
        val preview = state.value.sharePreview ?: return
        operation(s) {
            val result = io { client.json(s, "$path/invitations", "POST", selection.invitation(preview, audioConfirmed, cloud, recipient)) }
            state.value = state.value.copy(issuedInvitation = result, sharePreview = null, shareSelection = null,
                notice = if(result.has("code")) "邀请码已生成，亲友领取后仍需你确认。" else "接收人已选定，请核对账号后批准分享。")
            refreshNow(s)
        }
    }
    fun claimInvitation(code: String) {
        val s = session ?: return
        operation(s) {
            io { client.json(s, "/api/v1/workbench/invitations/claim", "POST", JSONObject().put("code", code.trim())) }
            state.value = state.value.copy(notice = "已领取邀请，等待记录者确认。批准后点击空间名称进入。")
            refreshNow(s)
        }
    }
    fun connect(server: String, token: String, remember: Boolean = false) {
        if(state.value.busy || state.value.recording) return
        clearIdentity()
        val next = runCatching { gate.connect(server, token) }.getOrElse { report(it.message ?: "服务地址无效。"); return }
        session = next
        operation(next) {
            val result = io { client.json(next, "/api/v1/workbench/spaces") }
            if(remember) savedSession.save(next.server, next.token) else savedSession.clear()
            state.value = state.value.copy(actor = result.text("actor_id"), actorName = result.text("display_name"), spaces = result.rows())
            val saved = spacePreferences.getString("${next.server}:${result.text("actor_id")}", null)
            val allSpaces = discoverSpaces(next, result.rows())
            val chosen = initialSpace(allSpaces, saved)
            state.value = state.value.copy(spaces = allSpaces, space = chosen, spaceChoiceRequired = chosen == null && allSpaces.size > 1)
            refreshNow(next)
            polling?.cancel()
            polling = viewModelScope.launch {
                while(isActive && gate.accepts(next)) {
                    delay(if(hasPendingCaptureWork()) 5_000 else 30_000)
                    if(foreground && pendingTransfer == null && !state.value.recording && state.value.subject.isNotBlank()) refreshCaptureFeed()
                    pumpCaptures()
                }
            }
        }
    }
    fun selectSpace(space: JSONObject) {
        if(state.value.busy || state.value.recording) return
        if(state.value.spaces.none { it.text("subject_id") == space.text("subject_id") }) return
        session?.let { spacePreferences.edit().putString("${it.server}:${state.value.actor}", space.text("subject_id")).apply() }
        closeRecorder(); endVoice();stopSource(); audio.stopPlayback(); polling?.cancel(); captureJob?.cancel(); feedJob?.cancel()
        captureAttempts.clear(); captureRetryAt.clear(); reminders.disable(); pendingTransfer = null
        session = gate.advance()
        state.value = NativeState(actor = state.value.actor, actorName = state.value.actorName, spaces = state.value.spaces, space = space)
        refresh()
        val next = session ?: return
        polling = viewModelScope.launch { while(isActive && gate.accepts(next)) {
            delay(if(hasPendingCaptureWork()) 5_000 else 30_000)
            if(foreground && pendingTransfer == null && !state.value.recording) refreshCaptureFeed()
            pumpCaptures()
        } }
    }
    fun logout() {
        val previous = session
        fun leave() {
            savedSession.clear(); clearIdentity()
            if(previous != null) viewModelScope.launch {
                runCatching { withContext(Dispatchers.IO) { accountRequest(previous.server, "logout", token = previous.token) } }
                    .onFailure { if(session == null) report("已清除本机登录；断网时无法撤销服务端会话，它将在到期后失效。") }
            }
        }
        if(state.value.companionRecording.isNotBlank()) { finishCompanionRecording { leave() } } else if(state.value.recording) { finish { leave() } } else leave()
    }
    private fun clearIdentity() {
        closeRecorder()
        endVoice()
        reminders.disable(); creationKeys.clear()
        gate.clear(); session = null; polling?.cancel(); ticker?.cancel(); recordTarget = null; activeCapture = null; pendingTransfer = null
        captureJob?.cancel(); feedJob?.cancel(); captureAttempts.clear(); captureRetryAt.clear(); loadedDraftScope=""
        stopSource(); audio.stopPlayback(); state.value = NativeState()
    }
    private fun root() = "${BackendClient.WORKBENCH}/${segment(state.value.subject)}"
    private fun companionDraftKey(s: BackendSession) = "${s.server}:${state.value.actor}:${state.value.subject}"
    private fun companionDrafts(): JSONObject = if(companionLedger.baseFile.exists()) JSONObject(companionLedger.readFully().toString(Charsets.UTF_8)) else JSONObject()
    private fun persistCompanionDraft(s: BackendSession, draft: CompanionAudioDraft?) {
        gate.requireCurrent(s)
        val all=companionDrafts();val key=companionDraftKey(s)
        if(draft==null) all.remove(key) else all.put(key,draft.saved())
        val stream=companionLedger.startWrite()
        try {stream.write(all.toString().toByteArray(Charsets.UTF_8));companionLedger.finishWrite(stream)}
        catch(e: Exception){companionLedger.failWrite(stream);throw e}
        state.value=state.value.copy(companionAudio=draft)
    }
    fun setDailyReminder(enabled: Boolean) {
        if(enabled && (!state.value.owner || session == null)) return
        try {
            if(enabled) reminders.enable() else reminders.disable()
            state.value = state.value.copy(dailyReminder = enabled, error = null)
        } catch(error: Exception) {
            reminders.disable(); state.value = state.value.copy(dailyReminder = false, error = error.message ?: "本机通知暂不可用。")
        }
    }
    private fun subjectRoot() = "/api/v1/subjects/${segment(state.value.subject)}"
    private fun scopeKey(s: BackendSession) = MessageDigest.getInstance("SHA-256")
        .digest("${s.server}|${state.value.actor}|${state.value.subject}".toByteArray()).joinToString("") { "%02x".format(it) }
    private fun records(): JSONObject = runCatching { ledger.openRead().bufferedReader().use { JSONObject(it.readText()) } }.getOrDefault(JSONObject())
    private fun writeRecords(data: JSONObject) {
        val stream = ledger.startWrite()
        try { stream.write(data.toString().toByteArray()); ledger.finishWrite(stream) }
        catch(error: Exception) { ledger.failWrite(stream); throw error }
    }
    private fun localCaptures(key: String): List<LocalCapture> {
        val links = records().optJSONArray(key) ?: JSONArray()
        val available = audio.recordings().associateBy { it.audioPath }
        return (0 until links.length()).mapNotNull { i ->
            val row = links.getJSONObject(i)
            val original = available[row.text("path")] ?: row.text("imported_recording").takeIf { it.isNotBlank() }?.let {
                runCatching { RecordingMetadata.decode(it) }.getOrNull()?.takeIf { recording -> File(recording.audioPath).let { file -> file.isFile && file.length() > 0 } }
            }
            original?.let { recording -> LocalCapture(recording, row.text("key"), row.text("episode"),
                row.optJSONObject("revision")?.let { RevisionTarget(it.text("memory"), it.text("kind"), it.text("time")) }, row.optBoolean("linked"),
                row.optJSONObject("client_transcript")?.let { runCatching { ClientTranscript.parse(it.toString()) }.getOrNull() }, row.optBoolean("upload_attempted"),
                if(row.has("upload_with_transcript")) row.getBoolean("upload_with_transcript") else null,
                row.text("calibration_id"), row.text("source").ifBlank { "ANDROID_MIC" }, row.text("hardware_import_id"), row.optBoolean("auto_process")) }
        }.reversed()
    }
    private suspend fun saveCapture(s: BackendSession, capture: LocalCapture) {
        gate.requireCurrent(s)
        val key = scopeKey(s)
        val captures = captureLedgerLock.withLock { io {
        val all = records(); val values = all.optJSONArray(key) ?: JSONArray()
        val row = JSONObject().put("path", capture.recording.audioPath).put("key", capture.key).put("episode", capture.episode).put("linked", capture.linked)
            .put("upload_attempted", capture.uploadAttempted)
            .put("calibration_id",capture.calibrationId).put("source",capture.source)
            .put("auto_process",capture.autoProcess)
        if(capture.source in setOf("IMPORT", "WORK_3200")) row.put("imported_recording",RecordingMetadata.encode(capture.recording))
        if(capture.hardwareImportId.isNotBlank()) row.put("hardware_import_id",capture.hardwareImportId)
        capture.transcript?.let { row.put("client_transcript", it.toJson()) }
        capture.uploadWithTranscript?.let { row.put("upload_with_transcript", it) }
        capture.revision?.let { row.put("revision", JSONObject().put("memory", it.memory).put("kind", it.kind).put("time", it.time)) }
        val index = (0 until values.length()).firstOrNull { values.getJSONObject(it).text("path") == capture.recording.audioPath }
        if(index == null) values.put(row) else values.put(index, row)
        all.put(key, values); writeRecords(all)
        localCaptures(key)
        } }
        gate.requireCurrent(s)
        state.value = state.value.copy(local = captures)
    }
    fun refresh() { val s = session ?: return; operation(s) {
        try { refreshNow(s) } catch(error: Exception) {
            if(gate.accepts(s)) {
                stopSource(); audio.stopPlayback()
                state.value = state.value.copy(stories = emptyList(), grants = emptyList(), revisions = emptyList(),
                    requests = emptyList(), candidates = emptyList(), candidateJobs = emptyList(), profileUpdates = emptyList(), portrait = JSONObject(), narrative = JSONObject(), narrativeJobs = emptyList(), vocabulary = "", answer = null, search = emptyList(), reviewEpisode = null,
                    companion = JSONObject(), contributionOriginal = null, voiceProfile = JSONObject(), voiceGrants = emptyList(), calibrations = emptyList(), calibrationId = "", invitations = emptyList(), recipients = emptyList(), sharePreview = null, shareSelection = null, issuedInvitation = null)
            }
            throw error
        }
    } }
    private suspend fun optionalJson(s: BackendSession, path: String): JSONObject = try { io { client.json(s,path) } } catch(e: BackendHttpException) { if(e.status in setOf(403,404)) JSONObject() else throw e }
    private suspend fun discoverSpaces(s: BackendSession, regular: List<JSONObject>): List<JSONObject> =
        mergeCompanionSpaces(regular, optionalJson(s,"/api/v1/companion/spaces").rows())
    private suspend fun refreshNow(s: BackendSession) {
        val spaces = discoverSpaces(s, io { client.json(s, "/api/v1/workbench/spaces").rows() })
        val selected = spaces.firstOrNull { it.text("subject_id") == state.value.subject }
            ?: if(state.value.spaceChoiceRequired) initialSpace(spaces, null) else spaces.firstOrNull()
        if(selected?.text("subject_id").orEmpty() != state.value.subject) {
            closeRecorder()
            stopSource(); audio.stopPlayback()
            state.value = state.value.forSpaceFallback(spaces, selected)
        } else state.value = state.value.copy(spaces = spaces, space = selected,
            spaceChoiceRequired = selected == null && spaces.size > 1)
        if(state.value.subject.isBlank()) return
        val path = root()
        val companionOnly = selected?.text("role") == "companion"
        val companion = optionalJson(s,"$path/companion")
        val stories = if(companionOnly) optionalJson(s,"$path/stories") else io { client.json(s, "$path/stories") }
        // Authoritative role comes from server, never from locally entered role labels.
        val grants = if(companionOnly) optionalJson(s,"$path/grants") else io { client.json(s, "$path/grants") }
        val requests = if(companionOnly) optionalJson(s,"$path/requests") else io { client.json(s, "$path/requests") }
        val capabilities = io { client.json(s, "/api/v1/workbench/capabilities") }
        val portrait = if(companionOnly) JSONObject() else io { client.json(s, "$path/portrait").optJSONObject("views") ?: JSONObject() }
        val owner = stories.text("role") == "owner"
        if (!owner) closeRecorder()
        val info = io { loadServiceInfo { client.json(s, "/api/v1/service-info") } }
        val invitations = if(owner && info.invitations) io { client.json(s, "$path/invitations").rows() } else emptyList()
        val recipients = if(owner && info.invitations) io { client.json(s, "$path/recipients").rows() } else emptyList()
        val narrative = if(capabilities.optBoolean("narrative")) optionalJson(s,"$path/narrative") else JSONObject()
        val voiceProfile = optionalJson(s,"${subjectRoot()}/voice/profile")
        val calibrations = if(owner) optionalJson(s,"${subjectRoot()}/calibrations").rows() else emptyList()
        val voiceGrants = if(owner) recipients.map { optionalJson(s,"${subjectRoot()}/voice/recipients/${segment(it.text("actor_id"))}") } else emptyList()
        val narrativeJobs = if(owner && capabilities.optBoolean("narrative")) io { client.json(s, "$path/narrative/jobs").rows() } else emptyList()
        val revisions = if(owner) io { client.json(s, "$path/revisions").rows() } else emptyList()
        val candidates = if(owner) io { client.json(s, "$path/profile-candidates") } else JSONObject()
        val updates = if(owner) io { client.json(s, "$path/profile-candidates/updates").rows() } else emptyList()
        val vocabulary = if(owner) io { client.json(s, "$path/vocabulary").text("text") } else ""
        gate.requireCurrent(s)
        val changed = state.value.stories.map { it.toString() } != stories.rows().map { it.toString() } ||
            state.value.grants.map { it.toString() } != grants.rows().map { it.toString() } ||
            state.value.candidates.map { it.toString() } != candidates.rows().map { it.toString() } || state.value.narrative.toString() != narrative.toString() || state.value.companion.toString() != companion.toString() || state.value.voiceProfile.toString() != voiceProfile.toString()
        // New recordings and processing updates must not stop an unrelated
        // original currently playing. Losing access still clears the player.
        if(state.value.playerAccessLost(stories.rows())) { stopSource(); audio.stopPlayback() }
        val savedAnswer=if(changed) null else state.value.answer?.let { answer ->
            try { io {client.json(s,"${subjectRoot()}/twin/answers/${segment(answer.text("answer_id"))}")} }
            catch(e: BackendHttpException) { if(e.status in setOf(403,404,409)) {stopSource();null} else throw e }
        }
        val restoredCompanion = state.value.companionAudio ?: io { companionDrafts().optJSONObject(companionDraftKey(s))?.let(::restoredCompanionAudio) }
        val localRows = if(owner) captureLedgerLock.withLock { val key=scopeKey(s); io {localCaptures(key)} } else emptyList()
        gate.requireCurrent(s)
        state.value = state.value.copy(space = state.value.space?.put("role", stories.text("role").ifBlank { selected?.text("role") ?: "companion" }), stories = stories.rows(),
            grants = grants.rows(), requests = requests.rows(), revisions = revisions, candidates = candidates.rows(), asrCapabilities = capabilities,
            serviceInfo = info, invitations = invitations, recipients = recipients, companion = companion, voiceProfile = voiceProfile, voiceGrants = voiceGrants,
            contributionOriginal = retainedContributionOriginal(state.value.contributionOriginal, companion.rows("contributions")),
            calibrations = calibrations,
            candidateJobs = candidates.rows("jobs"), profileUpdates = updates, vocabulary = vocabulary, portrait = portrait, narrative = narrative, narrativeJobs = narrativeJobs, local = localRows,
            answer = savedAnswer, search = if(changed) emptyList() else state.value.search,
            companionAudio = restoredCompanion)
        if(owner) { syncDrafts(s); pumpCaptures() }
    }
    fun start(revision: RevisionTarget?, calibrationId: String = "") {
        val s = session ?: return
        if(!state.value.owner || state.value.busy || state.value.recording) return
        operation(s) {
            if(calibrationId.isNotBlank()) requireCalibrationCapture(calibrationId)
            stopSource()
            val started = audio.start()
            recordTarget = revision
            val capture = LocalCapture(started, "android-${File(started.audioPath).nameWithoutExtension}", revision = revision, calibrationId = calibrationId, autoProcess = calibrationId.isBlank())
            activeCapture = capture
            try { saveCapture(s, capture) } catch(error: Exception) {
                runCatching { audio.stop() }; activeCapture = null; throw error
            }
            state.value = state.value.copy(recording = true, paused = false, elapsed = 0, notice = "正在本机录音，尚未上传。")
            ticker = viewModelScope.launch { while(isActive) { delay(250); state.value = state.value.copy(elapsed = audio.elapsedMillis()) } }
        }
    }
    fun pauseOrResumeRecording() {
        val s = session ?: return
        if(!state.value.recording) return
        operation(s) {
            val paused = state.value.paused
            if(paused) audio.resume() else audio.pause()
            state.value = state.value.copy(paused = !paused)
        }
    }
    fun finish(after: (() -> Unit)? = null) {
        val s = session ?: return
        if(!state.value.recording) { after?.invoke(); return }
        operation(s) {
            ticker?.cancel()
            val recording = try { audio.stop() } catch(error: Exception) {
                // The capture service preserves successful audio when sidecar metadata fails.
                val recovered = audio.recordings().firstOrNull { it.audioPath == activeCapture?.recording?.audioPath }
                if(recovered == null) throw error else recovered
            } finally { state.value = state.value.copy(recording = false, paused = false, elapsed = 0) }
            saveCapture(s, activeCapture?.copy(recording = recording) ?: LocalCapture(recording,
                "android-${File(recording.audioPath).nameWithoutExtension}", revision = recordTarget))
            activeCapture = null
            recordTarget = null
            // Publish only after both the audio and the scoped capture ledger are saved.
            state.value = state.value.copy(savedCaptureId = recording.audioPath, notice = "收到录音，正在转成文字。")
            pumpCaptures()
            after?.invoke()
        }
    }
    fun upload(capture: LocalCapture, recordingConsent: Boolean) {
        val s = session ?: return
        if(!recordingConsent) { report("请先确认本段完整原音的上传与转写方式；原音仍保留本机。"); return }
        viewModelScope.launch {
            try { saveCapture(s, capture.copy(autoProcess=true)); captureAttempts.remove(capture.key); captureRetryAt.remove(capture.key); pumpCaptures() }
            catch(e: Exception) { if(e is CancellationException) throw e; if(gate.accepts(s)) report(e.message ?: "未能加入转写队列。") }
        }
    }
    private suspend fun uploadCapture(s: BackendSession, capture: LocalCapture) {
        gate.requireCurrent(s)
        val caps = checkNotNull(state.value.asrCapabilities) { "正在获取转写配置，请稍后重试。" }
        val clientAsr = capture.usesClientTranscript(caps.text("stt") == "client")
        if(!clientAsr && caps.text("stt_processing") == "cloud" && !caps.optBoolean("stt_configured")) {
            error("转写服务暂不可用，原音已保存。")
        }
        val asrPolicy = if(!clientAsr && caps.text("stt_processing") == "cloud") caps.text("cloud_asr_policy") else null
        val correctionPolicy = if(!clientAsr) caps.text("transcript_correction_policy").takeIf { it.isNotBlank() } else null
        if(clientAsr && capture.episode.isBlank() && capture.transcript == null) {
            error("当前服务需要外部机器稿，请在我的录音中继续。")
        }
        if(!state.value.owner) return
        val subject = state.value.subject; val path = root()
        run {
            if(clientAsr) io { capture.transcript?.requireMatches(File(capture.recording.audioPath)) }
            val sending = capture.beginUpload(clientAsr).also { saveCapture(s, it) }
            val consent = io { client.consent(s, subject, "RECORDING") }
            val hardwareIdentity = if(capture.source == "WORK_3200") hardwareScope() else null
            val hardwareJournal = hardwareIdentity?.let { Work3200ImportJournal(File(appContext.filesDir, "work3200-imports")) }
            val metadata = if(hardwareIdentity != null && hardwareJournal != null) io {
                val candidate = hardwareJournal.uploadCandidate(capture.hardwareImportId, hardwareIdentity)
                require(candidate.idempotencyKey == capture.key && candidate.file.canonicalPath == File(capture.recording.audioPath).canonicalPath)
                val receipt = hardwareJournal.rawReceipt(capture.hardwareImportId, hardwareIdentity)
                JSONObject().put("import_id", capture.hardwareImportId).put("raw_sha256", receipt.sha256)
                    .put("device_marker_pending",hardwareJournal.deviceMarkerPending(capture.hardwareImportId,hardwareIdentity))
                    .put("file_id", receipt.fileId).put("markers", JSONArray().apply {
                        hardwareJournal.markers(capture.hardwareImportId, hardwareIdentity).forEach { put(JSONObject().put("offset_ms", it.offsetMs).put("origin", it.origin)) }
                    })
            } else null
            state.value = state.value.copy(uploadKey = capture.key, uploadPercent = 0)
            try { submitCapture(sending,
                upload = { io { client.upload(s, subject, consent, capture.recording, capture.key, asrPolicy, if(clientAsr) sending.transcript else null, capture.calibrationId, capture.source, correctionPolicy, metadata) { sent, total ->
                    viewModelScope.launch { if(gate.accepts(s) && state.value.uploadKey == capture.key)
                        if(state.value.uploadPercent != transferPercent(sent,total)) state.value = state.value.copy(uploadPercent = transferPercent(sent, total)) }
                } } },
                persist = { saved ->
                    saveCapture(s, saved)
                    if(saved.episode.isNotBlank() && hardwareIdentity != null && hardwareJournal != null)
                        io { hardwareJournal.markUploaded(capture.hardwareImportId, hardwareIdentity, saved.episode) }
                },
                link = { episode, revision ->
                io { client.json(s, "$path/revisions", "POST", JSONObject().put("episode_id", episode)
                    .put("target_memory_id", revision.memory).put("kind", revision.kind)
                    .put("time_text", revision.time.ifBlank { null })) }
            }) } finally { if(gate.accepts(s)) state.value = state.value.copy(uploadKey = "", uploadPercent = null) }
            refreshCaptureFeed()
        }
    }
    fun beginCaptureTransfer(capture: LocalCapture, importing: Boolean): String? {
        val s = session ?: return null
        if(state.value.busy || state.value.recording || !state.value.owner || pendingTransfer != null) return null
        if(state.value.local.none { it.key == capture.key && it.recording.audioPath == capture.recording.audioPath }) return null
        if(importing && (capture.uploadAttempted || capture.episode.isNotBlank())) {
            report("已开始上传，不能替换机器稿。请重试原请求，再到核对页修改。"); return null
        }
        return java.util.UUID.randomUUID().toString().also { pendingTransfer = CaptureTransfer(it, s, capture, importing) }
    }
    fun cancelCaptureTransfer(id: String) { if(pendingTransfer?.id == id) pendingTransfer = null }
    fun importTranscript(id: String, read: () -> java.io.InputStream?) {
        val transfer = pendingTransfer?.takeIf { it.id == id && it.importing } ?: return
        pendingTransfer = null
        if(!gate.accepts(transfer.session)) return
        operation(transfer.session) {
            val draft = io {
                val bytes = requireNotNull(read()) { "无法打开转写文件。" }.use { it.readBytesLimited(ClientTranscript.MAX_DOCUMENT_BYTES) }
                ClientTranscript.parse(bytes.toString(Charsets.UTF_8))
            }
            gate.requireCurrent(transfer.session)
            saveCapture(transfer.session, transfer.capture.withTranscript(draft))
            state.value = state.value.copy(notice = "机器稿已与原音匹配并保存在本机；上传后仍需核对，尚未整理记忆。")
        }
    }
    fun exportOriginal(id: String, write: () -> java.io.OutputStream?) {
        val transfer = pendingTransfer?.takeIf { it.id == id && !it.importing } ?: return
        pendingTransfer = null
        if(!gate.accepts(transfer.session)) return
        operation(transfer.session) {
            io {
                val file = File(transfer.capture.recording.audioPath)
                require(file.isFile && file.length() > 0) { "本机原音不存在或为空。" }
                requireNotNull(write()) { "无法写入选择的位置。" }.use { output -> file.inputStream().use { it.copyTo(output) } }
            }
            gate.requireCurrent(transfer.session)
            state.value = state.value.copy(notice = "已导出原音副本，手机内原音保留。转写后选择对应机器稿继续。")
        }
    }
    fun review(episode: String) {
        val s = session ?: return
        if(state.value.local.any { it.episode == episode && it.blocksReview }) { report("请先在本机录音列表重试上传，完成修订关联后再核对文字。"); return }
        operation(s) {
            val result = io { client.json(s, "/api/v1/episodes/${segment(episode)}/transcript-review") }
            check(result.text("state") == "reviewing") { "转写尚未完成或已经提交，请刷新后查看。" }
            val warnings = result.optJSONArray("review_warnings") ?: JSONArray()
            val draft=state.value.drafts[episode] ?: CaptureDraft.fromReview(episode,result)
            state.value = state.value.copy(drafts=state.value.drafts+(episode to draft), reviewEpisode = episode, reviewText = draft.text, reviewSupplement = draft.supplement,
                reviewMachineText = result.text("machine_transcript"), reviewCorrection = result.optJSONObject("automatic_correction"),
                reviewHighlights = result.optJSONObject("recording_highlights"),
                reviewInitialText = result.text("transcript"), reviewWarnings = (0 until warnings.length()).map { warnings.optString(it) },
                reviewParagraphPreview = result.optString("paragraph_preview").takeIf { it.isNotBlank() && it != "null" })
            persistDrafts(s)
        }
    }
    fun closeReview() { state.value = state.value.copy(reviewEpisode = null, reviewText = "", reviewSupplement = "", reviewInitialText = "", reviewWarnings = emptyList(), reviewParagraphPreview = null, reviewMachineText = "", reviewCorrection = null) }
    fun useParagraphPreview() {
        val current = state.value
        if(current.reviewEpisode != null && current.reviewText == current.reviewInitialText && current.reviewParagraphPreview != null)
            state.value = current.copy(reviewText = current.reviewParagraphPreview)
    }
    fun editSupplement(text: String) { if(text.length <= 3000) {
        state.value = state.value.copy(reviewSupplement = text)
        state.value.reviewEpisode?.let { editDraft(it,state.value.reviewText,text) }
    } }
    fun saveVocabulary(text: String) { mutation("/vocabulary", "PUT", JSONObject().put("text", text)) }
    fun editReview(episode: String, text: String) {
        if(state.value.reviewEpisode == episode) { state.value = state.value.copy(reviewText = text); editDraft(episode,text) }
    }
    fun confirmReview(text: String, cloudConfirmed: Boolean) {
        val episode = state.value.reviewEpisode ?: return
        if(!cloudConfirmed) { report("请确认将核对后的文字交由服务器整理；其配置的云端模型会收到文字。"); return }
        if(text.isBlank()) { report("核对文字不能为空。"); return }
        editDraft(episode,text,state.value.reviewSupplement)
        saveDraft(episode)
    }
    fun mutation(suffix: String, method: String, body: JSONObject? = null, subjectApi: Boolean = false, onSuccess: (() -> Unit)? = null) {
        val s = session ?: return; val path = if(subjectApi) subjectRoot() else root()
        operation(s) {
            stopSource(); audio.stopPlayback(); state.value = state.value.copy(answer = null, search = emptyList())
            io { client.json(s, path + suffix, method, body) }; refreshNow(s); onSuccess?.invoke()
        }
    }
    fun retry(episode: String, emptyResult: Boolean = false) {
        val s = session ?: return
        val action = if(emptyResult) "reextract-empty" else "retry"
        operation(s) { io { client.json(s, "/api/v1/episodes/${segment(episode)}/$action", "POST") }; refreshNow(s) }
    }
    private fun cloudConsent(s: BackendSession): String {
        if(state.value.owner) return client.consent(s, state.value.subject, "CLOUD_TWIN")
        return state.value.grants.firstOrNull { cloudProcessingAllowed(it) }?.text("grant_id")
            ?: throw IllegalStateException("记录者尚未允许共享故事参与云端问答。")
    }
    fun loadVoiceCapabilities() {
        val s=session?:return
        operation(s){
            val value=io{client.json(s,"/api/v1/voice-capabilities")}
            val engines=value.optJSONArray("engines")
            val speeds=value.optJSONArray("response_speeds")
            state.value=state.value.copy(fastVoiceAvailable=value.optBoolean("enabled") &&
                speeds?.let{a->(0 until a.length()).any{a.optString(it)=="fast"}}==true,
                stepVoiceAvailable=value.optBoolean("enabled") &&
                engines?.let{a->(0 until a.length()).any{a.optString(it)=="step_realtime"}}==true)
        }
    }
    fun beginVoice(mode:String,simpleMode:Boolean,calibrationId:String?=null,responseSpeed:String="reviewed",voiceEngine:String="pipeline") {
        val s=session?:return
        val subject=state.value.subject
        if(subject.isBlank()||state.value.recording||state.value.busy||!foreground)return
        endVoice()
        val ticket=voiceStartGate.begin(s)
        operation(s){
            val capabilities=io{client.json(s,"/api/v1/voice-capabilities")}
            check(capabilities.optBoolean("enabled")){"这个账号暂未开放语音聊聊。"}
            check(voiceEngine=="pipeline" || capabilities.optJSONArray("engines")?.let{a->(0 until a.length()).any{a.optString(it)==voiceEngine}}==true){"服务器尚未开放实时试用。"}
            val streamed=capabilities.optJSONArray("response_speeds")?.let{a->(0 until a.length()).any{a.optString(it)=="streamed"}}==true
            val speed=if(calibrationId!=null)"reviewed" else if(voiceEngine=="step_realtime")"fast" else if(responseSpeed=="fast"&&streamed)"streamed" else responseSpeed
            check(speed=="reviewed" || capabilities.optJSONArray("response_speeds")?.let{a->(0 until a.length()).any{a.optString(it)==speed}}==true){"服务器尚未开放快速回复，请关闭开关后开始。"}
            stopSource();audio.stopPlayback()
            val consent=io{cloudConsent(s)}
            val created=io{client.json(s,"/api/v1/subjects/${segment(subject)}/voice-sessions","POST",
                JSONObject().put("cloud_consent_id",consent).put("mode",mode).put("simple_mode",simpleMode)
                    .put("policy","continuous-voice-v1").put("cloud_asr_allowed",true).put("cloud_tts_allowed",true)
                    .put("purpose",if(calibrationId==null)"dialogue" else "calibration_report")
                    .apply{if(calibrationId!=null)put("calibration_id",calibrationId);if(speed!="reviewed")put("response_speed",speed);if(voiceEngine!="pipeline")put("engine",voiceEngine)})}
            val published=voiceStartGate.publish(ticket){
                if(state.value.subject==subject){
                    val engine=VoiceCallEngine(appContext,
                        {gate.accepts(s)&&state.value.subject==subject}, {foreground})
                    callState.value=engine
                    engine.start(s,created.getString("websocket_path"),created.getString("session_id"))
                }
            }
            if(!published || state.value.subject!=subject)io{
                runCatching{client.json(s,"/api/v1/voice-sessions/${segment(created.getString("session_id"))}","DELETE")}
            }
        }
    }
    fun endVoice(){voiceStartGate.invalidate();callState.value?.close();callState.value=null}
    fun ask(question: String, cloudConfirmed: Boolean, mode: String = "evidence") {
        val s = session ?: return
        if(!cloudConfirmed || question.isBlank()) { report("请填写问题并明确同意本次云端文字处理。"); return }
        val path = subjectRoot()
        operation(s) {
            stopSource();state.value = state.value.copy(answer = null)
            val consent = io { cloudConsent(s) }
            val answer = io { client.json(s, "$path/twin/answers", "POST", JSONObject().put("question", question.trim()).put("mode", mode).put("cloud_consent_id", consent)) }
            state.value = state.value.copy(answer = answer)
        }
    }
    fun search(query: String) {
        val s = session ?: return; val path = subjectRoot()
        operation(s) {
            state.value = state.value.copy(search=emptyList(),searchQuery="")
            val result = io { client.json(s, "$path/memory-search?q=${segment(query)}") }
            state.value = state.value.copy(search = result.rows(),searchQuery=query.trim())
        }
    }
    fun openCalibration(id: String) {
        val s=session?:return; if(!state.value.owner || state.value.recording) return
        operation(s) {
            val result=io {client.json(s,"${subjectRoot()}/calibrations/${segment(id)}")}
            state.value=state.value.copy(calibrationId=id,calibrations=listOf(result)+state.value.calibrations.filter{it.text("calibration_id")!=id})
        }
    }
    fun closeCalibration() { if(!state.value.recording) state.value=state.value.copy(calibrationId="") }
    fun prepareVoiceCalibration(question:String,mode:String){
        val s=session?:return
        if(!state.value.owner||question.isBlank())return
        operation(s){
            stopSource();state.value=state.value.copy(answer=null)
            val consent=io{cloudConsent(s)}
            val result=io{client.json(s,"${subjectRoot()}/calibrations/prepare-voice","POST",
                JSONObject().put("question",question.trim()).put("mode",mode).put("cloud_consent_id",consent))}
            state.value=state.value.copy(calibrationId=result.text("calibration_id"),
                calibrations=listOf(result)+state.value.calibrations.filter{it.text("calibration_id")!=result.text("calibration_id")})
        }
    }
    fun startCalibration(answer: JSONObject, cloud: Boolean) {
        val s=session?:return; if(!state.value.owner || !cloud) return
        operation(s) {
            val consent=io {cloudConsent(s)}
            val result=io {client.json(s,"${subjectRoot()}/calibrations","POST",JSONObject().put("twin_answer_id",answer.text("answer_id")).put("cloud_consent_id",consent))}
            state.value=state.value.copy(calibrationId=result.text("calibration_id"),calibrations=listOf(result)+state.value.calibrations.filter{it.text("calibration_id")!=result.text("calibration_id")})
        }
    }
    fun completeCalibration(id: String, cloud: Boolean) {
        val s=session?:return; if(!state.value.owner || !cloud) return
        operation(s) {
            val consent=io {cloudConsent(s)}
            val result=io {client.json(s,"${subjectRoot()}/calibrations/${segment(id)}/complete","POST",JSONObject().put("cloud_consent_id",consent))}
            state.value=state.value.copy(calibrations=listOf(result)+state.value.calibrations.filter{it.text("calibration_id")!=id})
        }
    }
    private fun requireCalibrationCapture(id: String) {
        val run=state.value.calibrations.firstOrNull{it.text("calibration_id")==id}
        require(run?.text("status")=="awaiting_human" && run.text("human_episode_id").isBlank() && state.value.local.none{it.calibrationId==id}) {"这次对照已有本人录音，请继续核对。"}
    }
    fun importCalibrationAudio(id: String, mime: String, read: () -> ByteArray) {
        val s=session?:return; if(!state.value.owner || state.value.recording) return
        operation(s) {
            requireCalibrationCapture(id)
            val extension=mapOf("audio/wav" to "wav","audio/x-wav" to "wav","audio/mpeg" to "mp3","audio/ogg" to "ogg","audio/webm" to "webm","audio/mp4" to "m4a")[mime]
                ?: throw IllegalArgumentException("请选择 M4A、WAV、MP3、OGG 或 WebM 音频。")
            val file=File(companionFiles,"calibration-${java.util.UUID.randomUUID()}.$extension")
            val recording=io {
                val bytes=read();require(bytes.isNotEmpty() && bytes.size<=40*1024*1024){"请选择不超过40MB的音频。"};file.writeBytes(bytes)
                val retriever=android.media.MediaMetadataRetriever()
                try {
                    retriever.setDataSource(file.absolutePath)
                    val duration=retriever.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0
                    require(duration>0){"无法读取这段音频，请换一个文件。"}
                    AudioRecording(file.absolutePath,duration,mime,file.length(),0,1,java.time.Instant.now().toString())
                } finally {retriever.release()}
            }
            saveCapture(s,LocalCapture(recording,"android-${file.nameWithoutExtension}",calibrationId=id,source="IMPORT"))
            state.value=state.value.copy(notice="本人原音已保存在本机。")
        }
    }
    fun startCompanionRecording(purpose: String) {
        val s = session ?: return
        if(state.value.recording || purpose !in setOf("contribution", "letter")) return
        operation(s) {
            stopSource(); audio.stopPlayback(); val started=audio.start()
            persistCompanionDraft(s,CompanionAudioDraft(purpose,File(started.audioPath),started.mimeType))
            state.value = state.value.copy(recording = true, companionRecording = purpose, elapsed = 0)
            ticker = viewModelScope.launch { while(isActive) { delay(250); state.value = state.value.copy(elapsed = audio.elapsedMillis()) } }
        }
    }
    fun finishCompanionRecording(after: (() -> Unit)? = null) {
        val s = session ?: return; val purpose = state.value.companionRecording
        if(purpose.isBlank()) return
        operation(s) {
            ticker?.cancel()
            val result = try { audio.stop() } finally { state.value = state.value.copy(recording = false, companionRecording = "", elapsed = 0) }
            persistCompanionDraft(s,state.value.companionAudio?.copy(file=File(result.audioPath),mime=result.mimeType) ?: CompanionAudioDraft(purpose,File(result.audioPath),result.mimeType))
            state.value = state.value.copy(notice = "声音已留在本机。")
            after?.invoke()
        }
    }
    fun importCompanionAudio(purpose: String, mime: String, read: () -> ByteArray) {
        val s = session ?: return
        operation(s) {
            val file = io {
                val bytes = read(); require(bytes.isNotEmpty() && bytes.size <= 40 * 1024 * 1024) { "请选择 40 MB 以内的音频。" }
                val suffix = when(mime) { "audio/wav", "audio/x-wav" -> "wav"; "audio/mpeg" -> "mp3"; "audio/webm" -> "webm"; "audio/ogg" -> "ogg"; else -> "m4a" }
                File(companionFiles,"${java.util.UUID.randomUUID()}.$suffix").also { it.writeBytes(bytes) }
            }
            persistCompanionDraft(s,CompanionAudioDraft(purpose,file,mime))
        }
    }
    fun clearCompanionAudio() { val s=session?:return;if(!state.value.recording) operation(s) {persistCompanionDraft(s,null)} }
    fun uploadCompanionAudio() {
        val s = session ?: return; val draft = state.value.companionAudio ?: return; val subject = state.value.subject
        operation(s) {
            val result = io { client.uploadCompanionAudio(s,subject,draft.purpose,draft.file,draft.mime,draft.key) }
            persistCompanionDraft(s,draft.copy(remote = result));state.value = state.value.copy(notice = "声音已保存，可以开始转写。")
        }
    }
    fun transcribeCompanionAudio(confirmed: Boolean) {
        val s = session ?: return; val draft = state.value.companionAudio ?: return
        val id = draft.remote?.text("audio_id")?.takeIf { it.isNotBlank() } ?: return
        if(!confirmed) { report("请先同意这段声音的云端转写。"); return }
        val path = root()+"/companion/audio/"+segment(id)
        operation(s) {
            val current = io { client.json(s,path) }
            val policy = current.text("cloud_asr_policy").ifBlank { state.value.asrCapabilities?.text("cloud_asr_policy").orEmpty() }
            check(policy.isNotBlank()) { "服务尚未提供云端转写许可版本。" }
            val result = io { client.json(s,"$path/transcribe","POST",JSONObject().put("cloud_asr_policy",policy)) }
            persistCompanionDraft(s,draft.copy(remote = result))
            check(result.text("status")!="failed") {result.text("error").ifBlank {"这次转写未完成，请稍后重试。"}}
        }
    }
    fun reviewCompanionAudio(text: String) {
        val s = session ?: return; val draft = state.value.companionAudio ?: return; val remote = draft.remote ?: return
        val path = root()+"/companion/audio/"+segment(remote.text("audio_id"))+"/review"
        operation(s) {
            val result = io { client.json(s,path,"PUT",JSONObject().put("revision",remote.optInt("revision")).put("text",text.trim())) }
            persistCompanionDraft(s,draft.copy(remote = result));state.value = state.value.copy(notice = "录音文字已核对。")
        }
    }
    fun createCompanion(kind: String, body: JSONObject, saved: () -> Unit) {
        val s = session ?: return; val path = root()+"/companion/"+kind
        val signature = "$path\n$body"; val key = creationKeys.getOrPut(signature) { java.util.UUID.randomUUID().toString() }
        operation(s) {
            io { client.json(s,path,"POST",JSONObject(body.toString()).put("idempotency_key",key)) }
            creationKeys.remove(signature)
            if(state.value.companionAudio?.purpose == if(kind=="letters") "letter" else "contribution") persistCompanionDraft(s,null)
            refreshNow(s); saved()
        }
    }
    fun openContributionOriginal(id: String) {
        val s=session?:return;val subject=state.value.subject
        operation(s) {
            state.value=state.value.copy(contributionOriginal=null)
            val original=io {client.companionOriginal(s,subject,id)}
            check(original.text("status")!="withdrawn") {"这段补记已撤回。"}
            state.value=state.value.copy(contributionOriginal=original)
        }
    }
    fun closeContributionOriginal() {state.value=state.value.copy(contributionOriginal=null)}
    fun enrollSyntheticVoice(confirmed: Boolean) {
        val s=session?:return; val path=subjectRoot(); val subject=state.value.subject
        if(!confirmed||!state.value.owner) {report("请先单独同意分身声音。");return}
        operation(s) {
            val consent=io {client.consent(s,subject,"VOICE")}
            io {client.json(s,"$path/voice/profile/synthetic","POST",JSONObject().put("preset","a01").put("voice_consent_id",consent))}
            refreshNow(s)
        }
    }
    fun voiceRecipient(actor: String, enabled: Boolean) {
        val s=session?:return;val path=subjectRoot()
        operation(s) {io {client.json(s,"$path/voice/recipients/${segment(actor)}","PUT",JSONObject().put("enabled",enabled))};refreshNow(s)}
    }
    fun disableVoice() {
        val s=session?:return;val consent=state.value.voiceProfile.text("voice_consent_id")
        if(!state.value.owner||consent.isBlank())return
        operation(s){stopSource();io{client.json(s,"/api/v1/consents/${segment(consent)}/revoke","POST")};refreshNow(s)}
    }
    fun refreshCandidates(cloudConfirmed: Boolean) {
        val s = session ?: return
        if(!state.value.owner || !cloudConfirmed) { report("请先确认将已核对的文字交由云端归纳人物候选。"); return }
        val path = root()
        operation(s) {
            val consent = io { cloudConsent(s) }
            io { client.json(s, "$path/profile-candidates/refresh", "POST", JSONObject().put("cloud_consent_id", consent)) }
            refreshNow(s)
        }
    }
    fun organizeNarrative(cloudConfirmed: Boolean, episodes: List<String>) {
        val s = session ?: return
        if(!state.value.owner || !cloudConfirmed) { report("请确认将已核对的文字交由云端组织故事。"); return }
        val path = root()
        operation(s) {
            val consent = io { cloudConsent(s) }
            io { client.json(s, "$path/narrative/suggest", "POST", JSONObject().put("cloud_consent_id", consent).put("episode_ids",JSONArray(episodes))) }
            refreshNow(s)
        }
    }
    fun playLocal(capture: LocalCapture) {
        stopSource(); audio.play(capture.recording, {}, ::report)
    }
    fun narrativeHistory(id: String, show: (JSONObject) -> Unit) {
        val s=session ?: return
        val path=root()+"/narrative/records/"+segment(id)+"/history"
        operation(s) {
            val history=io { client.json(s,path) }
            gate.requireCurrent(s);show(history)
        }
    }
    fun playSource(episode: String) {
        val subject = state.value.subject
        playRemote(episode) { s -> client.audio(s, subject, episode) }
    }
    fun speakAnswer(answer: JSONObject) {
        val path = subjectRoot(); val id = segment(answer.text("answer_id"))
        playRemote("answer:$id") { s ->
            val result = client.json(s,"$path/twin/answers/$id/speech","POST")
            check(result.text("status") == "ready" && result.text("asset_id").isNotBlank()) { "声音还没有准备好，请稍后再试。" }
            client.media(s,"$path/voice/assets/${segment(result.text("asset_id"))}/audio")
        }
    }
    fun openSavedAnswer(id: String) {
        val s=session?:return;val path=subjectRoot()
        operation(s) {
            stopSource();state.value=state.value.copy(answer=null)
            val result=io {client.json(s,"$path/twin/answers/${segment(id)}")}
            state.value=state.value.copy(answer=result)
        }
    }
    fun playSavedSpeech(answerId: String, assetId: String) {
        val path=subjectRoot()
        playRemote("answer:$answerId") {s ->
            client.json(s,"$path/twin/answers/${segment(answerId)}")
            client.media(s,"$path/voice/assets/${segment(assetId)}/audio")
        }
    }
    fun playCompanionAudio(id: String) {
        val path = root()+"/companion/audio/"+segment(id)
        playRemote("companion:$id") { s -> client.media(s,"$path/content") }
    }
    private fun playRemote(episode: String, load: (BackendSession) -> ByteArray) {
        val s = session ?: return
        operation(s) {
            stopSource(); audio.stopPlayback()
            val ticket = playbackGate.begin(s)
            val bytes = io { load(s) }
            // No cache or player may be restored by a download that crossed Home, stop, or identity change.
            playbackGate.publish(ticket) {
                val file = File(sources, "source-${s.epoch}-${ticket.generation}.audio"); file.writeBytes(bytes)
                val next = MediaPlayer(); player = next
                state.value = state.value.copy(player = SourcePlayback(episode = episode, preparing = true))
                next.setOnPreparedListener {
                    if(player !== next || !playbackGate.isCurrent(ticket)) {
                        if(player === next) stopSource() else runCatching { next.release() }
                        return@setOnPreparedListener
                    }
                    next.start(); state.value = state.value.copy(player = SourcePlayback(episode, true, duration = next.duration.toLong()))
                    playerJob = viewModelScope.launch { while(isActive && player === next) {
                        delay(250); runCatching { state.value = state.value.copy(player = state.value.player.copy(position = next.currentPosition.toLong(), playing = next.isPlaying)) }
                    } }
                }
                next.setOnCompletionListener { if(player === next) stopSource() }
                next.setOnErrorListener { _, _, _ ->
                    if(player === next) { stopSource(); report("来源原音播放失败，请重新加载。") }; true
                }
                try { next.setDataSource(file.absolutePath); next.prepareAsync() }
                catch(error: Exception) { stopSource(); throw error }
            }
        }
    }
    fun pauseSource() { player?.pause(); state.value = state.value.copy(player = state.value.player.copy(playing = false)) }
    fun resumeSource() { if(!foreground) return; player?.start(); state.value = state.value.copy(player = state.value.player.copy(playing = true)) }
    fun seekSource(value: Long) { player?.seekTo(value.toInt()); state.value = state.value.copy(player = state.value.player.copy(position = value)) }
    fun stopSource() {
        playbackGate.invalidate()
        playerJob?.cancel(); player?.let { runCatching { it.release() } }; player = null
        sources.listFiles()?.forEach { it.delete() }; state.value = state.value.copy(player = SourcePlayback())
    }
    fun clearSourceCache() {
        stopSource()
        state.value = if(sources.listFiles()?.isNotEmpty() == true) state.value.copy(error = "部分下载缓存未能清理，请稍后重试。")
            else state.value.copy(error = null, notice = "下载缓存已清理；本机原音、登录和云端记忆保留。")
    }
    fun onForeground(value: Boolean) {
        foreground = value
        voiceStartGate.setForeground(value)
        if(!value)callState.value?.pause("已暂停聆听")
        playbackGate.setForeground(value)
        if(!value) { stopSource(); audio.stopPlayback(); if(state.value.companionRecording.isNotBlank()) finishCompanionRecording() else if(state.value.recording) finish() }
        else if(session != null && pendingTransfer == null && !state.value.busy && !state.value.recording) { refreshCaptureFeed(); pumpCaptures() }
    }
    private suspend fun <T> io(block: () -> T): T = withContext(Dispatchers.IO) { block() }
    private fun operation(s: BackendSession, block: suspend () -> Unit) {
        if(state.value.busy) return
        val operationId = beginOperation()
        viewModelScope.launch {
            var completed = false
            try { gate.requireCurrent(s); block(); completed = true }
            catch(error: Exception) {
                if(error is CancellationException) throw error
                if(gate.accepts(s)) {
                    if(error is BackendHttpException && error.status == 401) {
                        if(state.value.recording) {
                            runCatching { val recording = audio.stop()
                                saveCapture(s, activeCapture?.copy(recording = recording) ?: LocalCapture(recording,
                                    "android-${File(recording.audioPath).nameWithoutExtension}", revision = recordTarget)) }
                        }
                        savedSession.clear(); clearIdentity()
                        state.value = state.value.copy(error = "登录已失效，请重新登录。本机原音仍保留。")
                    } else state.value = state.value.copy(error = error.message?.take(500) ?: "操作未完成，原音已保留。")
                }
            } finally { if(gate.accepts(s)) state.value = state.value.copy(busy = false,
                operation = OperationFeedback(operationId, when {
                    state.value.error != null -> ActionPhase.FAILED
                    completed -> ActionPhase.SUCCEEDED
                    else -> ActionPhase.CANCELLED
                })) }
        }
    }
    override fun onCleared() { closeRecorder(); endVoice();gate.clear(); stopSource(); audio.release(); super.onCleared() }
}

internal fun NativeState.playerAccessLost(stories: List<JSONObject>): Boolean =
    player.episode.isNotBlank() && !player.episode.contains(':') &&
        stories.none { it.text("episode_id")==player.episode && !it.optBoolean("unavailable") }

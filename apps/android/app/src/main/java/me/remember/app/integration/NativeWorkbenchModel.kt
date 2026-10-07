package me.remember.app.integration

import android.content.Context
import android.media.MediaPlayer
import android.util.AtomicFile
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.data.repository.AudioRecording
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

data class NativeState(
    val actor: String = "", val actorName: String = "", val spaces: List<JSONObject> = emptyList(),
    val space: JSONObject? = null, val stories: List<JSONObject> = emptyList(), val grants: List<JSONObject> = emptyList(),
    val revisions: List<JSONObject> = emptyList(), val requests: List<JSONObject> = emptyList(),
    val candidates: List<JSONObject> = emptyList(), val candidateJobs: List<JSONObject> = emptyList(),
    val answer: JSONObject? = null, val search: List<JSONObject> = emptyList(),
    val reviewEpisode: String? = null, val reviewText: String = "", val local: List<LocalCapture> = emptyList(),
    val busy: Boolean = false, val error: String? = null, val notice: String = "", val recording: Boolean = false, val paused: Boolean = false,
    val elapsed: Long = 0, val player: SourcePlayback = SourcePlayback(), val dailyReminder: Boolean = false
) {
    val owner get() = space?.text("role") == "owner"
    val subject get() = space?.text("subject_id").orEmpty()
}
data class SourcePlayback(val episode: String = "", val playing: Boolean = false, val preparing: Boolean = false,
    val position: Long = 0, val duration: Long = 0)

/** Tokens stay in memory. Local originals are indexed by authenticated actor and subject. */
class NativeWorkbenchModel(context: Context, val audio: AndroidAudioCaptureService) : ViewModel() {
    private val gate = SessionGate()
    private val playbackGate = SourcePlaybackGate(gate)
    private val client = BackendClient(gate)
    private val reminders = LocalDailyReminder(context)
    private var session: BackendSession? = null
    private val state = MutableStateFlow(NativeState())
    val ui = state.asStateFlow()
    private val ledger = AtomicFile(File(context.filesDir, "native-captures.json"))
    private val sources = File(context.cacheDir, "native-source-audio").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
    private var player: MediaPlayer? = null
    private var playerJob: Job? = null
    private var recordTarget: RevisionTarget? = null
    private var activeCapture: LocalCapture? = null
    private var ticker: Job? = null
    private var foreground = true
    private var polling: Job? = null
    init { reminders.disable() }

    fun report(message: String) { state.value = state.value.copy(error = message) }
    fun connect(server: String, token: String) {
        if(state.value.busy || state.value.recording) return
        clearIdentity()
        val next = runCatching { gate.connect(server, token) }.getOrElse { report(it.message ?: "服务地址无效。"); return }
        session = next
        operation(next) {
            val result = io { client.json(next, "/api/v1/workbench/spaces") }
            state.value = state.value.copy(actor = result.text("actor_id"), actorName = result.text("display_name"), spaces = result.rows())
            state.value = state.value.copy(space = result.rows().firstOrNull())
            refreshNow(next)
            polling?.cancel()
            polling = viewModelScope.launch {
                while(isActive && gate.accepts(next)) {
                    delay(8_000)
                    if(foreground && !state.value.busy && !state.value.recording && state.value.subject.isNotBlank()) refresh()
                }
            }
        }
    }
    fun selectSpace(space: JSONObject) {
        if(state.value.busy || state.value.recording) return
        stopSource(); audio.stopPlayback(); polling?.cancel(); reminders.disable()
        session = gate.advance()
        state.value = NativeState(actor = state.value.actor, actorName = state.value.actorName, spaces = state.value.spaces, space = space)
        refresh()
        val next = session ?: return
        polling = viewModelScope.launch { while(isActive && gate.accepts(next)) {
            delay(8_000); if(foreground && !state.value.busy && !state.value.recording) refresh()
        } }
    }
    fun logout() {
        if(state.value.recording) { finish { clearIdentity() } } else clearIdentity()
    }
    private fun clearIdentity() {
        reminders.disable()
        gate.clear(); session = null; polling?.cancel(); ticker?.cancel(); recordTarget = null; activeCapture = null
        stopSource(); audio.stopPlayback(); state.value = NativeState()
    }
    private fun root() = "${BackendClient.WORKBENCH}/${segment(state.value.subject)}"
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
    private fun localCaptures(s: BackendSession): List<LocalCapture> {
        val links = records().optJSONArray(scopeKey(s)) ?: JSONArray()
        val available = audio.recordings().associateBy { it.audioPath }
        return (0 until links.length()).mapNotNull { i ->
            val row = links.getJSONObject(i)
            available[row.text("path")]?.let { recording -> LocalCapture(recording, row.text("key"), row.text("episode"),
                row.optJSONObject("revision")?.let { RevisionTarget(it.text("memory"), it.text("kind"), it.text("time")) }, row.optBoolean("linked")) }
        }.reversed()
    }
    private fun saveCapture(s: BackendSession, capture: LocalCapture) {
        gate.requireCurrent(s)
        val all = records(); val key = scopeKey(s); val values = all.optJSONArray(key) ?: JSONArray()
        val row = JSONObject().put("path", capture.recording.audioPath).put("key", capture.key).put("episode", capture.episode).put("linked", capture.linked)
        capture.revision?.let { row.put("revision", JSONObject().put("memory", it.memory).put("kind", it.kind).put("time", it.time)) }
        val index = (0 until values.length()).firstOrNull { values.getJSONObject(it).text("path") == capture.recording.audioPath }
        if(index == null) values.put(row) else values.put(index, row)
        all.put(key, values); writeRecords(all)
        state.value = state.value.copy(local = localCaptures(s))
    }
    fun refresh() { val s = session ?: return; operation(s) {
        try { refreshNow(s) } catch(error: Exception) {
            if(gate.accepts(s)) {
                stopSource(); audio.stopPlayback()
                state.value = state.value.copy(stories = emptyList(), grants = emptyList(), revisions = emptyList(),
                    requests = emptyList(), candidates = emptyList(), candidateJobs = emptyList(), answer = null, search = emptyList(), reviewEpisode = null)
            }
            throw error
        }
    } }
    private suspend fun refreshNow(s: BackendSession) {
        if(state.value.subject.isBlank()) return
        val path = root()
        val stories = io { client.json(s, "$path/stories") }
        // Authoritative role comes from server, never from locally entered role labels.
        val grants = io { client.json(s, "$path/grants") }
        val requests = io { client.json(s, "$path/requests") }
        val owner = stories.text("role") == "owner"
        val revisions = if(owner) io { client.json(s, "$path/revisions").rows() } else emptyList()
        val candidates = if(owner) io { client.json(s, "$path/profile-candidates") } else JSONObject()
        gate.requireCurrent(s)
        val changed = state.value.stories.map { it.toString() } != stories.rows().map { it.toString() } ||
            state.value.grants.map { it.toString() } != grants.rows().map { it.toString() } ||
            state.value.candidates.map { it.toString() } != candidates.rows().map { it.toString() }
        if(changed) { stopSource(); audio.stopPlayback() }
        state.value = state.value.copy(space = state.value.space?.put("role", stories.text("role")), stories = stories.rows(),
            grants = grants.rows(), requests = requests.rows(), revisions = revisions, candidates = candidates.rows(),
            candidateJobs = candidates.rows("jobs"), local = if(owner) localCaptures(s) else emptyList(),
            answer = if(changed) null else state.value.answer, search = if(changed) emptyList() else state.value.search)
    }
    fun start(revision: RevisionTarget?) {
        val s = session ?: return
        if(!state.value.owner || state.value.busy || state.value.recording) return
        operation(s) {
            stopSource()
            val started = audio.start()
            recordTarget = revision
            val capture = LocalCapture(started, "android-${File(started.audioPath).nameWithoutExtension}", revision = revision)
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
            state.value = state.value.copy(notice = "原音已保存到本机。请明确同意录音上传后继续。")
            after?.invoke()
        }
    }
    fun upload(capture: LocalCapture, recordingConsent: Boolean) {
        val s = session ?: return
        if(!recordingConsent) { report("请先确认将这段原音上传到共享后端并转写；原音仍保留本机。"); return }
        if(!state.value.owner) return
        val subject = state.value.subject; val path = root()
        operation(s) {
            val consent = io { client.consent(s, subject, "RECORDING") }
            submitCapture(capture,
                upload = { io { client.upload(s, subject, consent, capture.recording, capture.key) } },
                persist = { saveCapture(s, it) },
                link = { episode, revision ->
                io { client.json(s, "$path/revisions", "POST", JSONObject().put("episode_id", episode)
                    .put("target_memory_id", revision.memory).put("kind", revision.kind)
                    .put("time_text", revision.time.ifBlank { null })) }
            })
            state.value = state.value.copy(notice = "上传已接收，原音留在本机。等待转写后核对文字。")
            refreshNow(s)
        }
    }
    fun review(episode: String) {
        val s = session ?: return
        if(state.value.local.any { it.episode == episode && it.blocksReview }) { report("请先在本机录音列表重试上传，完成修订关联后再核对文字。"); return }
        operation(s) {
            val result = io { client.json(s, "/api/v1/episodes/${segment(episode)}/transcript-review") }
            check(result.text("state") == "reviewing") { "转写尚未完成或已经提交，请刷新后查看。" }
            state.value = state.value.copy(reviewEpisode = episode, reviewText = result.text("transcript"))
        }
    }
    fun closeReview() { state.value = state.value.copy(reviewEpisode = null, reviewText = "") }
    fun editReview(episode: String, text: String) {
        if(state.value.reviewEpisode == episode) state.value = state.value.copy(reviewText = text)
    }
    fun confirmReview(text: String, cloudConfirmed: Boolean) {
        val s = session ?: return; val episode = state.value.reviewEpisode ?: return
        if(!cloudConfirmed) { report("请确认将核对后的文字交由服务器整理；其配置的云端模型会收到文字。"); return }
        if(text.isBlank()) { report("核对文字不能为空。"); return }
        operation(s) {
            io { client.json(s, "/api/v1/episodes/${segment(episode)}/transcript-review", "PATCH", JSONObject().put("transcript", text.trim())) }
            closeReview(); state.value = state.value.copy(notice = "文字已核对提交，原音与机器转写保留。")
            refreshNow(s)
        }
    }
    fun mutation(suffix: String, method: String, body: JSONObject? = null, subjectApi: Boolean = false) {
        val s = session ?: return; val path = if(subjectApi) subjectRoot() else root()
        operation(s) {
            stopSource(); audio.stopPlayback(); state.value = state.value.copy(answer = null, search = emptyList())
            io { client.json(s, path + suffix, method, body) }; refreshNow(s)
        }
    }
    fun retry(episode: String, emptyResult: Boolean = false) {
        val s = session ?: return
        val action = if(emptyResult) "reextract-empty" else "retry"
        operation(s) { io { client.json(s, "/api/v1/episodes/${segment(episode)}/$action", "POST") }; refreshNow(s) }
    }
    private fun cloudConsent(s: BackendSession): String {
        if(state.value.owner) return client.consent(s, state.value.subject, "CLOUD_TWIN")
        return state.value.grants.firstOrNull { it.optBoolean("cloud_processing_allowed") }?.text("grant_id")
            ?: throw IllegalStateException("记录者尚未允许共享故事参与云端问答。")
    }
    fun ask(question: String, cloudConfirmed: Boolean) {
        val s = session ?: return
        if(!cloudConfirmed || question.isBlank()) { report("请填写问题并明确同意本次云端文字处理。"); return }
        val path = subjectRoot()
        operation(s) {
            state.value = state.value.copy(answer = null)
            val consent = io { cloudConsent(s) }
            val answer = io { client.json(s, "$path/twin/answers", "POST", JSONObject().put("question", question.trim()).put("cloud_consent_id", consent)) }
            state.value = state.value.copy(answer = answer)
        }
    }
    fun search(query: String) {
        val s = session ?: return; val path = subjectRoot()
        operation(s) {
            val result = io { client.json(s, "$path/memory-search?q=${segment(query)}") }
            state.value = state.value.copy(search = result.rows())
        }
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
    fun playLocal(capture: LocalCapture) {
        stopSource(); audio.play(capture.recording, {}, ::report)
    }
    fun playSource(episode: String) {
        val s = session ?: return; val subject = state.value.subject
        operation(s) {
            stopSource(); audio.stopPlayback()
            val ticket = playbackGate.begin(s)
            val bytes = io { client.audio(s, subject, episode) }
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
    fun onForeground(value: Boolean) {
        foreground = value
        playbackGate.setForeground(value)
        if(!value) { stopSource(); audio.stopPlayback(); if(state.value.recording) finish() }
        else if(session != null && !state.value.busy && !state.value.recording) refresh()
    }
    private suspend fun <T> io(block: () -> T): T = withContext(Dispatchers.IO) { block() }
    private fun operation(s: BackendSession, block: suspend () -> Unit) {
        if(state.value.busy) return
        state.value = state.value.copy(busy = true, error = null)
        viewModelScope.launch {
            try { gate.requireCurrent(s); block() }
            catch(error: Exception) {
                if(error is CancellationException) throw error
                if(gate.accepts(s)) state.value = state.value.copy(error = error.message?.take(500) ?: "操作未完成，原音已保留。")
            } finally { if(gate.accepts(s)) state.value = state.value.copy(busy = false) }
        }
    }
    override fun onCleared() { gate.clear(); stopSource(); audio.release(); super.onCleared() }
}

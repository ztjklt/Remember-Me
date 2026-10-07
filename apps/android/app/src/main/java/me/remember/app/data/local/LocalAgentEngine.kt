package me.remember.app.data.local

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import me.remember.app.data.repository.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/** Durable single-Agent journal. One app-owned instance serializes local writes. */
class LocalAgentEngine(private val store: LocalStateStore, private val client: LocalModelClient,
    private val settings: () -> LocalModelSettings?) : AgentGateway {
    private val mutex = Mutex()
    private val inference = LocalInference(client)
    @Volatile private var state = store.read() ?: JSONObject().put("version", 1).put("subject_id", newId("local_"))
        .put("granted", false).put("revision", 0).put("model_version", "local-unconfigured")
        .put("materials", JSONArray()).put("traits", JSONArray()).put("history", JSONArray())
        .put("calibrations", JSONArray()).put("episodes", JSONArray()).put("withdrawn_evidence", JSONArray()).also(store::write)

    init { check(state.getInt("version") == 1) { "本地数据版本不兼容。" } }
    fun connection() = BackendConnection("local://device", "local-session", state.getString("subject_id"), "local-recording-consent", true)
    fun granted() = state.getBoolean("granted")
    fun pending(): JSONObject? = state.optJSONObject("job")?.copyJson()
    fun latestCalibration(): String? = state.getJSONArray("calibrations").objects().lastOrNull { it.getString("state") != "INVALIDATED" }?.getString("calibration_id")
    private fun persist(next: JSONObject) { store.write(next); state = next.copyJson() }
    private fun materials() = JSONArray(state.getJSONArray("materials").objects().filter { it.getString("evidence_id") !in withdrawn() })
    private fun withdrawn() = state.getJSONArray("withdrawn_evidence").strings().toSet()
    private fun model() = JSONObject().put("subject_id", state.getString("subject_id")).put("revision", state.getInt("revision"))
        .put("model_version", state.getString("model_version")).put("schema_version", "agent-loop-v0.2-experimental")
        .put("traits", JSONArray(state.getJSONArray("traits").objects().filter { t -> t.getJSONArray("evidence_ids").strings().none { it in withdrawn() } }))

    override suspend fun request(connection: BackendConnection, path: String, method: String, body: JSONObject?): JSONObject = withContext(Dispatchers.IO) {
        mutex.withLock {
            check(connection.subjectId == state.getString("subject_id")) { "本地 Subject 不匹配。" }
            if (path == "/grant") {
                val next = state.copyJson()
                if (method == "DELETE") next.put("granted", false).put("revoked_at", now())
                else {
                    check(body?.optBoolean("cloud_twin_consent") == true && body.optBoolean("subject_single_speaker")) { "请确认云端处理同意。" }
                    next.put("granted", true).put("consented_at", now())
                }
                persist(next)
                return@withLock JSONObject()
            }
            check(granted()) { "请先在模型设置中同意云端处理。" }
            when {
                path == "/model" -> model()
                path == "/evidence" -> JSONObject().put("materials", materials())
                path.startsWith("/evidence/") -> materials().objects().first { it.getString("evidence_id") == path.substringAfterLast('/') }
                path == "/calibrations" && method == "POST" -> {
                    val question = body!!.getString("question").trim()
                    require(question.length in 1..4000) { "问题为空或过长。" }
                    begin(JSONObject().put("kind", "ASK").put("question", question).put("id", newId("cal_")))
                    execute()
                }
                path.endsWith("/submit") -> {
                    val id = path.split('/')[2]
                    val cal = calibration(id)
                    if (cal.getString("state") == "COMPLETED") return@withLock cal.copyJson()
                    check(cal.getString("state") == "LOCKED" && body!!.getInt("expected_revision") == state.getInt("revision") &&
                        cal.getJSONObject("locked_answer").getInt("revision") == state.getInt("revision")) { "理解已变化，请重新提问。" }
                    val human = body!!.getString("human_answer").trim()
                    require(human.length in 1..8000) { "校正为空或过长。" }
                    begin(JSONObject().put("kind", "CORRECT").put("id", id).put("human_answer", human)
                        .put("evidence", evidence(newId("cev_"), human, "CALIBRATION", null, cal.getString("question"))
                            .put("source_ref", "calibration:$id")))
                    execute()
                }
                path.startsWith("/calibrations/") -> calibration(path.substringAfterLast('/'))
                path.startsWith("/episodes/") && method == "DELETE" -> withdraw(path.split('/')[2])
                else -> error("此功能尚未在手机本地模式开放。")
            }.copyJson()
        }
    }

    suspend fun capture(recording: AudioRecording) = withContext(Dispatchers.IO) { mutex.withLock {
        check(granted()) { "请先同意云端处理。" }
        val id = "ep_" + digest(recording.audioPath + recording.createdAt)
        val existing = state.getJSONArray("episodes").objects().firstOrNull { it.getString("id") == id }
        if (existing != null) { check(!existing.optBoolean("withdrawn")) { "这段材料已撤除，请重新录音。" }; return@withLock }
        require(File(recording.audioPath).isFile) { "原始录音文件不存在。" }
        begin(JSONObject().put("kind", "CAPTURE").put("id", id).put("audio_path", recording.audioPath)
            .put("duration", recording.durationMillis).put("mime", recording.mimeType).put("bytes", recording.byteSize)
            .put("sample_rate", recording.sampleRate).put("channels", recording.channelCount).put("recorded_at", recording.createdAt))
        execute()
    } }

    suspend fun retry() = withContext(Dispatchers.IO) { mutex.withLock { check(granted()); if (pending() != null) execute() } }
    suspend fun cancelPending() = withContext(Dispatchers.IO) { mutex.withLock {
        val next = state.copyJson()
        next.optJSONObject("job")?.let { next.optJSONArray("cancelled_jobs")?.put(it)
            ?: next.put("cancelled_jobs", JSONArray().put(it)) }
        next.remove("job")
        persist(next)
    } }
    private fun begin(job: JSONObject) {
        check(pending() == null) { "还有待完成任务，请先继续或取消该任务。" }
        persist(state.copyJson().put("job", job.put("started_at", now()).put("attempts", 0)))
    }
    private suspend fun execute(): JSONObject {
        val config = checkNotNull(settings()) { "请先保存语音和文字模型配置。" }.also { it.validate() }
        var job = checkNotNull(pending())
        job.put("attempts", job.getInt("attempts") + 1).put("status", "RUNNING").remove("error")
        persist(state.copyJson().put("job", job))
        try {
            if (job.getString("kind") == "ASK") {
                val answer = inference.answer(job.getString("question"), model(), materials(), config.language)
                val cal = JSONObject().put("calibration_id", job.getString("id")).put("question", job.getString("question"))
                    .put("locked_answer", answer).put("locked_at", now()).put("lock_digest", digest(answer.toString()))
                    .put("state", "LOCKED").put("resulting_revision", JSONObject.NULL)
                persist(state.copyJson().apply { getJSONArray("calibrations").put(cal); remove("job") })
                return cal
            }
            if (job.getString("kind") == "CAPTURE" && !job.has("evidence")) {
                val recording = AudioRecording(job.getString("audio_path"), job.getLong("duration"), job.getString("mime"),
                    job.getLong("bytes"), job.getInt("sample_rate"), job.getInt("channels"), job.getString("recorded_at"))
                val transcript = client.transcribe(recording, config)
                job.put("evidence", evidence("ev_" + job.getString("id"), transcript, "SUBJECT", job.getString("id"), ""))
                    .put("asr_model", config.speech.model)
                persist(state.copyJson().put("job", job)) // Checkpoint ASR before the language request.
            }
            val input = materials().put(job.getJSONObject("evidence"))
            val traits = inference.understand(model(), input, config.language)
            val next = state.copyJson()
            next.getJSONArray("history").put(model())
            next.getJSONArray("materials").put(job.getJSONObject("evidence"))
            next.put("traits", traits).put("revision", state.getInt("revision") + 1).put("model_version", config.language.model).remove("job")
            var result = JSONObject()
            if (job.getString("kind") == "CORRECT") {
                result = next.getJSONArray("calibrations").objects().first { it.getString("calibration_id") == job.getString("id") }
                result.put("state", "COMPLETED").put("resulting_revision", next.getInt("revision")).put("human_answer", job.getString("human_answer"))
            } else next.getJSONArray("episodes").put(job.copyJson().apply { remove("evidence") })
            persist(next)
            return result
        } catch (e: Exception) {
            job = checkNotNull(pending())
            persist(state.copyJson().put("job", job.put("status", "PAUSED").put("error", "任务未完成，可继续；已保存的材料保留。")))
            throw e
        }
    }
    private fun calibration(id: String) = state.getJSONArray("calibrations").objects().first {
        it.getString("calibration_id") == id && it.getString("state") != "INVALIDATED"
    }
    private fun withdraw(id: String): JSONObject {
        check(pending() == null) { "请先完成或取消待处理任务。" }
        val next = state.copyJson()
        val removed = withdrawn().toMutableSet()
        next.getJSONArray("materials").objects().filter { it.optString("episode_id") == id }.forEach { removed.add(it.getString("evidence_id")) }
        // Propagate only along provenance edges. Keep unrelated records and revision history.
        var changed: Boolean
        do {
            changed = false
            next.getJSONArray("calibrations").objects().forEach { cal ->
                if (cal.getJSONObject("locked_answer").getJSONArray("evidence_ids").strings().any { it in removed }) {
                    cal.put("state", "INVALIDATED")
                    next.getJSONArray("materials").objects().filter { it.getString("source_ref") == "calibration:${cal.getString("calibration_id")}" }
                        .forEach { if (removed.add(it.getString("evidence_id"))) changed = true }
                }
            }
        } while (changed)
        next.put("withdrawn_evidence", JSONArray(removed)).put("revision", next.getInt("revision") + 1)
        next.getJSONArray("episodes").objects().firstOrNull { it.getString("id") == id }?.put("withdrawn", true)
        persist(next)
        return model()
    }
    private fun evidence(id: String, text: String, source: String, episode: String?, context: String) = JSONObject()
        .put("evidence_id", id).put("excerpt", text).put("source_type", source).put("episode_id", episode ?: JSONObject.NULL)
        .put("source_ref", if (episode != null) "episode:$episode" else "calibration:$id")
        .put("context", context).put("observed_at", now()).put("speaker_authority", "SELF_ATTESTED")
    private fun digest(text: String) = MessageDigest.getInstance("SHA-256").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }
}

package me.remember.app.data.local

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map
import me.remember.app.model.Loadable
import me.remember.app.model.Memory
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
    private val settings: () -> LocalModelSettings?) : AgentGateway, MemoryRepository {
    private val changes = MutableStateFlow(0L)
    private val mutex = Mutex()
    private val inference = LocalInference(client)
    private val psychology = PsychologicalLearner(client)
    private val observer = MemoryObservationExtractor(client)
    private fun emptyJournal() = JSONObject().put("version", 1).put("subject_id", newId("local_"))
        .put("granted", false).put("revision", 0).put("model_version", "local-unconfigured")
        .put("materials", JSONArray()).put("traits", JSONArray()).put("history", JSONArray())
        .put("calibrations", JSONArray()).put("episodes", JSONArray()).put("withdrawn_evidence", JSONArray())

    @Volatile private var state = store.read() ?: emptyJournal().also(store::write)

    init {
        if (state.optInt("version") != 1) {
            store.preserve(state)
            throw LocalRecoveryRequired("本地数据版本不兼容，原始日志已保留。请导出可读原文并升级应用；不要清除应用数据。")
        }
    }
    fun connection() = BackendConnection("local://device", "local-session", state.getString("subject_id"), "local-recording-consent", true)
    fun granted() = state.getBoolean("granted")
    fun dimensions(): Set<String> = state.optJSONArray("enabled_dimensions")?.strings()?.toSet()
        ?: MemoryDimensionRegistry.dimensions.map { it.id }.toSet()
    suspend fun configureDimensions(enabled: Set<String>) = withContext(Dispatchers.IO) { mutex.withLock {
        require(enabled.all { id -> MemoryDimensionRegistry.dimensions.any { it.id == id } })
        check(pending() == null) { "请先完成或取消待处理任务。" }
        persist(state.copyJson().put("enabled_dimensions", JSONArray(enabled)))
    } }
    suspend fun portrait(): LocalPortrait? = withContext(Dispatchers.IO) { mutex.withLock {
        if (granted()) projectPortrait(state) else null
    } }
    fun pending(): JSONObject? = state.optJSONObject("job")?.copyJson()
    fun latestCalibration(): String? = state.getJSONArray("calibrations").objects().lastOrNull { it.getString("state") != "INVALIDATED" }?.getString("calibration_id")
    private fun persist(next: JSONObject) { store.write(next); state = next.copyJson(); changes.value++ }
    private fun materials() = JSONArray(state.getJSONArray("materials").objects().filter { it.getString("evidence_id") !in withdrawn() })
    private fun withdrawn() = state.getJSONArray("withdrawn_evidence").strings().toSet()
    private fun activeHabits() = JSONArray(state.optJSONArray("habits")?.objects().orEmpty().filter { h ->
        val allowed = materials().objects().map { it.getString("evidence_id") }.toSet()
        h.getJSONArray("evidence_ids").strings().all(allowed::contains)
    })
    private fun model() = JSONObject().put("subject_id", state.getString("subject_id")).put("revision", state.getInt("revision"))
        .put("memory_revision", state.optInt("memory_revision"))
        .put("model_version", state.getString("model_version")).put("schema_version", "agent-loop-v0.2-experimental")
        .put("traits", JSONArray(state.getJSONArray("traits").objects().filter { t -> t.getJSONArray("evidence_ids").strings().none { it in withdrawn() } }))

    fun recordings(saved: List<AudioRecording>): List<LocalRecording> {
        val episodes = state.getJSONArray("episodes").objects()
        val known = episodes.map { job -> AudioRecording(job.getString("audio_path"), job.getLong("duration"), job.getString("mime"),
            job.getLong("bytes"), job.getInt("sample_rate"), job.getInt("channels"), job.getString("recorded_at")) }
        return (known + saved).distinctBy { it.audioPath }.sortedByDescending { it.createdAt }.map { recording ->
            val episode = episodes.firstOrNull { it.getString("audio_path") == recording.audioPath }
            val status = when { episode?.optBoolean("deleted") == true -> "已删除"; episode?.optBoolean("delete_pending") == true -> "文件清理待重试"
                episode?.optBoolean("withdrawn") == true -> "已撤除"; episode?.optString("understanding_status") == "PENDING" -> "待理解"; episode != null -> "已处理"; else -> "未处理" }
            val excerpt = if (status in setOf("已删除", "文件清理待重试")) "" else state.getJSONArray("materials").objects()
                .firstOrNull { it.optString("episode_id") == episode?.getString("id") }?.optString("excerpt").orEmpty()
            LocalRecording(recording, excerpt, status)
        }
    }
    fun versions() = state.getJSONArray("history").objects().map { old -> old.copyJson().apply {
        put("traits", JSONArray(old.getJSONArray("traits").objects().filter { t -> t.getJSONArray("evidence_ids").strings().none { it in withdrawn() } }))
    } } + model()
    suspend fun deleteRecording(recording: AudioRecording, deleteFiles: () -> Unit) = withContext(Dispatchers.IO) { mutex.withLock {
        check(pending() == null || pending()?.optString("kind") == "CAPTURE") { "请先继续或取消待处理问答。" }
        val id = state.getJSONArray("episodes").objects().firstOrNull { it.getString("audio_path") == recording.audioPath }?.getString("id")
            ?: pending()?.takeIf { it.optString("kind") == "CAPTURE" && it.optString("audio_path") == recording.audioPath }?.getString("id")
            ?: "ep_" + digest(recording.audioPath + recording.createdAt)
        val next = eraseRecording(state, id)
        if (next.optJSONObject("job")?.optString("id") == id) next.remove("job")
        val episode = next.getJSONArray("episodes").objects().firstOrNull { it.getString("id") == id }
            ?: JSONObject().put("id", id).put("audio_path", recording.audioPath).put("duration", recording.durationMillis)
                .put("mime", recording.mimeType).put("bytes", recording.byteSize).put("sample_rate", recording.sampleRate)
                .put("channels", recording.channelCount).put("recorded_at", recording.createdAt).also { next.getJSONArray("episodes").put(it) }
        episode.put("withdrawn", true).put("delete_pending", true)
        persist(next) // Fail closed before touching files; an interrupted cleanup is visible and retryable.
        deleteFiles()
        episode.put("delete_pending", false).put("deleted", true).put("deleted_at", now())
        persist(next)
    } }
    suspend fun reset(cleanup: () -> Unit) = withContext(Dispatchers.IO) { mutex.withLock {
        persist(state.copyJson().put("granted", false))
        cleanup()
        persist(emptyJournal())
    } }

    override fun memories() = changes.map {
        if (!granted()) Loadable.Empty else {
            val episodes = state.getJSONArray("episodes").objects().associateBy { it.getString("id") }
            val entries = materials().objects().filter { it.getString("source_type") == "SUBJECT" }.map { m ->
                val episode = episodes[m.optString("episode_id")]
                Memory(m.getString("evidence_id"), episode?.optString("recorded_at").orEmpty(), "", m.getString("excerpt"),
                    emptyList(), listOf("原始转写"), "${(episode?.optLong("duration") ?: 0) / 1000} 秒",
                    episodeId = m.getString("episode_id"), sourceType = "SUBJECT", evidenceIds = listOf(m.getString("evidence_id")),
                    hasPlayableAudio = false)
            }.reversed()
            if (entries.isEmpty()) Loadable.Empty else Loadable.Content(entries)
        }
    }
    override suspend fun history(connection: BackendConnection) = withContext(Dispatchers.IO) { mutex.withLock {
        check(granted() && connection.subjectId == state.getString("subject_id"))
        JSONArray(state.getJSONArray("calibrations").objects().map(::calibrationView))
    } }
    private fun calibrationView(record: JSONObject): JSONObject = record.copyJson().apply {
        if (getString("state") == "INVALIDATED") {
            remove("human_answer")
            getJSONObject("locked_answer").put("answer", "原始材料已撤除，此回答不再可用。")
                .put("evidence", JSONArray()).put("evidence_ids", JSONArray()).put("response_type", "INSUFFICIENT")
        }
    }

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
                path.startsWith("/evidence/") -> materials().objects().flatMap { listOf(it) + evidenceSpans(it) }
                    .first { it.getString("evidence_id") == path.substringAfterLast('/') }
                path == "/calibrations" && method == "POST" -> {
                    val question = body!!.getString("question").trim()
                    require(question.length in 1..4000) { "问题为空或过长。" }
                    val job = pending()
                    if (job != null && job.optString("kind") == "CAPTURE" && job.has("evidence")) {
                        // Read-only answering remains available while a derived portrait awaits retry.
                        lockAnswer(question, newId("cal_"), checkNotNull(settings()).language)
                    } else {
                        begin(JSONObject().put("kind", "ASK").put("question", question).put("id", newId("cal_")))
                        execute()
                    }
                }
                path.endsWith("/submit") -> {
                    val id = path.split('/')[2]
                    val cal = calibration(id)
                    if (cal.getString("state") == "COMPLETED") return@withLock cal.copyJson()
                    check(cal.getString("state") == "LOCKED" && body!!.getInt("expected_revision") == state.getInt("revision") &&
                        cal.getJSONObject("locked_answer").getInt("revision") == state.getInt("revision")) { "理解已变化，请重新提问。" }
                    check(cal.getJSONObject("locked_answer").optInt("memory_revision") == state.optInt("memory_revision")) { "材料已变化，请重新提问。" }
                    val human = body!!.getString("human_answer").trim()
                    require(human.length in 1..8000) { "校正为空或过长。" }
                    begin(JSONObject().put("kind", "CORRECT").put("id", id).put("human_answer", human)
                        .put("evidence", evidence(newId("cev_"), human, "CALIBRATION", null, cal.getString("question"))
                            .put("source_ref", "calibration:$id").put("related_evidence_ids", JSONArray(answerRoots(cal.getJSONObject("locked_answer"))))))
                    execute()
                }
                path.startsWith("/calibrations/") -> calibrationView(calibration(path.substringAfterLast('/')))
                path.startsWith("/episodes/") && method == "DELETE" -> withdraw(path.split('/')[2])
                else -> error("此功能尚未在手机本地模式开放。")
            }.copyJson()
        }
    }

    suspend fun capture(recording: AudioRecording) = withContext(Dispatchers.IO) { mutex.withLock {
        check(granted()) { "请先同意云端处理。" }
        val id = "ep_" + digest(recording.audioPath + recording.createdAt)
        val existing = state.getJSONArray("episodes").objects().firstOrNull { it.getString("id") == id }
        if (existing != null) {
            check(!existing.optBoolean("withdrawn")) { "这段材料已撤除，请重新录音。" }
            if (existing.optString("understanding_status") != "PENDING" && existing.optString("observation_version") == MemoryDimensionRegistry.version) return@withLock
            val saved = state.getJSONArray("materials").objects().first { it.optString("episode_id") == id }
            begin(existing.copyJson().put("kind", "CAPTURE").put("evidence", saved))
            execute(); return@withLock
        }
        require(File(recording.audioPath).isFile) { "原始录音文件不存在。" }
        begin(JSONObject().put("kind", "CAPTURE").put("id", id).put("audio_path", recording.audioPath)
            .put("duration", recording.durationMillis).put("mime", recording.mimeType).put("bytes", recording.byteSize)
            .put("sample_rate", recording.sampleRate).put("channels", recording.channelCount).put("recorded_at", recording.createdAt))
        execute()
    } }

    suspend fun retry() = withContext(Dispatchers.IO) { mutex.withLock { check(granted()); if (pending() != null) execute() } }
    suspend fun cancelPending() = withContext(Dispatchers.IO) { mutex.withLock {
        val next = state.copyJson()
        next.optJSONObject("job")?.let { job ->
            if (job.optString("kind") == "CAPTURE" && job.has("evidence")) {
                publishMaterial(next, job)
                publishEpisode(next, job, "PENDING")
            } else {
                job.remove("traits"); job.remove("habits"); job.remove("observations")
                next.optJSONArray("cancelled_jobs")?.put(job) ?: next.put("cancelled_jobs", JSONArray().put(job))
            }
        }
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
                val cal = lockAnswer(job.getString("question"), job.getString("id"), config.language)
                persist(state.copyJson().apply { remove("job") })
                return cal
            }
            if (job.getString("kind") == "CAPTURE" && !job.has("evidence")) {
                val recording = AudioRecording(job.getString("audio_path"), job.getLong("duration"), job.getString("mime"),
                    job.getLong("bytes"), job.getInt("sample_rate"), job.getInt("channels"), job.getString("recorded_at"))
                val transcript = client.transcribe(recording, config)
                job.put("evidence", evidence("ev_" + job.getString("id"), transcript, "SUBJECT", job.getString("id"), ""))
                    .put("asr_model", config.speech.model)
                job.getJSONObject("evidence").put("observed_at", job.getString("recorded_at"))
                persist(state.copyJson().put("job", job)) // Checkpoint ASR before the language request.
            }
            // Raw evidence is committed independently of all derived model stages.
            persist(state.copyJson().apply {
                publishMaterial(this, job)
                if (job.getString("kind") == "CAPTURE") publishEpisode(this, job, "PENDING")
            })
            val source = job.getJSONObject("evidence")
            val full = source.getString("excerpt")
            val enabled = dimensions()
            while (job.optInt("observation_offset") < full.length) {
                val offset = job.optInt("observation_offset")
                val batch = observer.extract(source, offset, config.language, enabled)
                val accumulated = job.optJSONArray("observations") ?: JSONArray()
                batch.objects().forEach(accumulated::put)
                job.put("observations", accumulated).put("observation_offset", offset + sourceChunk(full, offset).length)
                persist(state.copyJson().put("job", job))
            }
            val observations = job.optJSONArray("observations") ?: JSONArray()
            persist(state.copyJson().put("observations", JSONArray(state.optJSONArray("observations")?.objects().orEmpty()
                .filter { it.getString("evidence_id") != source.getString("evidence_id") } + observations.objects()))
                .put("portrait_status", "BUILDING"))
            val chunks = evidenceSpans(source)
            if (job.has("traits") && !job.has("trait_chunks")) job.put("trait_chunks", chunks.size) // Resume a legacy full-material checkpoint.
            while (job.optInt("trait_chunks") < chunks.size) {
                val chunk = chunks[job.optInt("trait_chunks")]
                val newObservations = JSONArray(observations.objects().filter { !chunk.has("span_start") ||
                    it.getInt("start") < chunk.getInt("span_end") && it.getInt("end") > chunk.getInt("span_start") })
                val related = LocalEvidenceIndex(JSONArray(materials().objects().filter { it.getString("evidence_id") != source.getString("evidence_id") }),
                    state.optJSONArray("observations") ?: JSONArray()).retrieve(newObservations.objects().joinToString(" ") { it.getString("summary") }, fallback = false)
                val input = JSONArray(related.objects()).put(chunk)
                val current = model().put("traits", job.optJSONArray("traits") ?: model().getJSONArray("traits"))
                job.put("traits", inference.understand(current, input, config.language, newObservations)).put("trait_chunks", job.optInt("trait_chunks") + 1)
                persist(state.copyJson().put("job", job))
            }
            if (!job.has("habits")) {
                val psychologyIds = state.optJSONArray("observations")?.objects().orEmpty().filter {
                    it.getString("dimension") in setOf("psychological", "mood") }.map { it.getString("evidence_id") }.toSet() +
                    activeHabits().objects().flatMap { it.getJSONArray("evidence_ids").strings() } + source.getString("evidence_id")
                val input = JSONArray(materials().objects().filter { it.getString("evidence_id") in psychologyIds || it.getString("source_type") == "CALIBRATION" })
                job.put("habits", psychology.learn(job.getJSONArray("traits"), input, activeHabits(), config.language))
                persist(state.copyJson().put("job", job))
            }
            val next = state.copyJson()
            next.getJSONArray("history").put(model())
            publishMaterial(next, job)
            next.put("traits", job.getJSONArray("traits")).put("habits", job.getJSONArray("habits"))
                .put("portrait_status", "READY").put("portrait_memory_revision", state.optInt("memory_revision"))
                .put("revision", state.getInt("revision") + 1).put("model_version", config.language.model).remove("job")
            var result = JSONObject()
            if (job.getString("kind") == "CORRECT") {
                result = next.getJSONArray("calibrations").objects().first { it.getString("calibration_id") == job.getString("id") }
                result.put("state", "COMPLETED").put("resulting_revision", next.getInt("revision")).put("human_answer", job.getString("human_answer"))
            } else if (job.getString("kind") == "CAPTURE") publishEpisode(next, job, "READY")
            persist(next)
            return result
        } catch (e: Exception) {
            job = checkNotNull(pending())
            persist(state.copyJson().put("portrait_status", if (job.getString("kind") == "ASK") state.optString("portrait_status", "PENDING") else "FAILED")
                .put("job", job.put("status", "PAUSED").put("error", "任务未完成，可继续；已保存的材料保留。")))
            throw e
        }
    }
    private fun publishMaterial(next: JSONObject, job: JSONObject) {
        val evidence = job.getJSONObject("evidence")
        if (next.getJSONArray("materials").objects().none { it.getString("evidence_id") == evidence.getString("evidence_id") }) {
            next.put("memory_revision", next.optInt("memory_revision") + 1).put("portrait_status", "PENDING")
        }
        next.put("materials", JSONArray(next.getJSONArray("materials").objects().filter { it.getString("evidence_id") != evidence.getString("evidence_id") }).put(evidence))
    }
    private fun publishEpisode(next: JSONObject, job: JSONObject, status: String) {
        next.put("episodes", JSONArray(next.getJSONArray("episodes").objects().filter { it.getString("id") != job.getString("id") })
            .put(job.copyJson().apply { remove("evidence"); remove("traits"); remove("habits"); remove("observations"); put("understanding_status", status)
                if (status == "READY") put("observation_version", MemoryDimensionRegistry.version) }))
    }
    private suspend fun lockAnswer(question: String, id: String, endpoint: ModelEndpoint): JSONObject {
        val pack = LocalEvidenceIndex(materials(), state.optJSONArray("observations") ?: JSONArray()).retrieve(question)
        val answer = inference.answer(question, model(), pack, endpoint, activeHabits())
        val cal = JSONObject().put("calibration_id", id).put("question", question).put("locked_answer", answer)
            .put("locked_at", now()).put("lock_digest", digest(answer.toString())).put("state", "LOCKED").put("resulting_revision", JSONObject.NULL)
        persist(state.copyJson().apply { getJSONArray("calibrations").put(cal) })
        return cal
    }
    private fun calibration(id: String) = state.getJSONArray("calibrations").objects().first {
        it.getString("calibration_id") == id
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
                if (answerRoots(cal.getJSONObject("locked_answer")).any { it in removed }) {
                    cal.put("state", "INVALIDATED")
                    next.getJSONArray("materials").objects().filter { it.getString("source_ref") == "calibration:${cal.getString("calibration_id")}" }
                        .forEach { if (removed.add(it.getString("evidence_id"))) changed = true }
                }
            }
        } while (changed)
        next.put("withdrawn_evidence", JSONArray(removed)).put("revision", next.getInt("revision") + 1)
            .put("memory_revision", next.optInt("memory_revision") + 1).put("portrait_status", "PENDING")
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

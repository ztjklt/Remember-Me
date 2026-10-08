package me.remember.app.data.agent

import me.remember.app.data.repository.AudioRecording
import me.remember.app.data.repository.ExtractedMemory
import me.remember.app.data.repository.MemoryExtractionResult
import me.remember.app.data.repository.ReviewedMemoryProcessor

/** Existing UI receives ordinary sidecar memories; it need not know the journal or model protocol. */
class ReviewedAgentProcessor(private val engine: AgentMemoryEngine) : ReviewedMemoryProcessor {
    override val dataUseDescription = "将核对后的文字、相关已授权原文和已有理解发送给配置的整理服务。机器转写留在本机。"
    override suspend fun organize(confirmedText: String): MemoryExtractionResult =
        error("需要录音来源信息，请通过 RecordingWorkflow 整理。")

    fun episodeId(recording: AudioRecording): String {
        val text = checkNotNull(recording.reviewedTranscript) { "请先核对文字。" }
        return "ep_" + stableDigest("${recording.audioPath}|${recording.createdAt}|$text")
    }

    override suspend fun organize(recording: AudioRecording, consent: Boolean): MemoryExtractionResult {
        check(recording.reviewedAt != null && !recording.reviewedTranscript.isNullOrBlank()) { "请先核对并确认文字。" }
        val id = episodeId(recording)
        engine.addEpisode(id, recording.reviewedTranscript!!, recording.createdAt, consent,
            rawTranscript = recording.transcript, recordingRef = stableDigest("${recording.audioPath}|${recording.createdAt}"))
        val portrait = engine.portrait()
        val source = portrait.sources.single { it.episodeId == id }
        val memories = portrait.observations.filter { it.evidenceId == source.id && it.status == "ACTIVE" }.map {
            ExtractedMemory(it.id, it.dimension, it.summary, it.quote, .5f, sourceType = "AI_INFERENCE")
        }
        return MemoryExtractionResult(memories, engine.snapshot().getString("model_version"))
    }
}

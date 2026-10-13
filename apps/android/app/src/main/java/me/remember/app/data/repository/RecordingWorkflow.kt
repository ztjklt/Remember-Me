package me.remember.app.data.repository

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant

/** Inject a reviewed, consent-aware backend adapter here; production supplies no provider credentials. */
interface ReviewedMemoryProcessor {
    val dataUseDescription: String
    suspend fun organize(confirmedText: String): MemoryExtractionResult
}

class RecordingWorkflow(
    private val audio: AudioCaptureService,
    private val asr: LocalAsrService?,
    private val processor: ReviewedMemoryProcessor? = null
) {
    private val mutex = Mutex()
    val canOrganize get() = processor != null
    val dataUseDescription get() = processor?.dataUseDescription ?: "记忆整理服务尚未连接。原音和核对文字可以先保存在手机。"

    private fun current(path: String) = audio.recordings().first { it.audioPath == path }
    private fun save(recording: AudioRecording): AudioRecording {
        audio.updateRecording(recording)
        return recording
    }

    suspend fun transcribe(path: String): AudioRecording = mutex.withLock {
        val original = current(path)
        // Retrying organization never transcribes or overwrites the original text again.
        if (original.transcript.isNotBlank()) return@withLock original
        try {
            check(asr != null) { "本机转写暂不可用。原音仍保存在手机，可以稍后重试。" }
            save(original.copy(processingStage = ProcessingStage.Transcribing, processingError = null))
            val text = asr.transcribe(path).trim()
            check(text.isNotBlank()) { "没有识别出文字。请先听听原音，再决定是否重试。" }
            save(current(path).copy(transcript = text, asrStatus = AsrStatus.Ready,
                processingStage = ProcessingStage.NeedsReview, processingError = null))
        } catch (error: Exception) {
            save(current(path).copy(processingStage = ProcessingStage.Failed,
                processingError = if (error is CancellationException) "转写已中断，可重试。" else error.message,
                asrStatus = AsrStatus.Failed))
            throw error
        }
    }

    suspend fun confirm(path: String, text: String): AudioRecording = mutex.withLock {
        require(text.isNotBlank()) { "请先核对文字，不能保存空白内容。" }
        val original = current(path)
        check(original.transcript.isNotBlank()) { "请先完成本机转写。" }
        check(original.processingStage != ProcessingStage.Organizing) { "正在整理，请稍后再试。" }
        val changed = original.reviewedTranscript != text.trim()
        // Source edits invalidate derived results without discarding their local history.
        save(original.copy(reviewedTranscript = text.trim(), reviewedAt = Instant.now().toString(),
            memories = if (changed) original.memories.map { if (it.status == "active") it.copy(status = "superseded") else it } else original.memories,
            processingStage = if (!changed && original.processingStage == ProcessingStage.Complete) ProcessingStage.Complete else ProcessingStage.NeedsReview,
            processingError = null))
    }

    suspend fun organize(path: String, consent: Boolean): AudioRecording = mutex.withLock {
        require(consent) { "需要你明确同意后才会发送核对后的文字。" }
        val original = current(path)
        check(original.reviewedAt != null && !original.reviewedTranscript.isNullOrBlank()) { "请先核对并确认文字。" }
        if (original.processingStage == ProcessingStage.Complete) return@withLock original
        try {
            check(processor != null) { dataUseDescription }
            save(original.copy(processingStage = ProcessingStage.Organizing, processingError = null))
            val result = processor.organize(original.reviewedTranscript!!)
            // Reject invented quotations; UI must never dress unsupported evidence as original speech.
            require(result.memories.all { it.evidence.isBlank() || original.reviewedTranscript.contains(it.evidence) }) {
                "整理结果的来源无法核对，已保留文字，请稍后重试。"
            }
            val history = original.memories.filter { it.status != "active" }
            save(current(path).copy(memories = history + result.memories.distinctBy { it.id },
                personModelVersion = result.modelVersion, processingStage = ProcessingStage.Complete,
                processingError = null))
        } catch (error: Exception) {
            save(current(path).copy(processingStage = ProcessingStage.Failed,
                processingError = if (error is CancellationException) "整理已中断，可重试。" else error.message))
            throw error
        }
    }
}

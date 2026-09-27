package me.remember.app.data.repository

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flowOf
import me.remember.app.model.*

interface MemoryRepository { fun memories():Flow<Loadable<List<Memory>>> }
interface PersonModelRepository { fun subject():Flow<Loadable<Subject>> }
interface LegacyRepository { fun legacyProfile():Flow<Loadable<LegacyProfile>> }
data class AudioRecording(
    val audioPath: String,
    val durationMillis: Long,
    val mimeType: String,
    val byteSize: Long,
    val sampleRate: Int,
    val channelCount: Int,
    val createdAt: String,
    val title: String = "未命名录音",
    val transcript: String = "",
    val summary: String = "",
    val asrStatus: AsrStatus = AsrStatus.NotRequested,
    val memories: List<ExtractedMemory> = emptyList(),
    val personModelVersion: String = "",
    val reviewedTranscript: String? = null,
    val reviewedAt: String? = null,
    val processingStage: ProcessingStage = if (transcript.isBlank()) ProcessingStage.Unprocessed else ProcessingStage.NeedsReview,
    val processingError: String? = null
)

enum class ProcessingStage { Unprocessed, Transcribing, NeedsReview, Organizing, Complete, Failed }
data class PlaybackState(val audioPath: String? = null, val playing: Boolean = false,
    val positionMillis: Long = 0, val durationMillis: Long = 0, val error: String? = null,
    val preparing: Boolean = false)

data class ExtractedMemory(
    val id: String,
    val kind: String,
    val content: String,
    val evidence: String,
    val confidence: Float,
    val sourceType: String = "SUBJECT",
    val status: String = "active"
)

enum class AsrStatus { NotRequested, Processing, Ready, Failed }

interface AudioCaptureService {
    val playback: StateFlow<PlaybackState> get() = MutableStateFlow(PlaybackState())
    fun observeRecordings(): Flow<List<AudioRecording>> = flowOf(recordings())
    fun amplitude(): Float = 0f
    fun pausePlayback() = stopPlayback()
    fun resumePlayback() = Unit
    fun seekPlayback(positionMillis: Long) = Unit
    suspend fun start(): AudioRecording
    suspend fun pause()
    suspend fun resume()
    suspend fun stop(): AudioRecording
    fun elapsedMillis(): Long
    fun latestRecording(): AudioRecording?
    fun recordings(): List<AudioRecording>
    fun updateRecording(recording: AudioRecording)
    fun deleteMemory(recording: AudioRecording, memoryId: String)
    fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit)
    fun stopPlayback()
}
interface SpeechToTextService {
    suspend fun transcribe(audioRef:String): AsrResult
}

interface LocalAsrService {
    suspend fun transcribe(audioRef: String): String
}

data class AsrResult(val transcript: String, val summary: String, val title: String)

interface TitleGenerator {
    suspend fun generateTitle(transcript: String): String
}

interface MemoryExtractor {
    suspend fun extract(transcript: String, existingModelVersion: String = ""): MemoryExtractionResult
}

data class MemoryExtractionResult(
    val memories: List<ExtractedMemory>,
    val modelVersion: String
)

data class PersonTrait(
    val domain: String,
    val statement: String,
    val confidence: Float,
    val evidenceMemoryIds: List<String>,
    val sourceType: String = "SUBJECT"
)

data class PersonModel(
    val version: String = "1",
    val traits: List<PersonTrait> = emptyList()
)

data class GraphNode(val id: String, val label: String, val type: String)
data class GraphEdge(val from: String, val to: String, val label: String, val evidenceMemoryIds: List<String> = emptyList())
data class MemoryConflict(val memoryId: String, val existingMemoryId: String, val reason: String)

data class AgentState(
    val personModel: PersonModel = PersonModel(),
    val nodes: List<GraphNode> = emptyList(),
    val edges: List<GraphEdge> = emptyList(),
    val conflicts: List<MemoryConflict> = emptyList()
)

interface AgentStateStore {
    fun read(): AgentState
    fun write(state: AgentState)
    fun rebuild(recordings: List<AudioRecording>): AgentState
}

/** Replace with an ONNX text model when its tokenizer/model assets are bundled. */
class LocalTitleGenerator : TitleGenerator {
    override suspend fun generateTitle(transcript: String): String {
        val normalized = transcript.replace(Regex("\\s+"), " ").trim()
        if (normalized.isBlank()) return "未命名录音"
        val sentence = normalized.split(Regex("[。！？.!?]"))
            .firstOrNull { it.trim().length >= 4 }?.trim().orEmpty()
        return sentence.take(24).ifBlank { normalized.take(24) }
    }
}
interface TwinService { suspend fun respond(question:String):TwinReply }
interface VoiceCloneService { suspend fun preview():Result<Unit> }
interface HardwareCaptureAdapter { val isAvailable:Boolean; suspend fun startRecording(); suspend fun stopRecording() }

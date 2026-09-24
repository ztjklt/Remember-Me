package me.remember.app.data.repository

import kotlinx.coroutines.flow.Flow
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
    val createdAt: String
)

interface AudioCaptureService {
    suspend fun start(): AudioRecording
    suspend fun pause()
    suspend fun resume()
    suspend fun stop(): AudioRecording
    /** Finalize an active capture when its screen or activity stops; no-op after a save. */
    fun stopIfActive(): AudioRecording?
    /** Capabilities of the source selected for the current recording. */
    fun supportsPauseResume(): Boolean = true
    fun elapsedMillis(): Long
    fun latestRecording(): AudioRecording?
    fun canPlay(recording: AudioRecording): Boolean = true
    fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit)
    fun stopPlayback()
}
interface SpeechToTextService { suspend fun transcribe(audioRef:String):String }
interface TwinService { suspend fun respond(question:String):TwinReply }
interface VoiceCloneService { suspend fun preview():Result<Unit> }

enum class CaptureDeviceState {
    Unavailable,
    Ready,
    Starting,
    Recording,
    Paused,
    Failed
}

enum class CaptureCapability {
    PauseResume,
    RecordingRetrieval,
    LocalPlayback
}

data class CaptureCapabilityProfile(val supported: Set<CaptureCapability>) {
    fun supports(capability: CaptureCapability): Boolean = capability in supported
}

interface HardwareCaptureAdapter {
    val isAvailable: Boolean
    val deviceState: CaptureDeviceState
    val capabilityProfile: CaptureCapabilityProfile

    suspend fun startRecording(): AudioRecording
    suspend fun pauseRecording()
    suspend fun resumeRecording()
    suspend fun stopRecording(): AudioRecording
    /** Synchronously finalize an active capture during lifecycle teardown. */
    fun stopRecordingIfActive(): AudioRecording?
    fun elapsedMillis(): Long
    fun latestRecording(): AudioRecording?
    fun isRecordingAvailable(recording: AudioRecording? = null): Boolean
    fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit)
    fun stopPlayback()
}

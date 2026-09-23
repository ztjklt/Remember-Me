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
    fun elapsedMillis(): Long
    fun latestRecording(): AudioRecording?
    fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit)
    fun stopPlayback()
}
interface SpeechToTextService { suspend fun transcribe(audioRef:String):String }
interface TwinService { suspend fun respond(question:String):TwinReply }
interface VoiceCloneService { suspend fun preview():Result<Unit> }
interface HardwareCaptureAdapter { val isAvailable:Boolean; suspend fun startRecording(); suspend fun stopRecording() }

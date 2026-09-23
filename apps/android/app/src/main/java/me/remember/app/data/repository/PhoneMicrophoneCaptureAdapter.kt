package me.remember.app.data.repository

import android.content.Context
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.UUID

class PhoneMicrophoneCaptureAdapter(private val context: Context) : HardwareCaptureAdapter {
    private val recordingsDir = File(context.filesDir, "recordings").apply { mkdirs() }
    private var recorder: MediaRecorder? = null
    private var activeAudioFile: File? = null
    private var activeCreatedAt: String? = null
    private var activeStartedAt = 0L
    private var elapsedBeforeResume = 0L
    private var player: MediaPlayer? = null
    override var deviceState: CaptureDeviceState = CaptureDeviceState.Ready
        private set

    override val isAvailable: Boolean = true
    override val capabilityProfile = CaptureCapabilityProfile(
        setOf(
            CaptureCapability.PauseResume,
            CaptureCapability.RecordingRetrieval,
            CaptureCapability.LocalPlayback
        )
    )

    override suspend fun startRecording(): AudioRecording {
        check(recorder == null) { "A recording is already active." }
        check(recordingsDir.isDirectory) { "App storage is unavailable." }

        val audioFile = File(recordingsDir, "${UUID.randomUUID()}.m4a")
        val createdAt = Instant.now().toString()
        val newRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }

        deviceState = CaptureDeviceState.Starting
        try {
            newRecorder.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioSamplingRate(SAMPLE_RATE)
                setAudioChannels(CHANNEL_COUNT)
                setAudioEncodingBitRate(96_000)
                setOutputFile(audioFile.absolutePath)
                prepare()
                start()
            }
        } catch (error: Exception) {
            runCatching { newRecorder.release() }
            audioFile.delete()
            deviceState = CaptureDeviceState.Failed
            throw IllegalStateException("Could not start microphone recording: ${error.message ?: "unknown error"}", error)
        }

        stopPlayback()
        recorder = newRecorder
        activeAudioFile = audioFile
        activeCreatedAt = createdAt
        activeStartedAt = SystemClock.elapsedRealtime()
        elapsedBeforeResume = 0L
        deviceState = CaptureDeviceState.Recording
        return AudioRecording(audioFile.absolutePath, 0L, MIME_TYPE, 0L, SAMPLE_RATE, CHANNEL_COUNT, createdAt)
    }

    override suspend fun pauseRecording() {
        val active = checkNotNull(recorder) { "No recording is active." }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
            throw IllegalStateException("Pause and resume require Android 7.0 or newer.")
        }
        try {
            active.pause()
            elapsedBeforeResume += SystemClock.elapsedRealtime() - activeStartedAt
            activeStartedAt = 0L
            deviceState = CaptureDeviceState.Paused
        } catch (error: Exception) {
            throw IllegalStateException("Could not pause recording: ${error.message ?: "unknown error"}", error)
        }
    }

    override suspend fun resumeRecording() {
        val active = checkNotNull(recorder) { "No recording is active." }
        try {
            active.resume()
            activeStartedAt = SystemClock.elapsedRealtime()
            deviceState = CaptureDeviceState.Recording
        } catch (error: Exception) {
            throw IllegalStateException("Could not resume recording: ${error.message ?: "unknown error"}", error)
        }
    }

    override fun elapsedMillis(): Long = elapsedBeforeResume + if (activeStartedAt > 0L) {
        SystemClock.elapsedRealtime() - activeStartedAt
    } else 0L

    override suspend fun stopRecording(): AudioRecording =
        checkNotNull(stopRecordingIfActive()) { "No recording is active." }

    override fun stopRecordingIfActive(): AudioRecording? {
        if (recorder == null) return null
        val active = checkNotNull(recorder) { "No recording is active." }
        val audioFile = checkNotNull(activeAudioFile)
        val createdAt = checkNotNull(activeCreatedAt)
        val duration = elapsedMillis()

        try {
            active.stop()
        } catch (error: Exception) {
            audioFile.delete()
            throw IllegalStateException("Recording could not be finalized: ${error.message ?: "audio was too short"}", error)
        } finally {
            runCatching { active.reset() }
            active.release()
            recorder = null
            activeAudioFile = null
            activeCreatedAt = null
            activeStartedAt = 0L
            elapsedBeforeResume = 0L
            deviceState = CaptureDeviceState.Ready
        }

        if (!audioFile.isFile || audioFile.length() == 0L) {
            audioFile.delete()
            throw IllegalStateException("The recording file is empty.")
        }

        val recording = AudioRecording(
            audioPath = audioFile.absolutePath,
            durationMillis = duration,
            mimeType = MIME_TYPE,
            byteSize = audioFile.length(),
            sampleRate = SAMPLE_RATE,
            channelCount = CHANNEL_COUNT,
            createdAt = createdAt
        )
        try {
            File(audioFile.parentFile, "${audioFile.nameWithoutExtension}.json").writeText(recording.toJson().toString())
        } catch (error: Exception) {
            audioFile.delete()
            throw IllegalStateException("Could not save recording metadata: ${error.message ?: "unknown error"}", error)
        }
        return recording
    }

    override fun latestRecording(): AudioRecording? = recordingsDir.listFiles { file -> file.extension == "json" }
        ?.sortedByDescending(File::lastModified)
        ?.firstNotNullOfOrNull { sidecar ->
            runCatching {
                val recording = sidecar.readText().let(::JSONObject).toRecording()
                recording.takeIf { File(it.audioPath).isFile }
        }.getOrNull()
    }

    override fun isRecordingAvailable(recording: AudioRecording?): Boolean =
        if (recording == null) latestRecording() != null else File(recording.audioPath).isFile

    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) {
        stopPlayback()
        val audioFile = File(recording.audioPath)
        check(audioFile.isFile) { "The saved audio file no longer exists." }
        val newPlayer = MediaPlayer()
        try {
            newPlayer.setDataSource(audioFile.absolutePath)
            newPlayer.setOnCompletionListener {
                stopPlayback()
                onComplete()
            }
            newPlayer.setOnErrorListener { _, _, _ ->
                stopPlayback()
                onError("Audio playback failed. The saved file may be damaged or unsupported.")
                true
            }
            newPlayer.prepare()
            newPlayer.start()
            player = newPlayer
        } catch (error: Exception) {
            runCatching { newPlayer.release() }
            throw IllegalStateException("Could not play the saved recording: ${error.message ?: "unknown error"}", error)
        }
    }

    override fun stopPlayback() {
        player?.let { current ->
            runCatching { if (current.isPlaying) current.stop() }
            current.release()
        }
        player = null
    }

    companion object {
        const val MIME_TYPE = "audio/mp4"
        const val SAMPLE_RATE = 44_100
        const val CHANNEL_COUNT = 1

        private fun AudioRecording.toJson() = JSONObject().apply {
            put("audioPath", audioPath)
            put("durationMillis", durationMillis)
            put("mimeType", mimeType)
            put("byteSize", byteSize)
            put("sampleRate", sampleRate)
            put("channelCount", channelCount)
            put("created_at", createdAt)
        }

        private fun JSONObject.toRecording() = AudioRecording(
            audioPath = getString("audioPath"),
            durationMillis = getLong("durationMillis"),
            mimeType = getString("mimeType"),
            byteSize = getLong("byteSize"),
            sampleRate = getInt("sampleRate"),
            channelCount = getInt("channelCount"),
            createdAt = optString("created_at", optString("createdAt"))
        )
    }
}

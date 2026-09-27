package me.remember.app.data.repository

import android.content.Context
import android.media.MediaPlayer
import android.media.MediaMetadataRetriever
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import android.util.AtomicFile
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.File
import java.time.Instant
import java.util.UUID

class AndroidAudioCaptureService(private val context: Context) : AudioCaptureService {
    private val recordingsDir = File(context.filesDir, "recordings").apply { mkdirs() }
    private var recorder: MediaRecorder? = null
    private var activeAudioFile: File? = null
    private var activeCreatedAt: String? = null
    private var activeStartedAt = 0L
    private var elapsedBeforeResume = 0L
    private var player: MediaPlayer? = null

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var playbackJob: Job? = null
    private val playbackState = MutableStateFlow(PlaybackState())
    override val playback = playbackState.asStateFlow()
    private val archive = MutableStateFlow<List<AudioRecording>>(emptyList())
    override fun observeRecordings() = archive.asStateFlow()

    init {
        val initial = recordings().map { item ->
            val recovered = RecordingMetadata.recoverInterrupted(item)
            if (recovered != item) runCatching { updateRecording(recovered) }
            recovered
        }
        // Read access and playback still work when storage cannot accept a recovery write.
        archive.value = initial
    }

    private fun refreshArchive() { archive.value = recordings() }
    override fun amplitude(): Float = if (activeStartedAt == 0L) 0f else
        runCatching { ((recorder?.maxAmplitude ?: 0) / 32767f).coerceIn(0f, 1f) }.getOrDefault(0f)

    override suspend fun start(): AudioRecording {
        check(recorder == null) { "A recording is already active." }
        check(recordingsDir.isDirectory) { "App storage is unavailable." }

        stopPlayback()
        val audioFile = File(recordingsDir, "${UUID.randomUUID()}.m4a")
        val createdAt = Instant.now().toString()
        val newRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }

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
            throw IllegalStateException("Could not start microphone recording: ${error.message ?: "unknown error"}", error)
        }

        stopPlayback()
        recorder = newRecorder
        activeAudioFile = audioFile
        activeCreatedAt = createdAt
        activeStartedAt = SystemClock.elapsedRealtime()
        elapsedBeforeResume = 0L
        return AudioRecording(audioFile.absolutePath, 0L, MIME_TYPE, 0L, SAMPLE_RATE, CHANNEL_COUNT, createdAt)
    }

    override suspend fun pause() {
        val active = checkNotNull(recorder) { "No recording is active." }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
            throw IllegalStateException("Pause and resume require Android 7.0 or newer.")
        }
        try {
            active.pause()
            elapsedBeforeResume += SystemClock.elapsedRealtime() - activeStartedAt
            activeStartedAt = 0L
        } catch (error: Exception) {
            throw IllegalStateException("Could not pause recording: ${error.message ?: "unknown error"}", error)
        }
    }

    override suspend fun resume() {
        val active = checkNotNull(recorder) { "No recording is active." }
        try {
            active.resume()
            activeStartedAt = SystemClock.elapsedRealtime()
        } catch (error: Exception) {
            throw IllegalStateException("Could not resume recording: ${error.message ?: "unknown error"}", error)
        }
    }

    override fun elapsedMillis(): Long = elapsedBeforeResume + if (activeStartedAt > 0L) {
        SystemClock.elapsedRealtime() - activeStartedAt
    } else 0L

    override suspend fun stop(): AudioRecording {
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
        // A metadata failure must never remove a successfully recorded audio file.
        try { updateRecording(recording) }
        catch (error: Exception) {
            refreshArchive()
            throw IllegalStateException("原音文件已保留，但记录信息未能保存。可从档案中的恢复录音继续。", error)
        }
        return recording
    }

    override fun latestRecording(): AudioRecording? = recordings().firstOrNull()

    override fun recordings(): List<AudioRecording> = recordingsDir.listFiles { file -> file.extension == "m4a" && file != activeAudioFile }
        ?.mapNotNull { file ->
            val sidecar = AtomicFile(File(recordingsDir, "${file.nameWithoutExtension}.json"))
            runCatching { sidecar.openRead().bufferedReader().use { RecordingMetadata.decode(it.readText()) } }
                .getOrNull()?.copy(audioPath = file.absolutePath) ?: recoverAudioFile(file)
        }
        ?.sortedByDescending { it.createdAt }
        ?: emptyList()

    // A interrupted metadata write must not hide a valid original audio file.
    private fun recoverAudioFile(file: File): AudioRecording? {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(file.absolutePath)
            val duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: return null
            AudioRecording(file.absolutePath, duration, MIME_TYPE, file.length(), SAMPLE_RATE, CHANNEL_COUNT,
                Instant.ofEpochMilli(file.lastModified()).toString(), title = "恢复的录音", processingStage = ProcessingStage.Failed,
                processingError = "原音已恢复。记录信息缺失或损坏，可以播放或重新转写。")
        } catch (_: Exception) { null } finally { retriever.release() }
    }

    override fun updateRecording(recording: AudioRecording) {
        val audioFile = File(recording.audioPath)
        val atomic = AtomicFile(File(audioFile.parentFile, "${audioFile.nameWithoutExtension}.json"))
        val stream = atomic.startWrite()
        try {
            stream.write(RecordingMetadata.encode(recording).toByteArray(Charsets.UTF_8))
            atomic.finishWrite(stream)
        } catch (error: Exception) {
            atomic.failWrite(stream)
            throw error
        }
        refreshArchive()
    }

    override fun deleteMemory(recording: AudioRecording, memoryId: String) {
        updateRecording(recording.copy(memories = recording.memories.map { memory ->
            if (memory.id == memoryId) memory.copy(status = "deleted") else memory
        }))
    }

    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) {
        stopPlayback()
        val file = File(recording.audioPath)
        check(file.isFile) { "原始录音文件不存在。" }
        val next = MediaPlayer()
        player = next
        playbackState.value = PlaybackState(recording.audioPath, durationMillis = recording.durationMillis, preparing = true)
        try {
            next.setDataSource(file.absolutePath)
            next.setOnPreparedListener {
                if (player !== next) return@setOnPreparedListener
                next.start()
                playbackState.value = playbackState.value.copy(playing = true, preparing = false, durationMillis = next.duration.toLong())
                watchPlayer()
            }
            next.setOnCompletionListener {
                playbackJob?.cancel()
                playbackState.value = playbackState.value.copy(playing = false, positionMillis = playbackState.value.durationMillis)
                onComplete()
            }
            next.setOnErrorListener { _, _, _ ->
                stopPlayback()
                playbackState.value = PlaybackState(recording.audioPath, error = "原音播放失败，请检查文件后重试。")
                onError("原音播放失败，请检查文件后重试。")
                true
            }
            next.prepareAsync()
        } catch (error: Exception) {
            stopPlayback()
            playbackState.value = PlaybackState(recording.audioPath, error = "无法打开原音。")
            onError("无法打开原音。")
        }
    }

    private fun watchPlayer() {
        playbackJob?.cancel()
        playbackJob = scope.launch {
            while (isActive) {
                val current = player ?: break
                runCatching { playbackState.value = playbackState.value.copy(
                    positionMillis = current.currentPosition.toLong(), playing = current.isPlaying) }
                delay(200)
            }
        }
    }
    override fun pausePlayback() {
        if (playbackState.value.preparing) return
        player?.let { runCatching { it.pause() } }
        playbackState.value = playbackState.value.copy(playing = false)
    }
    override fun resumePlayback() {
        if (playbackState.value.preparing) return
        player?.let { current -> runCatching {
            if (current.currentPosition >= current.duration) current.seekTo(0)
            current.start()
            playbackState.value = playbackState.value.copy(playing = true)
            watchPlayer()
        } }
    }
    override fun seekPlayback(positionMillis: Long) {
        if (playbackState.value.preparing) return
        val position = positionMillis.coerceIn(0, playbackState.value.durationMillis)
        player?.let { runCatching { it.seekTo(position.toInt()) } }
        playbackState.value = playbackState.value.copy(positionMillis = position)
    }
    override fun stopPlayback() {
        playbackJob?.cancel()
        player?.let { current -> runCatching { current.release() } }
        player = null
        playbackState.value = PlaybackState()
    }
    fun release() { stopPlayback(); scope.cancel() }

    companion object {
        const val MIME_TYPE = "audio/mp4"
        const val SAMPLE_RATE = 44_100
        const val CHANNEL_COUNT = 1
    }
}

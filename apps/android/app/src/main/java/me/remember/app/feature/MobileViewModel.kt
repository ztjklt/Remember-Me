package me.remember.app.feature

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import me.remember.app.data.repository.*

enum class CapturePhase { Ready, Starting, Recording, Paused, Saving, Saved, Failed }
data class CaptureUiState(val phase: CapturePhase = CapturePhase.Ready, val elapsedMillis: Long = 0,
    val levels: List<Float> = List(27) { 0f }, val recording: AudioRecording? = null, val error: String? = null)

class MobileViewModel(val audio: AudioCaptureService, localAsr: LocalAsrService? = null,
    processor: ReviewedMemoryProcessor? = null) : ViewModel() {
    private val workflow = RecordingWorkflow(audio, localAsr, processor)
    val recordings = audio.observeRecordings().stateIn(viewModelScope, SharingStarted.Eagerly, audio.recordings())
    val playback = audio.playback
    private val captureValue = MutableStateFlow(CaptureUiState())
    val capture = captureValue.asStateFlow()
    private val pendingValue = MutableStateFlow<Set<String>>(emptySet())
    val pending = pendingValue.asStateFlow()
    private val messageValue = MutableStateFlow<String?>(null)
    val message = messageValue.asStateFlow()
    val canOrganize get() = workflow.canOrganize
    val dataUseDescription get() = workflow.dataUseDescription
    private var ticker: Job? = null
    fun dismissMessage() { messageValue.value = null }
    fun newRecording() {
        if (captureValue.value.phase in listOf(CapturePhase.Starting, CapturePhase.Recording, CapturePhase.Paused, CapturePhase.Saving)) return
        captureValue.value = CaptureUiState()
    }
    fun start() {
        if (captureValue.value.phase !in listOf(CapturePhase.Ready, CapturePhase.Failed)) return
        captureValue.value = CaptureUiState(phase = CapturePhase.Starting)
        viewModelScope.launch {
            try {
                val recording = audio.start()
                captureValue.value = CaptureUiState(phase = CapturePhase.Recording, recording = recording)
                ticker = launch {
                    while (isActive) {
                        val state = captureValue.value
                        if (state.phase == CapturePhase.Recording) captureValue.value = state.copy(
                            elapsedMillis = audio.elapsedMillis(), levels = state.levels.drop(1) + audio.amplitude())
                        delay(100)
                    }
                }
            } catch (error: Exception) { captureValue.value = CaptureUiState(phase = CapturePhase.Failed, error = error.message ?: "录音未能开始，请重试。") }
        }
    }
    fun pauseOrResume() {
        val phase = captureValue.value.phase
        if (phase !in listOf(CapturePhase.Recording, CapturePhase.Paused)) return
        viewModelScope.launch {
            try {
                if (phase == CapturePhase.Recording) audio.pause() else audio.resume()
                captureValue.value = captureValue.value.copy(phase = if (phase == CapturePhase.Recording) CapturePhase.Paused else CapturePhase.Recording)
            } catch (error: Exception) { captureValue.value = captureValue.value.copy(error = error.message ?: "操作未完成，请重试。") }
        }
    }
    fun finish(after: () -> Unit = {}) {
        if (captureValue.value.phase !in listOf(CapturePhase.Recording, CapturePhase.Paused)) { after(); return }
        captureValue.value = captureValue.value.copy(phase = CapturePhase.Saving)
        ticker?.cancel()
        viewModelScope.launch {
            try {
                val saved = audio.stop()
                captureValue.value = captureValue.value.copy(phase = CapturePhase.Saved, recording = saved,
                    elapsedMillis = saved.durationMillis, error = null)
                after()
            } catch (error: Exception) { captureValue.value = captureValue.value.copy(phase = CapturePhase.Failed,
                error = error.message ?: "保存未完成，请重试。") }
        }
    }
    private fun task(path: String, action: suspend () -> Unit) {
        if (path in pendingValue.value) return
        pendingValue.value += path
        viewModelScope.launch {
            try { action() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) { messageValue.value = error.message ?: "操作未完成，已有内容仍保留。" }
            finally { pendingValue.value -= path }
        }
    }
    fun transcribe(path: String) = task(path) { workflow.transcribe(path) }
    fun saveReview(path: String, text: String) = task(path) { workflow.confirm(path, text) }
    fun organize(path: String, text: String, consent: Boolean) = task(path) {
        workflow.confirm(path, text); workflow.organize(path, consent)
    }
    fun deleteMemory(path: String, id: String) = task(path) {
        audio.deleteMemory(audio.recordings().first { it.audioPath == path }, id)
    }
    fun togglePlayback(recording: AudioRecording) {
        if (captureValue.value.phase in listOf(CapturePhase.Recording, CapturePhase.Paused, CapturePhase.Starting)) return
        val state = playback.value
        if (state.preparing && state.audioPath == recording.audioPath) return
        if (state.audioPath == recording.audioPath && state.error == null) {
            if (state.playing) audio.pausePlayback() else audio.resumePlayback()
        } else runCatching { audio.play(recording, {}, { messageValue.value = it }) }
            .onFailure { messageValue.value = it.message ?: "无法播放这段原音。" }
    }
    override fun onCleared() { ticker?.cancel(); audio.stopPlayback(); (audio as? AndroidAudioCaptureService)?.release() }
}

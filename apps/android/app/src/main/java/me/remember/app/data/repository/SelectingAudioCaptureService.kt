package me.remember.app.data.repository

class SelectingAudioCaptureService(
    private val phoneFallbackAdapter: HardwareCaptureAdapter,
    private val externalAdapter: HardwareCaptureAdapter? = null
) : AudioCaptureService {
    private var activeAdapter: HardwareCaptureAdapter? = null

    override suspend fun start(): AudioRecording {
        check(activeAdapter == null) { "A recording is already active." }
        val selected = externalAdapter?.takeIf {
            it.isAvailable && it.capabilityProfile.supports(CaptureCapability.RecordingRetrieval)
        } ?: phoneFallbackAdapter
        check(selected.isAvailable) { "No recording source is available." }
        activeAdapter = selected
        return try {
            selected.startRecording()
        } catch (error: Exception) {
            activeAdapter = null
            throw error
        }
    }

    override suspend fun pause() {
        val selected = activeForCurrentRecording()
        selected.requireCapability(CaptureCapability.PauseResume, "pause and resume")
        selected.pauseRecording()
    }

    override suspend fun resume() {
        val selected = activeForCurrentRecording()
        selected.requireCapability(CaptureCapability.PauseResume, "pause and resume")
        selected.resumeRecording()
    }

    override suspend fun stop(): AudioRecording {
        val selected = activeForCurrentRecording()
        return try {
            selected.stopRecording()
        } finally {
            activeAdapter = null
        }
    }

    override fun stopIfActive(): AudioRecording? {
        val selected = activeAdapter ?: return null
        return try {
            selected.stopRecordingIfActive()
        } finally {
            activeAdapter = null
        }
    }

    override fun supportsPauseResume(): Boolean =
        (activeAdapter ?: externalAdapter?.takeIf {
            it.isAvailable && it.capabilityProfile.supports(CaptureCapability.RecordingRetrieval)
        } ?: phoneFallbackAdapter).capabilityProfile.supports(CaptureCapability.PauseResume)

    override fun elapsedMillis(): Long = activeAdapter?.elapsedMillis() ?: 0L

    override fun latestRecording(): AudioRecording? =
        allAdapters().firstNotNullOfOrNull { adapter ->
            if (adapter.capabilityProfile.supports(CaptureCapability.RecordingRetrieval)) {
                adapter.latestRecording()
            } else {
                null
            }
        }

    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) {
        val selected = allAdapters().firstOrNull { adapter ->
            adapter.capabilityProfile.supports(CaptureCapability.LocalPlayback) &&
                adapter.isRecordingAvailable(recording)
        } ?: throw IllegalStateException("No available capture adapter can play this recording.")
        selected.play(recording, onComplete, onError)
    }

    override fun stopPlayback() {
        allAdapters().forEach(HardwareCaptureAdapter::stopPlayback)
    }

    private fun activeForCurrentRecording(): HardwareCaptureAdapter =
        checkNotNull(activeAdapter) { "No recording is active." }

    private fun HardwareCaptureAdapter.requireCapability(capability: CaptureCapability, label: String) {
        check(capabilityProfile.supports(capability)) {
            "The selected capture device does not support $label. Stop the recording to continue."
        }
    }

    private fun allAdapters(): List<HardwareCaptureAdapter> = buildList {
        externalAdapter?.let(::add)
        if (phoneFallbackAdapter !in this) add(phoneFallbackAdapter)
    }
}

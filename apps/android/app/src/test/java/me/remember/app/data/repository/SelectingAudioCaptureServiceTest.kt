package me.remember.app.data.repository

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class SelectingAudioCaptureServiceTest {
    @Test
    fun usesPhoneFallbackAndKeepsFullCapturePathWhenNoExternalDeviceExists() = runBlocking {
        val fallback = FakeCaptureAdapter()
        val service = SelectingAudioCaptureService(phoneFallbackAdapter = fallback)

        service.start()
        service.pause()
        service.resume()
        assertEquals(1_250L, service.elapsedMillis())
        val saved = service.stop()

        assertEquals(saved, service.latestRecording())
        assertTrue(fallback.isRecordingAvailable(saved))
        service.play(saved, {}, {})
        assertEquals(listOf("start", "pause", "resume", "stop", "play"), fallback.calls)
    }

    @Test
    fun unavailableExternalDeviceFallsBackToPhoneMicrophone() = runBlocking {
        val external = FakeCaptureAdapter(isAvailable = false)
        val fallback = FakeCaptureAdapter()
        val service = SelectingAudioCaptureService(fallback, external)

        service.start()
        service.stop()

        assertTrue(external.calls.isEmpty())
        assertEquals(listOf("start", "stop"), fallback.calls)
    }

    @Test
    fun availableExternalDeviceOwnsTheWholeCaptureSessionAndPlayback() = runBlocking {
        val external = FakeCaptureAdapter(recordingPath = "/external/device.m4a")
        val fallback = FakeCaptureAdapter()
        val service = SelectingAudioCaptureService(fallback, external)

        service.start()
        service.pause()
        service.resume()
        val saved = service.stop()
        assertEquals(saved, service.latestRecording())
        service.play(saved, {}, {})

        assertEquals(listOf("start", "pause", "resume", "stop", "play"), external.calls)
        assertTrue(fallback.calls.isEmpty())
    }

    @Test
    fun unsupportedPauseIsReportedButRecordingCanStillBeStopped() = runBlocking {
        val external = FakeCaptureAdapter(
            capabilityProfile = CaptureCapabilityProfile(setOf(CaptureCapability.RecordingRetrieval))
        )
        val fallback = FakeCaptureAdapter()
        val service = SelectingAudioCaptureService(fallback, external)

        service.start()
        assertFalse(service.supportsPauseResume())
        val error = assertThrows(IllegalStateException::class.java) { runBlocking { service.pause() } }
        assertTrue(error.message.orEmpty().contains("does not support pause and resume"))
        service.stop()

        assertEquals(listOf("start", "stop"), external.calls)
        assertFalse(fallback.calls.contains("start"))
    }

    @Test
    fun externalWithoutRecordingRetrievalFallsBackToPhone() = runBlocking {
        val external = FakeCaptureAdapter(
            capabilityProfile = CaptureCapabilityProfile(setOf(CaptureCapability.PauseResume))
        )
        val fallback = FakeCaptureAdapter()
        val service = SelectingAudioCaptureService(fallback, external)

        service.start()
        service.stop()

        assertTrue(external.calls.isEmpty())
        assertEquals(listOf("start", "stop"), fallback.calls)
    }

    @Test
    fun lifecycleStopFinalizesSelectedAdapterOnlyOnce() = runBlocking {
        val external = FakeCaptureAdapter(recordingPath = "/external/device.m4a")
        val service = SelectingAudioCaptureService(FakeCaptureAdapter(), external)

        service.start()
        assertEquals(service.latestRecording(), service.stopIfActive())
        assertEquals(null, service.stopIfActive())
        assertEquals(listOf("start", "stop"), external.calls)
        service.start()
        assertEquals(listOf("start", "stop", "start"), external.calls)
    }

    @Test
    fun playbackCapabilityUsesAnAdapterThatCanOpenTheSavedRecording() = runBlocking {
        val external = FakeCaptureAdapter(
            recordingPath = "/external/device.m4a",
            capabilityProfile = CaptureCapabilityProfile(setOf(CaptureCapability.RecordingRetrieval))
        )
        val service = SelectingAudioCaptureService(FakeCaptureAdapter(), external)

        service.start()
        val saved = service.stop()

        assertFalse(service.canPlay(saved))
    }
}

private class FakeCaptureAdapter(
    override val isAvailable: Boolean = true,
    private val recordingPath: String = "/phone/recording.m4a",
    override val capabilityProfile: CaptureCapabilityProfile = CaptureCapabilityProfile(
        CaptureCapability.entries.toSet()
    )
) : HardwareCaptureAdapter {
    val calls = mutableListOf<String>()
    private var state = CaptureDeviceState.Ready
    override val deviceState: CaptureDeviceState get() = state
    private val recording = AudioRecording(recordingPath, 1_000L, "audio/mp4", 4_096L, 44_100, 1, "2026-09-23T00:00:00Z")

    override suspend fun startRecording(): AudioRecording {
        calls += "start"
        state = CaptureDeviceState.Recording
        return recording
    }

    override suspend fun pauseRecording() {
        calls += "pause"
        state = CaptureDeviceState.Paused
    }

    override suspend fun resumeRecording() {
        calls += "resume"
        state = CaptureDeviceState.Recording
    }

    override suspend fun stopRecording(): AudioRecording {
        return checkNotNull(stopRecordingIfActive())
    }

    override fun stopRecordingIfActive(): AudioRecording? {
        if (state != CaptureDeviceState.Recording && state != CaptureDeviceState.Paused) return null
        calls += "stop"
        state = CaptureDeviceState.Ready
        return recording
    }

    override fun elapsedMillis(): Long = 1_250L
    override fun latestRecording(): AudioRecording = recording
    override fun isRecordingAvailable(recording: AudioRecording?): Boolean =
        recording == null || recording.audioPath == recordingPath

    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) {
        calls += "play"
        onComplete()
    }

    override fun stopPlayback() = Unit
}

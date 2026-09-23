package me.remember.app

import android.Manifest
import androidx.activity.compose.setContent
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.lifecycle.Lifecycle
import kotlinx.coroutines.CompletableDeferred
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.AudioCaptureService
import me.remember.app.data.repository.AudioRecording
import me.remember.app.feature.RecordingScreen
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CaptureInstrumentedTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    private lateinit var audioService: FakeAudioCaptureService

    @Before
    fun setUp() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.grantRuntimePermission(
            instrumentation.targetContext.packageName,
            Manifest.permission.RECORD_AUDIO
        )
        audioService = FakeAudioCaptureService()
        composeRule.activity.setContent {
            RememberMeTheme { RecordingScreen(audioService) }
        }
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("capture.recordingConsent").performClick()
    }

    @Test
    fun recordsPausesResumesSavesAndPlaysLocally() {
        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("capture.pause").performClick()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("capture.resume").performClick()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("capture.stop").performClick()
        composeRule.waitForIdle()

        composeRule.onNodeWithText("audio/mp4 · 44100 Hz · 1 ch").assertExists()
        composeRule.onNodeWithTag("capture.play").performClick()

        assertEquals(1, audioService.startCalls)
        assertEquals(1, audioService.pauseCalls)
        assertEquals(1, audioService.resumeCalls)
        assertEquals(1, audioService.stopCalls)
        assertEquals(1, audioService.playCalls)
    }

    @Test
    fun savedRecordingCanBeHandedToUploadWithoutStartingAnotherCapture() {
        var handedOff: AudioRecording? = null
        composeRule.activity.setContent {
            RememberMeTheme { RecordingScreen(audioService) { handedOff = it } }
        }
        composeRule.onNodeWithTag("capture.recordingConsent").performClick()
        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.onNodeWithTag("capture.stop").performClick()
        composeRule.onNodeWithTag("capture.upload").performClick()

        assertEquals("/app-private/recordings/test.m4a", handedOff?.audioPath)
        assertEquals(1, audioService.startCalls)
        assertEquals(1, audioService.stopCalls)
    }

    @Test
    fun startFailureIsShownAndCanBeRetried() {
        audioService.failStart = true

        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.waitForIdle()

        composeRule.onNodeWithText("test microphone failure").assertExists()
        composeRule.onNodeWithTag("capture.start").assertExists()
    }

    @Test
    fun missingPermissionShowsStorageRationaleBeforeRequest() {
        composeRule.activity.setContent {
            RememberMeTheme { RecordingScreen(audioService, hasMicrophonePermission = { false }) }
        }
        composeRule.waitForIdle()

        composeRule.onNodeWithText("录音需要麦克风权限。音频只会保存到此应用的私有存储。").assertExists()
        composeRule.onNodeWithTag("capture.recordingConsent").performClick()
        composeRule.onNodeWithTag("capture.requestPermission").assertExists()
        assertEquals(0, audioService.startCalls)
    }

    @Test
    fun recordingConsentIsRequiredBeforeStarting() {
        composeRule.activity.setContent {
            RememberMeTheme { RecordingScreen(audioService) }
        }
        composeRule.waitForIdle()

        composeRule.onNodeWithTag("capture.start").assertDoesNotExist()
        assertEquals(0, audioService.startCalls)
        composeRule.onNodeWithTag("capture.recordingConsent").performClick()
        composeRule.onNodeWithTag("capture.start").assertExists()
    }

    @Test
    fun anotherStartIsUnavailableWhileMicrophoneStartIsPending() {
        val startGate = CompletableDeferred<Unit>()
        audioService.startGate = startGate

        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.waitUntil(timeoutMillis = 3_000) { audioService.startCalls == 1 }

        composeRule.onNodeWithTag("capture.starting").assertExists()
        composeRule.onNodeWithTag("capture.start").assertDoesNotExist()
        assertEquals(1, audioService.startCalls)

        startGate.complete(Unit)
        composeRule.onNodeWithTag("capture.pause").assertExists()
    }

    @Test
    fun leavingAndReenteringCaptureFinalizesAndRestoresTheSavedFile() {
        val showCapture = mutableStateOf(true)
        composeRule.activity.setContent {
            RememberMeTheme { if (showCapture.value) RecordingScreen(audioService) }
        }
        composeRule.onNodeWithTag("capture.recordingConsent").performClick()
        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.onNodeWithTag("capture.pause").assertExists()

        composeRule.runOnUiThread { showCapture.value = false }
        composeRule.waitForIdle()
        assertEquals(1, audioService.stopCalls)

        composeRule.runOnUiThread { showCapture.value = true }
        composeRule.onNodeWithTag("capture.play").assertExists()
        composeRule.onNodeWithTag("capture.start").assertDoesNotExist()
        assertEquals(1, audioService.startCalls)
    }

    @Test
    fun backgroundingActivityFinalizesCaptureBeforeReturning() {
        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.onNodeWithTag("capture.pause").assertExists()

        composeRule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
        assertEquals(1, audioService.stopCalls)
        composeRule.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)

        composeRule.onNodeWithTag("capture.play").assertExists()
        composeRule.onNodeWithTag("capture.start").assertDoesNotExist()
    }

    @Test
    fun deviceWithoutPauseCapabilityStillOffersStopAndSave() {
        audioService.canPause = false
        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.onNodeWithTag("capture.stop").assertExists()
        composeRule.onNodeWithTag("capture.pause").assertDoesNotExist()
        composeRule.onNodeWithTag("capture.stop").performClick()
        composeRule.onNodeWithTag("capture.play").assertExists()
        assertEquals(0, audioService.pauseCalls)
    }
}

private class FakeAudioCaptureService : AudioCaptureService {
    var startCalls = 0
    var pauseCalls = 0
    var resumeCalls = 0
    var stopCalls = 0
    var playCalls = 0
    var failStart = false
    var canPause = true
    var startGate: CompletableDeferred<Unit>? = null
    private var active = false
    private var saved = false

    override suspend fun start(): AudioRecording {
        startCalls++
        startGate?.await()
        check(!failStart) { "test microphone failure" }
        active = true
        return savedRecording
    }

    override suspend fun pause() { pauseCalls++ }
    override suspend fun resume() { resumeCalls++ }
    override suspend fun stop(): AudioRecording = checkNotNull(stopIfActive())
    override fun stopIfActive(): AudioRecording? {
        if (!active) return null
        active = false
        saved = true
        stopCalls++
        return savedRecording
    }
    override fun supportsPauseResume(): Boolean = canPause
    override fun elapsedMillis(): Long = savedRecording.durationMillis
    override fun latestRecording(): AudioRecording? = if (saved) savedRecording else null
    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) {
        playCalls++
        onComplete()
    }
    override fun stopPlayback() = Unit

    private val savedRecording = AudioRecording(
        audioPath = "/app-private/recordings/test.m4a",
        durationMillis = 2_500L,
        mimeType = "audio/mp4",
        byteSize = 12_345L,
        sampleRate = 44_100,
        channelCount = 1,
        createdAt = "2026-09-23T00:00:00Z"
    )
}

package me.remember.app

import android.Manifest
import androidx.activity.compose.setContent
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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
    fun startFailureIsShownAndCanBeRetried() {
        audioService.failStart = true

        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.waitForIdle()

        composeRule.onNodeWithText("test microphone failure").assertExists()
        composeRule.onNodeWithTag("capture.start").assertExists()
    }

    @Test
    fun missingPermissionShowsStorageRationaleBeforeRequest() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.revokeRuntimePermission(
            instrumentation.targetContext.packageName,
            Manifest.permission.RECORD_AUDIO
        )
        composeRule.activity.setContent {
            RememberMeTheme { RecordingScreen(audioService) }
        }
        composeRule.waitForIdle()

        composeRule.onNodeWithText("录音需要麦克风权限。音频只会保存到此应用的私有存储。").assertExists()
        composeRule.onNodeWithTag("capture.requestPermission").assertExists()
        assertEquals(0, audioService.startCalls)
    }
}

private class FakeAudioCaptureService : AudioCaptureService {
    var startCalls = 0
    var pauseCalls = 0
    var resumeCalls = 0
    var stopCalls = 0
    var playCalls = 0
    var failStart = false

    override suspend fun start(): AudioRecording {
        startCalls++
        check(!failStart) { "test microphone failure" }
        return savedRecording
    }

    override suspend fun pause() { pauseCalls++ }
    override suspend fun resume() { resumeCalls++ }
    override suspend fun stop(): AudioRecording { stopCalls++; return savedRecording }
    override fun elapsedMillis(): Long = savedRecording.durationMillis
    override fun latestRecording(): AudioRecording? = null
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

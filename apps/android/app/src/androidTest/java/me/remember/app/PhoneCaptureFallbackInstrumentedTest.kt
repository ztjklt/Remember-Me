package me.remember.app

import android.Manifest
import androidx.activity.compose.setContent
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.PhoneMicrophoneCaptureAdapter
import me.remember.app.data.repository.SelectingAudioCaptureService
import me.remember.app.feature.RecordingScreen
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PhoneCaptureFallbackInstrumentedTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    private lateinit var captureService: SelectingAudioCaptureService

    @Before
    fun setUp() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.grantRuntimePermission(
            instrumentation.targetContext.packageName,
            Manifest.permission.RECORD_AUDIO
        )
        captureService = SelectingAudioCaptureService(
            phoneFallbackAdapter = PhoneMicrophoneCaptureAdapter(composeRule.activity.applicationContext)
        )
        composeRule.activity.setContent {
            RememberMeTheme { RecordingScreen(captureService) }
        }
        composeRule.waitForIdle()
        if (composeRule.onAllNodesWithTag("capture.retake").fetchSemanticsNodes().isNotEmpty()) {
            composeRule.onNodeWithTag("capture.retake").performClick()
        }
        composeRule.onNodeWithTag("capture.recordingConsent").performClick()
    }

    @Test
    fun phoneFallbackRecordsPausesSavesAndDecodesPrivateAudio() {
        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.waitUntil(10_000) {
            composeRule.onAllNodesWithTag("capture.stop").fetchSemanticsNodes().isNotEmpty()
        }

        Thread.sleep(1_200L)
        composeRule.onNodeWithTag("capture.pause").performClick()
        composeRule.waitUntil(5_000) {
            composeRule.onAllNodesWithTag("capture.resume").fetchSemanticsNodes().isNotEmpty()
        }
        Thread.sleep(500L)
        composeRule.onNodeWithTag("capture.resume").performClick()
        Thread.sleep(1_200L)
        composeRule.onNodeWithTag("capture.stop").performClick()
        composeRule.waitUntil(10_000) {
            composeRule.onAllNodesWithTag("capture.play").fetchSemanticsNodes().isNotEmpty()
        }

        val saved = requireNotNull(captureService.latestRecording())
        val audioFile = File(saved.audioPath)
        assertTrue(audioFile.isFile)
        assertTrue(audioFile.length() > 0L)
        assertEquals(audioFile.length(), saved.byteSize)
        assertTrue(saved.durationMillis >= 2_000L)
        assertTrue(saved.durationMillis < 3_000L)
        assertTrue(saved.audioPath.contains("/files/recordings/"))

        composeRule.onNodeWithTag("capture.play").performClick()
        captureService.stopPlayback()
    }
}

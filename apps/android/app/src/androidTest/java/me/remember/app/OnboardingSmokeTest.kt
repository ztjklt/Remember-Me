package me.remember.app

import androidx.activity.compose.setContent
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.AudioCaptureService
import me.remember.app.data.repository.AudioRecording
import me.remember.app.data.repository.EpisodeFlow
import me.remember.app.data.repository.EpisodeMemoryRepository
import me.remember.app.data.repository.HttpEpisodeGateway
import me.remember.app.navigation.RememberMeApp
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalTestApi::class)
class OnboardingSmokeTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun onboardingReachesCaptureWithoutStartingMicrophone() {
        val audioService = OnboardingAudioCaptureService()
        val memories = EpisodeMemoryRepository()
        composeRule.activity.setContent {
            RememberMeTheme { RememberMeApp(audioService, memories, EpisodeFlow(HttpEpisodeGateway(), memories)) }
        }

        composeRule.waitUntilAtLeastOneExists(hasText("开始"), 3_000)
        composeRule.onNodeWithText("开始").performClick()
        composeRule.onNodeWithText("继续").performClick()
        composeRule.onNodeWithText("同意并继续").performClick()
        composeRule.onNodeWithText("开始说").performClick()

        composeRule.onNodeWithText("我在听。").assertExists()
        composeRule.onNodeWithTag("capture.recordingConsent").assertExists()
    }
}

private class OnboardingAudioCaptureService : AudioCaptureService {
    override suspend fun start(): AudioRecording = error("Onboarding must not start the microphone")
    override suspend fun pause() = error("Onboarding must not pause a recording")
    override suspend fun resume() = error("Onboarding must not resume a recording")
    override suspend fun stop(): AudioRecording = error("Onboarding must not stop a recording")
    override fun stopIfActive(): AudioRecording? = null
    override fun elapsedMillis(): Long = 0L
    override fun latestRecording(): AudioRecording? = null
    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) =
        error("Onboarding must not play a recording")
    override fun stopPlayback() = Unit
}

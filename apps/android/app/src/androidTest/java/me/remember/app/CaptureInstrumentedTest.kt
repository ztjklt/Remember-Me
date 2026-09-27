package me.remember.app

import android.Manifest
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.MutableStateFlow
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.*
import me.remember.app.feature.*
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CaptureInstrumentedTest {
    @get:Rule val composeRule = createAndroidComposeRule<MainActivity>()
    private lateinit var service: UiTestAudio
    @Before fun setUp() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.grantRuntimePermission(instrumentation.targetContext.packageName, Manifest.permission.RECORD_AUDIO)
        service = UiTestAudio()
        val model = MobileViewModel(service)
        composeRule.activity.setContent { RememberMeTheme { CapturePage(model, {}, {}) } }
    }
    @Test fun consentThenPauseResumeSaveAndRealStatePlayer() {
        composeRule.onNodeWithTag("capture.start").performClick()
        assertEquals(0, service.startCalls)
        composeRule.onNodeWithText("同意并开始").performClick()
        composeRule.onNodeWithTag("capture.pause").performClick()
        composeRule.onNodeWithTag("capture.resume").performClick()
        composeRule.onNodeWithTag("capture.stop").performClick()
        composeRule.onNodeWithText("录音已保存在手机").assertExists()
        composeRule.onNodeWithTag("audio.play").performScrollTo().performClick()
        composeRule.onNodeWithContentDescription("暂停原音").assertExists()
        composeRule.onNodeWithTag("audio.play").performClick()
        composeRule.onNodeWithContentDescription("播放原音").assertExists()
        assertEquals(1, service.startCalls)
        assertEquals(1, service.pauseCalls)
        assertEquals(1, service.resumeCalls)
        assertEquals(1, service.stopCalls)
    }
    @Test fun microphoneFailureOffersRetry() {
        service.failStart = true
        composeRule.onNodeWithTag("capture.start").performClick()
        composeRule.onNodeWithText("同意并开始").performClick()
        composeRule.onNodeWithText("测试麦克风启动失败").assertExists()
        composeRule.onNodeWithTag("capture.start").assertIsEnabled()
    }
}
internal class UiTestAudio : AudioCaptureService {
    val archive = MutableStateFlow<List<AudioRecording>>(emptyList())
    override val playback = MutableStateFlow(PlaybackState())
    var startCalls = 0; var pauseCalls = 0; var resumeCalls = 0; var stopCalls = 0
    var failStart = false
    val saved = AudioRecording("/private/test.m4a", 2500, "audio/mp4", 12345, 44100, 1, "2026-09-27T00:00:00Z", title="测试录音")
    override fun observeRecordings() = archive
    override fun recordings() = archive.value
    override fun updateRecording(recording: AudioRecording) { archive.value = archive.value.filterNot { it.audioPath == recording.audioPath } + recording }
    override fun deleteMemory(recording: AudioRecording, memoryId: String) = updateRecording(recording.copy(memories=recording.memories.filterNot { it.id==memoryId }))
    override suspend fun start(): AudioRecording { startCalls++; check(!failStart) { "测试麦克风启动失败" }; return saved }
    override suspend fun pause() { pauseCalls++ }
    override suspend fun resume() { resumeCalls++ }
    override suspend fun stop(): AudioRecording { stopCalls++; updateRecording(saved); return saved }
    override fun elapsedMillis() = saved.durationMillis
    override fun latestRecording() = archive.value.firstOrNull()
    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) { playback.value = PlaybackState(recording.audioPath,true,durationMillis=recording.durationMillis) }
    override fun pausePlayback() { playback.value=playback.value.copy(playing=false) }
    override fun resumePlayback() { playback.value=playback.value.copy(playing=true) }
    override fun stopPlayback() { playback.value=PlaybackState() }
}

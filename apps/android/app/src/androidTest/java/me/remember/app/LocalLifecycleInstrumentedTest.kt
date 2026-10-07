package me.remember.app

import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import me.remember.app.data.local.*
import me.remember.app.data.repository.AudioRecording
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LocalLifecycleInstrumentedTest {
    @Test fun recreationRetainsUnsavedConfigurationAndCaptureHandoffInMemory() {
        val draft = LocalModelSettings(ModelEndpoint("https://speech.test", "speech-test", "synthetic-speech-key"),
            ModelEndpoint("https://language.test", "language-test", "synthetic-language-key"), SpeechProtocol.CHAT_COMPLETIONS)
        val recording = AudioRecording("/synthetic.m4a", 1000, "audio/mp4", 100, 44100, 1, "2026-01-01T00:00:00Z")
        ActivityScenario.launch(MainActivity::class.java).use { activity ->
            activity.onActivity {
                ViewModelProvider(it)[LocalAgentSession::class.java].modelDraft = draft
                ViewModelProvider(it)[CaptureFlowViewModel::class.java].recording = recording
            }
            activity.recreate()
            activity.onActivity {
                assertEquals(draft, ViewModelProvider(it)[LocalAgentSession::class.java].modelDraft)
                assertEquals(recording, ViewModelProvider(it)[CaptureFlowViewModel::class.java].recording)
            }
        }
    }
}

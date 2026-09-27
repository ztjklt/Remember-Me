package me.remember.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.data.repository.MemoryRepository
import me.remember.app.data.repository.LocalMemoryRepository
import me.remember.app.navigation.RememberMeApp
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.UnisoundSpeechToTextService
import me.remember.app.data.repository.DeepSeekTitleGenerator
import me.remember.app.data.repository.LocalTitleGenerator
import me.remember.app.data.repository.LocalAsrService
import me.remember.app.data.repository.AndroidSherpaOnnxAsrService
import me.remember.app.data.repository.DeepSeekMemoryExtractor
import me.remember.app.data.repository.MemoryAgentOrchestrator
import me.remember.app.data.repository.LocalAgentStateStore

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val audioCaptureService = AndroidAudioCaptureService(applicationContext)
        val memoryRepository: MemoryRepository = LocalMemoryRepository(audioCaptureService)
        val asrKey = BuildConfig.UNISOUND_API_KEY
        val titleGenerator = BuildConfig.DEEPSEEK_API_KEY.takeIf { it.isNotBlank() }
            ?.let { DeepSeekTitleGenerator(it, BuildConfig.DEEPSEEK_TITLE_MODEL) }
            ?: LocalTitleGenerator()
        val speechToTextService = asrKey.takeIf { it.isNotBlank() }
            ?.let { UnisoundSpeechToTextService(it) }
        val localAsrService: LocalAsrService = AndroidSherpaOnnxAsrService(applicationContext)
        val memoryExtractor = BuildConfig.DEEPSEEK_API_KEY.takeIf { it.isNotBlank() }
            ?.let { DeepSeekMemoryExtractor(it, BuildConfig.DEEPSEEK_TITLE_MODEL) }
        val agentStateStore = LocalAgentStateStore(applicationContext)
        val orchestrator = memoryExtractor?.let { MemoryAgentOrchestrator(localAsrService, titleGenerator, it, agentStateStore) }
        setContent { RememberMeTheme { RememberMeApp(audioCaptureService, memoryRepository, speechToTextService, localAsrService, titleGenerator, orchestrator) } }
    }
}

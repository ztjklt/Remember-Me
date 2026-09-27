package me.remember.app.navigation

import androidx.compose.runtime.*
import androidx.navigation.compose.*
import me.remember.app.data.repository.AudioCaptureService
import me.remember.app.data.repository.MemoryRepository
import me.remember.app.data.repository.AudioRecording
import me.remember.app.data.repository.SpeechToTextService
import me.remember.app.data.repository.LocalAsrService
import me.remember.app.data.repository.TitleGenerator
import me.remember.app.data.repository.MemoryAgentOrchestrator
import android.net.Uri
import java.net.URLDecoder
import me.remember.app.feature.*

@Composable fun RememberMeApp(audioCaptureService: AudioCaptureService, memoryRepository: MemoryRepository, speechToTextService: SpeechToTextService? = null, localAsrService: LocalAsrService? = null, titleGenerator: TitleGenerator? = null, orchestrator: MemoryAgentOrchestrator? = null){
    val nav=rememberNavController()
    // The current product surface starts at the ASCII-designed portrait dashboard.
    // Recording and ASR remain internal capabilities, not the primary navigation.
    val startDestination = Routes.Home
    NavHost(nav,startDestination){
        composable(Routes.Splash){SplashScreen{nav.navigate(Routes.Welcome){popUpTo(Routes.Splash){inclusive=true}}}}
        composable(Routes.Welcome){WelcomeScreen{nav.navigate(Routes.Explain)}}
        composable(Routes.Explain){ExplanationScreen{nav.navigate(Routes.Consent)}}
        composable(Routes.Consent){ConsentScreen{nav.navigate(Routes.Introduce)}}
        composable(Routes.Introduce){IntroduceScreen{nav.navigate(Routes.Recording)}}
composable(Routes.Recording){RecordingScreen(audioCaptureService, speechToTextService, localAsrService, titleGenerator, orchestrator, openDetail = { recording -> nav.navigate("audio/${Uri.encode(recording.audioPath)}") })}
        composable(Routes.AudioDetail){ entry ->
            val path = URLDecoder.decode(entry.arguments?.getString("path").orEmpty(), "UTF-8")
            val recording = audioCaptureService.recordings().firstOrNull { it.audioPath == path }
            if (recording != null) AudioDetailScreen(recording, audioCaptureService, speechToTextService, localAsrService, titleGenerator, orchestrator) { nav.popBackStack() }
        }
        composable(Routes.Processing){ProcessingScreen{nav.navigate(Routes.Birth)}}
        composable(Routes.Birth){TwinBirthScreen{nav.navigate(Routes.Voice)}}
        composable(Routes.Voice){VoiceSeedScreen{nav.navigate(Routes.Home){popUpTo(Routes.Welcome){inclusive=true}}}}
        composable(Routes.Home){PortraitScreen(nav::navigate)}
        composable(Routes.Portrait){PortraitScreen(nav::navigate)}
        composable(Routes.Graph){GraphDashboardScreen(nav::navigate)}
        composable(Routes.Agents){SimpleSectionScreen("Agents", "查看记忆、画像和回答所经过的智能分工", nav::popBackStack)}
        composable(Routes.Me){SimpleSectionScreen("我", "隐私、模型和数据管理", nav::popBackStack)}
        composable(Routes.Memories){MemoriesScreen(memoryRepository){nav.popBackStack()}}
        composable(Routes.Twin){TwinScreen{nav.popBackStack()}}
        composable(Routes.Calibration){CalibrationScreen{nav.popBackStack()}}
        composable(Routes.Handover){HandoverScreen{nav.popBackStack()}}
        composable(Routes.Legacy){LegacyHomeScreen{nav.navigate(Routes.Twin)}}
        composable(Routes.Debug){DemoMenuScreen(nav::navigate){nav.popBackStack()}}
    }
}

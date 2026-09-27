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
import androidx.compose.ui.platform.LocalContext
import java.net.URLDecoder
import me.remember.app.feature.*
import me.remember.app.ui.components.LocalHomeNavigation

@Composable fun RememberMeApp(audioCaptureService: AudioCaptureService, memoryRepository: MemoryRepository, speechToTextService: SpeechToTextService? = null, localAsrService: LocalAsrService? = null, titleGenerator: TitleGenerator? = null, orchestrator: MemoryAgentOrchestrator? = null){
    val nav=rememberNavController()
    val context = LocalContext.current
    val onboardingComplete = remember {
        context.getSharedPreferences("remember_me_state", android.content.Context.MODE_PRIVATE)
            .getBoolean("onboarding_complete", false)
    }
    val startDestination = Routes.Splash
    CompositionLocalProvider(LocalHomeNavigation provides {
        context.getSharedPreferences("remember_me_state", android.content.Context.MODE_PRIVATE).edit().putBoolean("onboarding_complete", true).apply()
        nav.navigate(Routes.Portrait){ popUpTo(Routes.Splash){ inclusive=true } }
    }) { NavHost(nav,startDestination){
        composable(Routes.Splash){SplashScreen(
            next = {
                val destination = if (onboardingComplete) Routes.Home else Routes.Welcome
                nav.navigate(destination){popUpTo(Routes.Splash){inclusive=true}}
            },
            home = { nav.navigate(Routes.Home){popUpTo(Routes.Splash){inclusive=true}} }
        )}
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
        composable(Routes.Voice){VoiceSeedScreen{
            context.getSharedPreferences("remember_me_state", android.content.Context.MODE_PRIVATE)
                .edit().putBoolean("onboarding_complete", true).apply()
            nav.navigate(Routes.Home){popUpTo(Routes.Splash){inclusive=true}}
        }}
        composable(Routes.Home){PortraitScreen(nav::navigate)}
        composable(Routes.Portrait){PortraitScreen(nav::navigate)}
        composable(Routes.Graph){GraphDashboardScreen(nav::navigate)}
        composable(Routes.Agents){AgentsDashboardScreen(nav::navigate)}
        composable(Routes.Me){MeDashboardScreen(nav::navigate)}
        composable(Routes.Memories){MemoryDashboardScreen(memoryRepository, nav::navigate)}
        composable(Routes.Twin){ChatHistoryScreen(nav::popBackStack, nav::navigate)}
        composable(Routes.Calibration){CalibrationScreen{nav.popBackStack()}}
        composable(Routes.Handover){HandoverScreen{nav.popBackStack()}}
        composable(Routes.Legacy){LegacyHomeScreen{nav.navigate(Routes.Twin)}}
        composable(Routes.Debug){DemoMenuScreen(nav::navigate){nav.popBackStack()}}
    } }
}

package me.remember.app.navigation

import androidx.compose.runtime.*
import androidx.navigation.compose.*
import me.remember.app.data.repository.AgentRepository
import me.remember.app.data.repository.EpisodeUiState
import me.remember.app.data.repository.AudioCaptureService
import me.remember.app.data.repository.AudioRecording
import me.remember.app.data.repository.EpisodeFlow
import me.remember.app.data.repository.MemoryRepository
import me.remember.app.feature.*
import kotlinx.coroutines.launch

@Composable fun RememberMeApp(
    audioCaptureService: AudioCaptureService,
    memoryRepository: MemoryRepository,
    episodeFlow: EpisodeFlow,
    agentRepository: AgentRepository
){
    val nav=rememberNavController()
    val scope=rememberCoroutineScope()
    var recordingForUpload by remember { mutableStateOf<AudioRecording?>(null) }
    val startDestination = remember(audioCaptureService) {
        if (audioCaptureService.latestRecording() != null) Routes.Recording else Routes.Splash
    }
    NavHost(nav,startDestination){
        composable(Routes.Splash){SplashScreen{nav.navigate(Routes.Welcome){popUpTo(Routes.Splash){inclusive=true}}}}
        composable(Routes.Welcome){WelcomeScreen{nav.navigate(Routes.Explain)}}
        composable(Routes.Explain){ExplanationScreen{nav.navigate(Routes.Consent)}}
        composable(Routes.Consent){ConsentScreen{nav.navigate(Routes.Introduce)}}
        composable(Routes.Introduce){IntroduceScreen{nav.navigate(Routes.Recording)}}
        composable(Routes.Recording){RecordingScreen(audioCaptureService, onUnderstanding = { nav.navigate(Routes.Understanding) }) { recording ->
            recordingForUpload = recording
            nav.navigate(Routes.Connection)
        }}
        composable(Routes.Connection){
            val recording = recordingForUpload
            if (recording != null) BackendConnectionScreen(recording, back = { nav.popBackStack() }, initialConnection = agentRepository.currentConnection()) { settings ->
                nav.navigate(Routes.Processing)
                scope.launch {
                    agentRepository.bind(settings)
                    if (settings.subjectSingleSpeaker) agentRepository.enable(settings)
                    episodeFlow.submit(recording, settings)
                    if (settings.subjectSingleSpeaker && episodeFlow.state.value is EpisodeUiState.Ready) agentRepository.refresh()
                }
            }
        }
        composable(Routes.Processing){
            val state by episodeFlow.state.collectAsState()
            ProcessingScreen(
                state = state,
                back = { nav.popBackStack() },
                retry = { scope.launch {
                    episodeFlow.retry()
                    if (episodeFlow.state.value is EpisodeUiState.Ready && agentRepository.state.value.configured) agentRepository.refresh()
                } },
                showUnderstanding = { nav.navigate(Routes.Understanding) },
                showMemories = { nav.navigate(Routes.Memories) }
            )
        }
        composable(Routes.Understanding){
            val episode by episodeFlow.state.collectAsState()
            AgentScreen(agentRepository, { nav.popBackStack() }, { nav.navigate(Routes.Recording) }, (episode as? EpisodeUiState.Ready)?.episodeId)
        }
        composable(Routes.Birth){TwinBirthScreen{nav.navigate(Routes.Voice)}}
        composable(Routes.Voice){VoiceSeedScreen{nav.navigate(Routes.Home){popUpTo(Routes.Welcome){inclusive=true}}}}
        composable(Routes.Home){CreatorHomeScreen(memoryRepository,nav::navigate)}
        composable(Routes.Memories){MemoriesScreen(memoryRepository){nav.popBackStack()}}
        composable(Routes.Twin){AgentScreen(agentRepository, { nav.popBackStack() }, { nav.navigate(Routes.Recording) })}
        composable(Routes.Calibration){AgentScreen(agentRepository, { nav.popBackStack() }, { nav.navigate(Routes.Recording) })}
        composable(Routes.Handover){HandoverScreen{nav.popBackStack()}}
        composable(Routes.Legacy){LegacyHomeScreen{nav.navigate(Routes.Twin)}}
        composable(Routes.Debug){DemoMenuScreen(nav::navigate){nav.popBackStack()}}
    }
}

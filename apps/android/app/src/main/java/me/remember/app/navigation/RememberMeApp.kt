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
import me.remember.app.LocalAgentSession
import me.remember.app.CaptureFlowViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import me.remember.app.ui.components.RmPage
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton

@Composable fun RememberMeApp(
    audioCaptureService: AudioCaptureService,
    memoryRepository: MemoryRepository,
    episodeFlow: EpisodeFlow,
    agentRepository: AgentRepository,
    local: LocalAgentSession? = null
){
    val localState = local?.state?.collectAsState()?.value
    val localMode = localState?.localMode == true
    if (localMode && localState?.ready != true) {
        RmPage {
            Text(localState?.error ?: "正在打开手机资料…")
            TextButton({ local?.setLocalMode(false) }) { Text("使用电脑 Backend 模式") }
        }
        return
    }
    val selectedMemories = if (localMode) local!!.memories!! else memoryRepository
    val selectedAgent = if (localMode) local!!.repository!! else agentRepository
    val nav=rememberNavController()
    val scope=rememberCoroutineScope()
    val captureFlow: CaptureFlowViewModel = viewModel()
    val startDestination = remember(audioCaptureService) {
        if (audioCaptureService.latestRecording() != null) Routes.Recording else Routes.Splash
    }
    NavHost(nav,startDestination){
        composable(Routes.Splash){SplashScreen{nav.navigate(Routes.Welcome){popUpTo(Routes.Splash){inclusive=true}}}}
        composable(Routes.Welcome){WelcomeScreen{nav.navigate(Routes.Explain)}}
        composable(Routes.Explain){ExplanationScreen{nav.navigate(Routes.Consent)}}
        composable(Routes.Consent){ConsentScreen{nav.navigate(Routes.Introduce)}}
        composable(Routes.Introduce){IntroduceScreen{nav.navigate(Routes.Recording)}}
        composable("local-recordings") { RecordingLibraryScreen(local!!, audioCaptureService, { nav.popBackStack() }) {
            captureFlow.recording = it; nav.navigate(Routes.Connection)
        } }
        composable("local-model-settings") { LocalSettingsScreen(local!!, audioCaptureService.latestRecording()) { nav.popBackStack() } }
        composable(Routes.Recording){RecordingScreen(audioCaptureService, onUnderstanding = { nav.navigate(Routes.Understanding) },
            onLibrary = if (localMode) ({ nav.navigate("local-recordings") }) else null,
            onHome = { nav.navigate(Routes.Home) },
            onSettings = if (localMode) ({ nav.navigate("local-model-settings") }) else null,
            onSwitchMode = local?.let { { it.setLocalMode(!localMode) } },
            modeLabel = if (localMode) "手机独立模式" else "电脑 Backend 模式") { recording ->
            captureFlow.recording = recording
            nav.navigate(Routes.Connection)
        }}
        composable(Routes.Connection){
            val recording = captureFlow.recording
            if (recording != null && localMode) LocalCaptureScreen(local!!, recording, { nav.popBackStack() },
                { nav.navigate("local-model-settings") }) { local.capture(recording); nav.navigate(Routes.Processing) }
            else if (recording != null) BackendConnectionScreen(recording, back = { nav.popBackStack() }, initialConnection = agentRepository.currentConnection()) { settings ->
                nav.navigate(Routes.Processing)
                scope.launch {
                    agentRepository.bind(settings)
                    if (settings.subjectSingleSpeaker) agentRepository.enable(settings)
                    episodeFlow.submit(recording, settings)
                    if (settings.subjectSingleSpeaker && episodeFlow.state.value is EpisodeUiState.Ready) agentRepository.refresh()
                }
            }
            else RmPage {
                Text("待处理录音未恢复，请返回录音页选择已保存的录音。")
                TextButton({ nav.navigate(Routes.Recording) }) { Text("返回录音") }
            }
        }
        composable(Routes.Processing){
            if (localMode) LocalProcessingScreen(local!!, { nav.popBackStack() }, { nav.navigate("local-model-settings") }, { nav.navigate(Routes.Understanding) })
            else {
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
        }
        composable(Routes.Understanding){
            val episode by episodeFlow.state.collectAsState()
            AgentScreen(selectedAgent, { nav.popBackStack() }, { nav.navigate(Routes.Recording) },
                if (localMode) null else (episode as? EpisodeUiState.Ready)?.episodeId, localMode, localState?.busy == true) {
                LocalAgentStatus(local!!) { nav.navigate("local-model-settings") }
            }
        }
        composable(Routes.Birth){ if (me.remember.app.BuildConfig.DEBUG) TwinBirthScreen{nav.navigate(Routes.Voice)} }
        composable(Routes.Voice){ if (me.remember.app.BuildConfig.DEBUG) VoiceSeedScreen{nav.navigate(Routes.Home){popUpTo(Routes.Welcome){inclusive=true}}}}
        composable(Routes.Home){CreatorHomeScreen(selectedMemories,nav::navigate)}
        composable(Routes.Memories){MemoriesScreen(selectedMemories){nav.popBackStack()}}
        composable(Routes.Twin){AgentScreen(selectedAgent, { nav.popBackStack() }, { nav.navigate(Routes.Recording) }, localMode = localMode, externalBusy = localState?.busy == true) {
            LocalAgentStatus(local!!) { nav.navigate("local-model-settings") }
        }}
        composable(Routes.Calibration){AgentScreen(selectedAgent, { nav.popBackStack() }, { nav.navigate(Routes.Recording) }, localMode = localMode, externalBusy = localState?.busy == true) {
            LocalAgentStatus(local!!) { nav.navigate("local-model-settings") }
        }}
        composable(Routes.Handover){HandoverScreen{nav.popBackStack()}}
        composable(Routes.Legacy){ if (me.remember.app.BuildConfig.DEBUG) LegacyHomeScreen{nav.navigate(Routes.Twin)}}
        composable(Routes.Debug){DemoMenuScreen(nav::navigate){nav.popBackStack()}}
    }
}

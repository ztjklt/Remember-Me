package me.remember.app.navigation

import androidx.compose.runtime.*
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.res.stringResource
import me.remember.app.BuildConfig
import me.remember.app.R
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Scaffold
import androidx.compose.ui.Modifier
import me.remember.app.data.local.remotePortrait

@Composable fun RememberMeApp(
    audioCaptureService: AudioCaptureService,
    memoryRepository: MemoryRepository,
    episodeFlow: EpisodeFlow,
    agentRepository: AgentRepository,
    local: LocalAgentSession? = null
){
    val localState = local?.state?.collectAsState()?.value
    val localMode = localState?.localMode == true
    val recoveryExport = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/plain")) { uri ->
        uri?.let { local?.exportRecovery(it) }
    }
    if (localMode && localState?.ready != true) {
        RmPage {
            Text(localState?.error ?: stringResource(R.string.local_opening))
            localState?.message?.let { Text(it) }
            if (localState?.error != null) TextButton({ recoveryExport.launch("remember-me-originals.txt") }, enabled = localState.busy.not()) { Text(stringResource(R.string.export_originals)) }
            TextButton({ local?.setLocalMode(false) }) { Text(stringResource(R.string.remote_mode)) }
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
    val entry by nav.currentBackStackEntryAsState()
    val agentState by selectedAgent.state.collectAsState()
    val mainPages = setOf(Routes.Recording, Routes.Home, Routes.Memories, Routes.Understanding, Routes.Twin, Routes.Calibration,
        Routes.Connection, Routes.Processing, "local-portrait", "local-recordings", "local-model-settings", "remote-settings")
    Scaffold(bottomBar = {
        if (entry?.destination?.route in mainPages) Row(Modifier.fillMaxWidth()) {
            val settingsRoute = if (localMode) "local-model-settings" else "remote-settings"
            listOf(R.string.nav_record to Routes.Recording, R.string.nav_memory to Routes.Memories,
                R.string.nav_portrait to "local-portrait", R.string.nav_ask to Routes.Twin, R.string.nav_settings to settingsRoute).forEach { (label, route) ->
                TextButton({ nav.navigate(route) { launchSingleTop = true } }, modifier = Modifier.weight(1f)) { Text(stringResource(label)) }
            }
        }
    }) { padding -> NavHost(nav,startDestination, modifier = Modifier.padding(padding)){
        composable(Routes.Splash){SplashScreen{nav.navigate(Routes.Welcome){popUpTo(Routes.Splash){inclusive=true}}}}
        composable(Routes.Welcome){WelcomeScreen{nav.navigate(Routes.Explain)}}
        composable(Routes.Explain){ExplanationScreen{nav.navigate(Routes.Consent)}}
        composable(Routes.Consent){ConsentScreen{nav.navigate(Routes.Introduce)}}
        composable(Routes.Introduce){IntroduceScreen{nav.navigate(Routes.Recording)}}
        composable("local-recordings") { if (localMode) RecordingLibraryScreen(local!!, audioCaptureService, { nav.popBackStack() }) {
            captureFlow.recording = it; nav.navigate(Routes.Connection)
        } else LocalModeUnavailable { nav.navigate(Routes.Recording) } }
        composable("local-model-settings") { if (localMode) LocalSettingsScreen(local!!, audioCaptureService.latestRecording()) { nav.popBackStack() }
            else LocalModeUnavailable { nav.navigate(Routes.Recording) } }
        composable("remote-settings") { RmPage {
            TextButton({ nav.popBackStack() }) { Text(stringResource(R.string.back)) }
            Text(stringResource(R.string.remote_settings))
            AgentConnection(agentRepository)
            agentState.error?.let { Text(it) }
        } }
        composable("local-portrait") { if (localMode) LocalPortraitScreen(local!!, { nav.popBackStack() }, { nav.navigate(Routes.Understanding) })
            else PortraitScreen(remotePortrait(agentState), agentState.busy, agentState.error,
                { nav.popBackStack() }, { nav.navigate(Routes.Understanding) }, remoteMode = true) }
        composable(Routes.Recording){RecordingScreen(audioCaptureService, onUnderstanding = { nav.navigate(Routes.Understanding) },
            onLibrary = if (localMode) ({ nav.navigate("local-recordings") }) else null,
            onHome = { nav.navigate(Routes.Home) },
            onSettings = if (localMode) ({ nav.navigate("local-model-settings") }) else null,
            onSwitchMode = local?.takeIf { BuildConfig.LOCAL_AGENT_ENABLED }?.let { { it.setLocalMode(!localMode) } },
            modeLabel = stringResource(if (localMode) R.string.local_mode else R.string.remote_mode)) { recording ->
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
                Text(stringResource(R.string.missing_recording))
                TextButton({ nav.navigate(Routes.Recording) }) { Text(stringResource(R.string.return_recording)) }
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
                LocalAgentControls(local!!, { nav.navigate("local-model-settings") }, { nav.navigate("local-portrait") })
            }
        }
        composable(Routes.Birth){ if (me.remember.app.BuildConfig.DEBUG) TwinBirthScreen{nav.navigate(Routes.Voice)} }
        composable(Routes.Voice){ if (me.remember.app.BuildConfig.DEBUG) VoiceSeedScreen{nav.navigate(Routes.Home){popUpTo(Routes.Welcome){inclusive=true}}}}
        composable(Routes.Home){CreatorHomeScreen(selectedMemories,nav::navigate)}
        composable(Routes.Memories){
            LaunchedEffect(localMode, agentState.snapshot?.revision, agentState.busy) {
                if (localMode && !agentState.busy) local?.loadPortrait()
            }
            MemoriesScreen(selectedMemories, if (localMode) local?.portrait else null,
                localMode, localState?.busy == true, if (localMode) ({ if (localState?.pending == true) local?.retry() else local?.rebuildMemories() }) else null,
                if (localMode) localState?.error else agentState.error) { nav.popBackStack() }
        }
        composable(Routes.Twin){AgentScreen(selectedAgent, { nav.popBackStack() }, { nav.navigate(Routes.Recording) }, localMode = localMode, externalBusy = localState?.busy == true) {
            LocalAgentControls(local!!, { nav.navigate("local-model-settings") }, { nav.navigate("local-portrait") })
        }}
        composable(Routes.Calibration){AgentScreen(selectedAgent, { nav.popBackStack() }, { nav.navigate(Routes.Recording) }, localMode = localMode, externalBusy = localState?.busy == true) {
            LocalAgentControls(local!!, { nav.navigate("local-model-settings") }, { nav.navigate("local-portrait") })
        }}
        composable(Routes.Handover){HandoverScreen{nav.popBackStack()}}
        composable(Routes.Legacy){ if (me.remember.app.BuildConfig.DEBUG) LegacyHomeScreen{nav.navigate(Routes.Twin)}}
        composable(Routes.Debug){DemoMenuScreen(nav::navigate){nav.popBackStack()}}
    } }
}

@Composable private fun LocalModeUnavailable(back: () -> Unit) = RmPage {
    Text(stringResource(R.string.local_mode_unavailable))
    TextButton(back) { Text(stringResource(R.string.back_recording)) }
}

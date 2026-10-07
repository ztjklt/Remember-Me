package me.remember.app.feature

import androidx.compose.ui.res.stringResource
import me.remember.app.R
import androidx.compose.material3.*
import androidx.compose.runtime.*
import me.remember.app.LocalAgentSession
import me.remember.app.data.repository.AudioCaptureService
import me.remember.app.data.repository.AudioRecording
import me.remember.app.ui.components.RmPage
import java.io.File

@Composable
fun RecordingLibraryScreen(session: LocalAgentSession, audio: AudioCaptureService, back: () -> Unit, process: (AudioRecording) -> Unit) {
    val playbackFailure = stringResource(R.string.playback_failure)
    val state by session.state.collectAsState()
    var deleting by remember { mutableStateOf<AudioRecording?>(null) }
    var clearing by remember { mutableStateOf(false) }
    var playbackError by remember { mutableStateOf<String?>(null) }
    var showVersions by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { session.loadLibrary() }
    DisposableEffect(Unit) { onDispose { audio.stopPlayback() } }
    RmPage {
        TextButton(back) { Text(stringResource(R.string.back)) }
        Text(stringResource(R.string.recording_library), style = MaterialTheme.typography.headlineLarge)
        Text(stringResource(R.string.recording_retention_notice))
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        playbackError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        if (state.busy) LinearProgressIndicator()
        session.recordings.forEach { item ->
            Text(stringResource(R.string.recording_status, item.recording.createdAt, item.recording.durationMillis / 1000, item.status))
            if (item.excerpt.isNotEmpty()) Text(item.excerpt)
            if (File(item.recording.audioPath).isFile) TextButton({
                runCatching { audio.play(item.recording, {}, { playbackError = it }) }.onFailure { playbackError = playbackFailure }
            }, enabled = !state.busy) { Text(stringResource(R.string.play_recording)) }
            TextButton({ audio.stopPlayback() }) { Text(stringResource(R.string.stop_playback)) }
            if (item.status in setOf("未处理", "待理解")) TextButton({ process(item.recording) }, enabled = !state.busy) { Text(stringResource(R.string.process_recording)) }
            if (item.status != "已删除") TextButton({ deleting = item.recording }, enabled = !state.busy) { Text(stringResource(R.string.delete_recording)) }
        }
        TextButton({ showVersions = !showVersions }) { Text(stringResource(R.string.understanding_history)) }
        if (showVersions) session.versions.asReversed().forEach { version ->
            Text(stringResource(R.string.revision_number, version.getInt("revision")))
            val traits = version.getJSONArray("traits")
            for (i in 0 until traits.length()) Text(traits.getJSONObject(i).getString("statement"))
        }
        TextButton({ clearing = true }, enabled = !state.busy) { Text(stringResource(R.string.clear_local_data)) }
    }
    if (deleting != null || clearing) AlertDialog(onDismissRequest = { deleting = null; clearing = false },
        title = { Text(if (clearing) stringResource(R.string.clear_local_title) else stringResource(R.string.delete_recording_title)) },
        text = { Text(if (clearing) stringResource(R.string.clear_local_notice) else stringResource(R.string.delete_recording_notice)) },
        confirmButton = { TextButton({
            audio.stopPlayback()
            if (clearing) session.clearLocalData() else deleting?.let(session::deleteRecording)
            deleting = null; clearing = false
        }) { Text(stringResource(R.string.confirm_delete)) } }, dismissButton = { TextButton({ deleting = null; clearing = false }) { Text(stringResource(R.string.cancel)) } })
}

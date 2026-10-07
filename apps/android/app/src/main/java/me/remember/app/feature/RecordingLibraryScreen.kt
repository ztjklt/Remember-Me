package me.remember.app.feature

import androidx.compose.material3.*
import androidx.compose.runtime.*
import me.remember.app.LocalAgentSession
import me.remember.app.data.repository.AudioCaptureService
import me.remember.app.data.repository.AudioRecording
import me.remember.app.ui.components.RmPage
import java.io.File

@Composable
fun RecordingLibraryScreen(session: LocalAgentSession, audio: AudioCaptureService, back: () -> Unit, process: (AudioRecording) -> Unit) {
    val state by session.state.collectAsState()
    var deleting by remember { mutableStateOf<AudioRecording?>(null) }
    var clearing by remember { mutableStateOf(false) }
    var playbackError by remember { mutableStateOf<String?>(null) }
    var showVersions by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { session.loadLibrary() }
    DisposableEffect(Unit) { onDispose { audio.stopPlayback() } }
    RmPage {
        TextButton(back) { Text("← 返回") }
        Text("我录过的", style = MaterialTheme.typography.headlineLarge)
        Text("不自动删除录音。删除会清除本机音频和原文，并使依赖的问答失效；电脑副本不受影响。")
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        playbackError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        if (state.busy) LinearProgressIndicator()
        session.recordings.forEach { item ->
            Text("${item.recording.createdAt} · ${item.recording.durationMillis / 1000} 秒 · ${item.status}")
            if (item.excerpt.isNotEmpty()) Text(item.excerpt)
            if (File(item.recording.audioPath).isFile) TextButton({
                runCatching { audio.play(item.recording, {}, { playbackError = it }) }.onFailure { playbackError = "播放失败，文件可能已损坏。" }
            }, enabled = !state.busy) { Text("播放录音") }
            TextButton({ audio.stopPlayback() }) { Text("停止播放") }
            if (item.status == "未处理") TextButton({ process(item.recording) }, enabled = !state.busy) { Text("处理这段录音") }
            if (item.status != "已删除") TextButton({ deleting = item.recording }, enabled = !state.busy) { Text("删除这段录音") }
        }
        TextButton({ showVersions = !showVersions }) { Text("理解版本历史") }
        if (showVersions) session.versions.asReversed().forEach { version ->
            Text("第 ${version.getInt("revision")} 版")
            val traits = version.getJSONArray("traits")
            for (i in 0 until traits.length()) Text(traits.getJSONObject(i).getString("statement"))
        }
        TextButton({ clearing = true }, enabled = !state.busy) { Text("清除本地数据并退出手机模式") }
    }
    if (deleting != null || clearing) AlertDialog(onDismissRequest = { deleting = null; clearing = false },
        title = { Text(if (clearing) "清除全部本地资料？" else "删除这段录音？") },
        text = { Text(if (clearing) "将删除本机全部录音、理解、问答和加密模型配置。此操作无法撤销。" else "将清除音频与原文，保留不含内容的删除记录，相关问答会失效。此操作无法撤销。") },
        confirmButton = { TextButton({
            audio.stopPlayback()
            if (clearing) session.clearLocalData() else deleting?.let(session::deleteRecording)
            deleting = null; clearing = false
        }) { Text("确认删除") } }, dismissButton = { TextButton({ deleting = null; clearing = false }) { Text("取消") } })
}

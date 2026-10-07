package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import me.remember.app.LocalAgentSession
import me.remember.app.CaptureProgress
import me.remember.app.data.local.*
import me.remember.app.data.repository.AudioRecording
import me.remember.app.ui.components.RmPage

@Composable
fun LocalSettingsScreen(session: LocalAgentSession, recording: AudioRecording?, back: () -> Unit) {
    val state by session.state.collectAsState()
    val draft = session.modelDraft ?: (session.settings ?: LocalModelSettings(
        ModelEndpoint("https://dashscope.aliyuncs.com", "qwen-audio-3.0-asr-flash", ""),
        ModelEndpoint("https://api.deepseek.com", "deepseek-flash", ""), SpeechProtocol.DASHSCOPE))
    fun update(value: LocalModelSettings) { session.modelDraft = value }
    val protocol = draft.protocol
    var consent by remember { mutableStateOf(false) }
    fun config() = draft.copy(speech = draft.speech.copy(baseUrl = draft.speech.baseUrl.trim(), model = draft.speech.model.trim(), apiKey = draft.speech.apiKey.trim()),
        language = draft.language.copy(baseUrl = draft.language.baseUrl.trim(), model = draft.language.model.trim(), apiKey = draft.language.apiKey.trim()))
    RmPage {
        TextButton(back, enabled = !state.busy) { Text("← 返回") }
        Text("手机模型设置", style = MaterialTheme.typography.headlineLarge)
        Text("原文、理解和校正存放在手机；录音发给语音服务，文字材料发给文字模型。无需电脑常开。")
        Text("语音模型", style = MaterialTheme.typography.titleLarge)
        Row {
            RadioButton(protocol == SpeechProtocol.DASHSCOPE, { update(draft.copy(protocol = SpeechProtocol.DASHSCOPE)) }, enabled = !state.busy)
            Text("DashScope 原生")
        }
        Row {
            RadioButton(protocol == SpeechProtocol.CHAT_COMPLETIONS, { update(draft.copy(protocol = SpeechProtocol.CHAT_COMPLETIONS)) }, enabled = !state.busy)
            Text("Chat Completions 音频")
        }
        Text(if (protocol == SpeechProtocol.DASHSCOPE) "原生协议填服务根地址，例如 https://你的服务域名，不带 /compatible-mode/v1。" else "填写兼容接口 Base URL，模型必须支持音频输入。")
        ModelField("语音 Base URL", draft.speech.baseUrl, { update(draft.copy(speech = draft.speech.copy(baseUrl = it))) }, state.busy)
        ModelField("语音 Model", draft.speech.model, { update(draft.copy(speech = draft.speech.copy(model = it))) }, state.busy)
        ModelField("语音 API Key", draft.speech.apiKey, { update(draft.copy(speech = draft.speech.copy(apiKey = it))) }, state.busy, true)
        Text("文字模型 · OpenAI-compatible", style = MaterialTheme.typography.titleLarge)
        ModelField("文字 Base URL", draft.language.baseUrl, { update(draft.copy(language = draft.language.copy(baseUrl = it))) }, state.busy)
        ModelField("文字 Model", draft.language.model, { update(draft.copy(language = draft.language.copy(model = it))) }, state.busy)
        ModelField("文字 API Key", draft.language.apiKey, { update(draft.copy(language = draft.language.copy(apiKey = it))) }, state.busy, true)
        Row { Checkbox(consent, { consent = it }, enabled = !state.busy); Text("同意将本人单人录音及相关文字发给以上模型处理，并在手机保存材料和校正。") }
        Button({ session.save(config(), consent, back) }, enabled = consent && state.ready && !state.busy) { Text("保存并启用手机模式") }
        TextButton({ session.test(config()) }, enabled = consent && state.ready && !state.busy) { Text("测试文字模型") }
        TextButton({ session.test(config(), recording, speech = true) }, enabled = consent && recording != null && state.ready && !state.busy) { Text("用最新录音测试语音模型") }
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        state.message?.let { Text(it) }
        Text("Key 加密保存于本机，不随备份导出。电脑上的旧数据不会自动搬到手机。", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun ModelField(label: String, text: String, change: (String) -> Unit, busy: Boolean, secret: Boolean = false) {
    OutlinedTextField(text, change, label = { Text(label) }, enabled = !busy, singleLine = true,
        visualTransformation = if (secret) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        modifier = Modifier.fillMaxWidth())
}

@Composable
fun LocalAgentStatus(session: LocalAgentSession, settings: () -> Unit) {
    val state by session.state.collectAsState()
    val repo = session.repository
    val agent = repo?.state?.collectAsState()?.value
    LaunchedEffect(agent?.busy, state.ready) { session.syncPending() }
    Text("手机独立模式", style = MaterialTheme.typography.bodySmall)
    TextButton(settings, enabled = !state.busy && agent?.busy != true) { Text("模型设置") }
    if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
    state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    if (state.pending) {
        Text("有尚未完成的任务。继续将使用已保存的原文或校正；取消只停止该任务。")
        state.checkpoint?.let { Text("已保存的文字：$it") }
        Row {
            TextButton({ session.retry() }, enabled = !state.busy && agent?.busy != true) { Text("继续任务") }
            TextButton({ session.cancelPending() }, enabled = !state.busy && agent?.busy != true) { Text("取消任务") }
        }
    }
}

@Composable
fun LocalCaptureScreen(session: LocalAgentSession, recording: AudioRecording, back: () -> Unit, settings: () -> Unit, process: () -> Unit) {
    val state by session.state.collectAsState()
    val configured = session.repository?.state?.collectAsState()?.value?.configured == true
    RmPage {
        TextButton(back) { Text("← 返回录音") }
        Text("处理这段录音", style = MaterialTheme.typography.headlineLarge)
        Text("${recording.createdAt} · ${recording.durationMillis / 1000} 秒")
        Text("保存原文，调用文字模型更新理解。录音仍保留在手机。")
        LocalAgentStatus(session, settings)
        if (!configured || session.settings == null) Text("请先配置模型并确认处理同意。")
        Button(process, enabled = configured && session.settings != null && !state.busy && !state.pending) { Text("开始转写并更新理解") }
    }
}

@Composable
fun LocalProcessingScreen(session: LocalAgentSession, back: () -> Unit, settings: () -> Unit, understanding: () -> Unit) {
    val state by session.state.collectAsState()
    RmPage {
        TextButton(back) { Text("← 返回") }
        Text(when (state.captureProgress) {
            CaptureProgress.RUNNING -> "正在处理录音"
            CaptureProgress.FAILED -> "处理失败"
            CaptureProgress.PAUSED -> "处理已暂停"
            CaptureProgress.COMPLETE -> "处理完成"
            CaptureProgress.IDLE -> "暂无新的处理结果"
        }, style = MaterialTheme.typography.headlineLarge)
        LocalAgentStatus(session, settings)
        if (state.captureProgress == CaptureProgress.FAILED && !state.pending) TextButton({ session.retryCapture() }) { Text("重试处理") }
        state.message?.let { Text(it) }
        Text("处理中建议保持应用打开。若进程被系统结束，再次打开后可继续任务。")
        Button(understanding, enabled = !state.busy) { Text("查看原文与理解") }
    }
}

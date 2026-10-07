package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import me.remember.app.LocalAgentSession
import me.remember.app.data.local.*
import me.remember.app.data.repository.AudioRecording
import me.remember.app.ui.components.RmPage

@Composable
fun LocalSettingsScreen(session: LocalAgentSession, recording: AudioRecording?, back: () -> Unit) {
    val state by session.state.collectAsState()
    val current = session.settings
    var speechUrl by remember(current) { mutableStateOf(current?.speech?.baseUrl ?: "https://dashscope.aliyuncs.com") }
    var speechModel by remember(current) { mutableStateOf(current?.speech?.model ?: "qwen-audio-3.0-asr-flash") }
    var speechKey by remember(current) { mutableStateOf(current?.speech?.apiKey.orEmpty()) }
    var languageUrl by remember(current) { mutableStateOf(current?.language?.baseUrl ?: "https://api.deepseek.com") }
    var languageModel by remember(current) { mutableStateOf(current?.language?.model ?: "deepseek-flash") }
    var languageKey by remember(current) { mutableStateOf(current?.language?.apiKey.orEmpty()) }
    var protocol by remember(current) { mutableStateOf(current?.protocol ?: SpeechProtocol.DASHSCOPE) }
    var consent by remember { mutableStateOf(false) }
    fun config() = LocalModelSettings(ModelEndpoint(speechUrl.trim(), speechModel.trim(), speechKey.trim()),
        ModelEndpoint(languageUrl.trim(), languageModel.trim(), languageKey.trim()), protocol)
    RmPage {
        TextButton(back, enabled = !state.busy) { Text("← 返回") }
        Text("手机模型设置", style = MaterialTheme.typography.headlineLarge)
        Text("原文、理解和校正存放在手机；录音发给语音服务，文字材料发给文字模型。无需电脑常开。")
        Text("语音模型", style = MaterialTheme.typography.titleLarge)
        Row {
            RadioButton(protocol == SpeechProtocol.DASHSCOPE, { protocol = SpeechProtocol.DASHSCOPE }, enabled = !state.busy)
            Text("DashScope 原生")
        }
        Row {
            RadioButton(protocol == SpeechProtocol.CHAT_COMPLETIONS, { protocol = SpeechProtocol.CHAT_COMPLETIONS }, enabled = !state.busy)
            Text("Chat Completions 音频")
        }
        Text(if (protocol == SpeechProtocol.DASHSCOPE) "原生协议填服务根地址，例如 https://你的服务域名，不带 /compatible-mode/v1。" else "填写兼容接口 Base URL，模型必须支持音频输入。")
        ModelField("语音 Base URL", speechUrl, { speechUrl = it }, state.busy)
        ModelField("语音 Model", speechModel, { speechModel = it }, state.busy)
        ModelField("语音 API Key", speechKey, { speechKey = it }, state.busy, true)
        Text("文字模型 · OpenAI-compatible", style = MaterialTheme.typography.titleLarge)
        ModelField("文字 Base URL", languageUrl, { languageUrl = it }, state.busy)
        ModelField("文字 Model", languageModel, { languageModel = it }, state.busy)
        ModelField("文字 API Key", languageKey, { languageKey = it }, state.busy, true)
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
        Text(if (state.busy) "正在处理录音" else if (state.pending) "处理已暂停" else "处理完成", style = MaterialTheme.typography.headlineLarge)
        LocalAgentStatus(session, settings)
        state.message?.let { Text(it) }
        Text("处理中建议保持应用打开。若进程被系统结束，再次打开后可继续任务。")
        Button(understanding, enabled = !state.busy) { Text("查看原文与理解") }
    }
}

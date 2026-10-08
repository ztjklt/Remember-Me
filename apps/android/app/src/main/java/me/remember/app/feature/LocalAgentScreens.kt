package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.res.stringResource
import me.remember.app.R
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
        TextButton(back, enabled = !state.busy) { Text(stringResource(R.string.back)) }
        Text(stringResource(R.string.local_settings_title), style = MaterialTheme.typography.headlineLarge)
        Text(stringResource(R.string.local_settings_explanation))
        Text(stringResource(R.string.speech_model), style = MaterialTheme.typography.titleLarge)
        Row {
            RadioButton(protocol == SpeechProtocol.DASHSCOPE, { update(draft.copy(protocol = SpeechProtocol.DASHSCOPE)) }, enabled = !state.busy)
            Text(stringResource(R.string.speech_native_protocol))
        }
        Row {
            RadioButton(protocol == SpeechProtocol.CHAT_COMPLETIONS, { update(draft.copy(protocol = SpeechProtocol.CHAT_COMPLETIONS)) }, enabled = !state.busy)
            Text(stringResource(R.string.speech_compatible_protocol))
        }
        Text(if (protocol == SpeechProtocol.DASHSCOPE) stringResource(R.string.speech_native_hint) else stringResource(R.string.speech_compatible_hint))
        ModelField(stringResource(R.string.speech_url), draft.speech.baseUrl, { update(draft.copy(speech = draft.speech.copy(baseUrl = it))) }, state.busy)
        ModelField(stringResource(R.string.speech_model_name), draft.speech.model, { update(draft.copy(speech = draft.speech.copy(model = it))) }, state.busy)
        ModelField(stringResource(R.string.speech_key), draft.speech.apiKey, { update(draft.copy(speech = draft.speech.copy(apiKey = it))) }, state.busy, true)
        Text(stringResource(R.string.language_model), style = MaterialTheme.typography.titleLarge)
        ModelField(stringResource(R.string.language_url), draft.language.baseUrl, { update(draft.copy(language = draft.language.copy(baseUrl = it))) }, state.busy)
        ModelField(stringResource(R.string.language_model_name), draft.language.model, { update(draft.copy(language = draft.language.copy(model = it))) }, state.busy)
        ModelField(stringResource(R.string.language_key), draft.language.apiKey, { update(draft.copy(language = draft.language.copy(apiKey = it))) }, state.busy, true)
        Row {
            Checkbox(compatibleReasoningEffort(draft.language) == "none", {
                update(draft.copy(language = draft.language.copy(reasoningEffort = if (it) "none" else "high")))
            }, enabled = !state.busy)
            Text(stringResource(R.string.language_plain_mode))
        }
        Text(stringResource(R.string.language_plain_mode_hint), style = MaterialTheme.typography.bodySmall)
        Row { Checkbox(consent, { consent = it }, enabled = !state.busy); Text(stringResource(R.string.local_consent)) }
        Button({ session.save(config(), consent, back) }, enabled = consent && state.ready && !state.busy) { Text(stringResource(R.string.local_save)) }
        TextButton({ session.test(config()) }, enabled = consent && state.ready && !state.busy) { Text(stringResource(R.string.language_test)) }
        TextButton({ session.test(config(), recording, speech = true) }, enabled = consent && recording != null && state.ready && !state.busy) { Text(stringResource(R.string.speech_test)) }
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        state.message?.let { Text(it) }
        Text(stringResource(R.string.local_key_notice), style = MaterialTheme.typography.bodySmall)
        ReminderSettings(session)
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
    Text(stringResource(R.string.local_mode), style = MaterialTheme.typography.bodySmall)
    TextButton(settings, enabled = !state.busy && agent?.busy != true) { Text(stringResource(R.string.model_settings)) }
    if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
    state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    if (state.pending) {
        Text(stringResource(R.string.local_pending_notice))
        state.checkpoint?.let { Text(stringResource(R.string.saved_transcript, it)) }
        Row {
            TextButton({ session.retry() }, enabled = !state.busy && agent?.busy != true) { Text(stringResource(R.string.resume_task)) }
            TextButton({ session.cancelPending() }, enabled = !state.busy && agent?.busy != true) { Text(stringResource(R.string.cancel_task)) }
        }
    }
}

@Composable
fun LocalAgentControls(session: LocalAgentSession, settings: () -> Unit, portrait: () -> Unit) {
    LocalAgentStatus(session, settings)
    TextButton(portrait, enabled = !session.state.collectAsState().value.busy) { Text(stringResource(R.string.portrait_open)) }
}

@Composable
fun LocalCaptureScreen(session: LocalAgentSession, recording: AudioRecording, back: () -> Unit, settings: () -> Unit, process: () -> Unit) {
    val state by session.state.collectAsState()
    val configured = session.repository?.state?.collectAsState()?.value?.configured == true
    RmPage {
        TextButton(back) { Text(stringResource(R.string.back_recording)) }
        Text(stringResource(R.string.process_recording), style = MaterialTheme.typography.headlineLarge)
        Text(stringResource(R.string.recording_info, recording.createdAt, recording.durationMillis / 1000))
        Text(stringResource(R.string.local_capture_notice))
        LocalAgentStatus(session, settings)
        if (!configured || session.settings == null) Text(stringResource(R.string.local_configure_first))
        Button(process, enabled = configured && session.settings != null && !state.busy && !state.pending) { Text(stringResource(R.string.local_capture_start)) }
    }
}

@Composable
fun LocalProcessingScreen(session: LocalAgentSession, back: () -> Unit, settings: () -> Unit, understanding: () -> Unit) {
    val state by session.state.collectAsState()
    RmPage {
        TextButton(back) { Text(stringResource(R.string.back)) }
        Text(when (state.captureProgress) {
            CaptureProgress.RUNNING -> stringResource(R.string.capture_running)
            CaptureProgress.FAILED -> stringResource(R.string.capture_failed)
            CaptureProgress.PAUSED -> stringResource(R.string.capture_paused)
            CaptureProgress.COMPLETE -> stringResource(R.string.capture_complete)
            CaptureProgress.IDLE -> stringResource(R.string.capture_idle)
        }, style = MaterialTheme.typography.headlineLarge)
        LocalAgentStatus(session, settings)
        if (state.captureProgress == CaptureProgress.FAILED && !state.pending) TextButton({ session.retryCapture() }) { Text(stringResource(R.string.capture_retry)) }
        state.message?.let { Text(it) }
        Text(stringResource(R.string.local_processing_notice))
        Button(understanding, enabled = !state.busy) { Text(stringResource(R.string.show_understanding)) }
    }
}

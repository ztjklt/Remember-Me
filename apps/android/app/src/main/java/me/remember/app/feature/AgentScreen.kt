package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.res.stringResource
import me.remember.app.R
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.PasswordVisualTransformation
import kotlinx.coroutines.launch
import me.remember.app.data.repository.AgentRepository
import me.remember.app.data.repository.BackendConnection
import me.remember.app.model.AgentSnapshot
import me.remember.app.ui.components.*

/** Native client for the same original → understanding → answer → correction loop. */
@Composable
fun AgentScreen(repository: AgentRepository, back: () -> Unit, capture: () -> Unit, episodeId: String? = null,
    localMode: Boolean = false, externalBusy: Boolean = false, localControls: @Composable () -> Unit = {}) {
    val state by repository.state.collectAsState()
    val busy = state.busy || externalBusy
    val scope = rememberCoroutineScope()
    val connection = repository.currentConnection()
    var question by rememberSaveable(connection?.subjectId) { mutableStateOf("") }
    var human by rememberSaveable(connection?.subjectId, state.calibration?.id) { mutableStateOf("") }
    var resumeId by rememberSaveable(connection?.subjectId) { mutableStateOf("") }
    var shownCalibration by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(state.calibration?.id) { state.calibration?.let {
        if (shownCalibration != it.id) { question = it.question; shownCalibration = it.id }
    } }

    RmPage {
        TextButton(back) { Text(stringResource(R.string.back)) }
        Text(stringResource(R.string.agent_title), style = MaterialTheme.typography.headlineLarge)
        if (localMode) localControls()
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("agent.error")) }
        if (!state.configured) {
            if (localMode) Text(stringResource(R.string.agent_configure_first)) else AgentConnection(repository)
        } else {
            if (state.snapshot?.modelVersion?.startsWith("fixture-") == true) {
                Text(stringResource(R.string.agent_fixture_notice))
            }
            RmSectionHeader(stringResource(R.string.agent_original))
            val recordings = state.materials.filter { it.sourceType == "SUBJECT" && it.episodeId != null }
            val selected = episodeId ?: recordings.maxByOrNull { it.observedAt }?.episodeId
            val original = recordings.filter { it.episodeId == selected }.maxByOrNull { it.excerpt.length }
            Text(original?.excerpt ?: stringResource(R.string.agent_original_empty), modifier = Modifier.testTag("agent.original"))
            if (original != null) Text(stringResource(R.string.agent_transcription_notice), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { scope.launch { repository.refresh() } }, enabled = !busy) { Text(stringResource(R.string.agent_refresh)) }

            RmDivider()
            RmSectionHeader(stringResource(R.string.agent_understanding))
            AgentUnderstanding(state.snapshot, localMode)
            if (!localMode && state.snapshot?.limitations?.any { it.startsWith("最近一次自动更新失败") } == true)
                TextButton({ scope.launch { repository.retryUnderstanding() } }, enabled = !busy) { Text(stringResource(R.string.agent_retry_understanding)) }

            RmDivider()
            RmSectionHeader(stringResource(R.string.agent_questions))
            AgentDetails(stringResource(R.string.answer_history, state.history.size)) {
                if (!localMode) Text(stringResource(R.string.remote_history_notice))
                state.history.asReversed().forEach { entry ->
                    Text(entry.question)
                    val status = when (entry.state) { "COMPLETED" -> stringResource(R.string.calibration_completed); "INVALIDATED" -> stringResource(R.string.calibration_invalidated); else -> stringResource(R.string.calibration_pending) }
                    Text(stringResource(R.string.history_entry, entry.lockedAnswer.revision, answerType(entry.lockedAnswer.type), status))
                    TextButton({ scope.launch { repository.resume(entry.id) } }, enabled = !busy) { Text(stringResource(R.string.show_answer)) }
                }
            }
            OutlinedTextField(question, { question = it }, label = { Text(stringResource(R.string.question_label)) }, enabled = !busy,
                modifier = Modifier.fillMaxWidth().testTag("agent.question"))
            Button(onClick = { scope.launch { repository.ask(question) } }, enabled = question.isNotBlank() && !busy,
                modifier = Modifier.testTag("agent.ask")) { Text(stringResource(R.string.ask)) }
            state.answer?.let { answer ->
                state.calibration?.let { Text(stringResource(R.string.your_question, it.question)) }
                if (state.calibration?.state == "COMPLETED") Text(stringResource(R.string.locked_answer_notice))
                val label = answerType(answer.type)
                Text(stringResource(R.string.answer_revision, label, answer.revision), style = MaterialTheme.typography.bodySmall)
                Text(answer.answer, modifier = Modifier.testTag("agent.answer"))
                if (answer.evidence.isNotEmpty()) AgentDetails(stringResource(R.string.answer_evidence)) {
                    answer.evidence.forEach { Text("${if (it.sourceType == "CALIBRATION") stringResource(R.string.evidence_calibration) else stringResource(R.string.evidence_original)}：${it.excerpt}") }
                    answer.limitations.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }

            RmDivider()
            RmSectionHeader(stringResource(R.string.agent_correction))
            val calibration = state.calibration
            when (calibration?.state) {
                "LOCKED" -> {
                    val canCorrect = state.canCorrect(question) && !externalBusy
                    Text(when {
                        state.snapshot?.revision != calibration.lockedAnswer.revision -> stringResource(R.string.revision_changed)
                        question.trim() != calibration.question -> stringResource(R.string.question_changed)
                        else -> stringResource(R.string.correction_hint)
                    })
                    OutlinedTextField(human, { human = it }, label = { Text(stringResource(R.string.correction_label)) }, enabled = canCorrect,
                        modifier = Modifier.fillMaxWidth().testTag("agent.correctionInput"))
                    Button(onClick = { scope.launch { repository.submit(human, question) } }, enabled = canCorrect && human.isNotBlank(),
                        modifier = Modifier.testTag("agent.submit")) { Text(stringResource(R.string.submit_correction)) }
                }
                "COMPLETED" -> {
                    state.correction?.let { Text(stringResource(R.string.your_correction, it), modifier = Modifier.testTag("agent.correction")) }
                    Text(stringResource(R.string.correction_saved, stringResource(if (state.snapshot?.revision == calibration.resultingRevision) R.string.understanding_updated else R.string.refresh_result)))
                    if (state.snapshot?.revision == calibration.resultingRevision) AgentDetails(stringResource(R.string.show_updated_understanding)) {
                        AgentUnderstanding(state.snapshot, localMode)
                    }
                }
                "INVALIDATED" -> Text(stringResource(R.string.calibration_expired))
                else -> Text(stringResource(R.string.ask_before_correction))
            }
            Button(capture, enabled = !busy) { Text(stringResource(R.string.capture_again)) }

            AgentDetails(stringResource(R.string.agent_details)) {
                state.snapshot?.let { Text("Subject ${it.subjectId} · ${it.modelVersion}", style = MaterialTheme.typography.bodySmall) }
                calibration?.let {
                    Text("${it.state} · ${it.id}", style = MaterialTheme.typography.bodySmall)
                    it.diffs.forEach { diff -> Text("${diff.dimension} · ${diff.assessment}\n${diff.reason}") }
                }
                if (!localMode) {
                    OutlinedTextField(resumeId, { resumeId = it }, label = { Text(stringResource(R.string.resume_calibration_label)) }, enabled = !busy,
                        modifier = Modifier.fillMaxWidth())
                    TextButton(onClick = { scope.launch { repository.resume(resumeId.trim()) } }, enabled = resumeId.isNotBlank() && !busy) { Text(stringResource(R.string.resume_answer)) }
                    TextButton(onClick = { scope.launch { repository.plan() } }, enabled = !busy) { Text(stringResource(R.string.plan_next)) }
                    state.plan?.let { Text(it.question) }
                }
                original?.let { evidence ->
                    TextButton(onClick = { scope.launch { repository.inspect(evidence.id) } }, enabled = !busy) { Text(stringResource(R.string.inspect_evidence)) }
                }
                state.inspectedEvidence?.let { evidence ->
                    Text("${evidence.sourceType} · ${evidence.sourceRef}\n${evidence.excerpt}")
                    evidence.episodeId?.let { id ->
                        TextButton(onClick = { scope.launch { repository.withdraw(id) } }, enabled = !busy) { Text(stringResource(R.string.withdraw_episode)) }
                    }
                }
                TextButton(onClick = { scope.launch { repository.revoke() } }, enabled = !busy) { Text(if (localMode) stringResource(R.string.revoke_local) else stringResource(R.string.revoke_remote)) }
                if (!localMode) AgentDetails(stringResource(R.string.remote_settings)) { AgentConnection(repository) }
            }
        }
    }
}

@Composable
private fun AgentUnderstanding(snapshot: AgentSnapshot?, localMode: Boolean) {
    snapshot?.let { Text(stringResource(R.string.understanding_revision, it.revision), style = MaterialTheme.typography.bodySmall) }
    snapshot?.limitations?.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
    val traits = snapshot?.traits.orEmpty().filter { it.status != "SUPERSEDED" }
    if (traits.isEmpty()) Text(stringResource(R.string.understanding_empty))
    traits.forEach {
        val domain = when (it.domain) {
            "IDENTITY" -> stringResource(R.string.domain_identity); "EPISODIC_MEMORY" -> stringResource(R.string.domain_episodes); "RELATIONSHIPS" -> stringResource(R.string.domain_relations)
            "PREFERENCES" -> stringResource(R.string.domain_preferences); "VALUES" -> stringResource(R.string.domain_values); "DECISION_PATTERNS" -> stringResource(R.string.domain_decisions); else -> stringResource(R.string.domain_expression)
        }
        val status = when (it.status) { "CONFLICTED" -> stringResource(R.string.trait_conflicted); "SUPPORTED" -> stringResource(R.string.trait_supported); else -> stringResource(R.string.trait_candidate) }
        Text(if (localMode) domain else "$domain · $status", style = MaterialTheme.typography.bodySmall)
        Text(it.statement)
    }
}

@Composable
private fun AgentDetails(title: String, content: @Composable ColumnScope.() -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    TextButton(onClick = { expanded = !expanded }) { Text("${if (expanded) "▾" else "▸"} $title") }
    if (expanded) Column(Modifier.fillMaxWidth(), content = content)
}

@Composable
private fun AgentConnection(repository: AgentRepository) {
    val state by repository.state.collectAsState()
    val scope = rememberCoroutineScope()
    val current = repository.currentConnection()
    var url by remember(current) { mutableStateOf(current?.baseUrl ?: "http://10.0.2.2:8000") }
    var token by remember(current) { mutableStateOf(current?.actorToken.orEmpty()) }
    var subject by remember(current) { mutableStateOf(current?.subjectId.orEmpty()) }
    var consent by remember(current) { mutableStateOf(current?.recordingConsentId.orEmpty()) }
    var agreed by remember(current) { mutableStateOf(false) }
    Text(stringResource(R.string.remote_connect_notice))
    OutlinedTextField(url, { url = it }, label = { Text(stringResource(R.string.backend_url)) }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(token, { token = it }, label = { Text("Actor Token") }, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
    OutlinedTextField(subject, { subject = it }, label = { Text("Subject ID") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(consent, { consent = it }, label = { Text("RECORDING Consent ID") }, modifier = Modifier.fillMaxWidth())
    Row { Checkbox(agreed, { agreed = it }); Text(stringResource(R.string.remote_consent)) }
    Button(onClick = { scope.launch { repository.enable(BackendConnection(url.trim(), token.trim(), subject.trim(), consent.trim(), true)) } },
        enabled = agreed && !state.busy && listOf(url, token, subject, consent).all { it.isNotBlank() }) { Text(stringResource(R.string.remote_connect)) }
}

@Composable private fun answerType(type: String) = stringResource(when (type) {
    "ORIGINAL" -> R.string.answer_original
    "SIMULATION" -> R.string.answer_simulation
    else -> R.string.answer_insufficient
})

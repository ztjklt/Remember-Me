package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
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
fun AgentScreen(repository: AgentRepository, back: () -> Unit, capture: () -> Unit, episodeId: String? = null) {
    val state by repository.state.collectAsState()
    val scope = rememberCoroutineScope()
    val connection = repository.currentConnection()
    var question by remember(connection) { mutableStateOf("") }
    var human by remember(connection, state.calibration?.id) { mutableStateOf("") }
    var resumeId by remember(connection) { mutableStateOf("") }
    LaunchedEffect(state.calibration?.id) { state.calibration?.let { question = it.question } }

    RmPage {
        TextButton(back) { Text("← 返回") }
        Text("记忆与理解", style = MaterialTheme.typography.headlineLarge)
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("agent.error")) }
        if (!state.configured) {
            AgentConnection(repository)
        } else {
            if (state.snapshot?.modelVersion?.startsWith("fixture-") == true) {
                Text("离线测试：录音会转为固定测试句，不代表真实语音识别或理解。")
            }
            RmSectionHeader("记忆原文")
            val recordings = state.materials.filter { it.sourceType == "SUBJECT" && it.episodeId != null }
            val selected = episodeId ?: recordings.maxByOrNull { it.observedAt }?.episodeId
            val original = recordings.filter { it.episodeId == selected }.maxByOrNull { it.excerpt.length }
            Text(original?.excerpt ?: "暂无这段录音的原文，请上传录音或刷新已有理解。", modifier = Modifier.testTag("agent.original"))
            if (original != null) Text("转写可能有同音字错误，可在下方校正。", style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { scope.launch { repository.refresh() } }, enabled = !state.busy) { Text("刷新已有理解") }

            RmDivider()
            RmSectionHeader("当前理解")
            AgentUnderstanding(state.snapshot)

            RmDivider()
            RmSectionHeader("提问与回答")
            OutlinedTextField(question, { question = it }, label = { Text("你想问什么？") }, enabled = !state.busy,
                modifier = Modifier.fillMaxWidth().testTag("agent.question"))
            Button(onClick = { scope.launch { repository.ask(question) } }, enabled = question.isNotBlank() && !state.busy,
                modifier = Modifier.testTag("agent.ask")) { Text("提问") }
            state.answer?.let { answer ->
                state.calibration?.let { Text("你问：${it.question}") }
                if (state.calibration?.state == "COMPLETED") Text("以下保留校正前的回答；再次提问会使用更新后的理解。")
                val label = when (answer.type) {
                    "ORIGINAL" -> "引用原话"
                    "SIMULATION" -> "依据记忆生成"
                    else -> "材料不足"
                }
                Text("$label · 第 ${answer.revision} 版理解", style = MaterialTheme.typography.bodySmall)
                Text(answer.answer, modifier = Modifier.testTag("agent.answer"))
                if (answer.evidence.isNotEmpty()) AgentDetails("查看回答依据") {
                    answer.evidence.forEach { Text("${if (it.sourceType == "CALIBRATION") "本人校正" else "原始材料"}：${it.excerpt}") }
                    answer.limitations.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }

            RmDivider()
            RmSectionHeader("校正与更新")
            val calibration = state.calibration
            when (calibration?.state) {
                "LOCKED" -> {
                    val canCorrect = state.canCorrect(question)
                    Text(when {
                        state.snapshot?.revision != calibration.lockedAnswer.revision -> "理解已变化，请重新提问后再校正。"
                        question.trim() != calibration.question -> "问题已修改，请重新提问后再校正。"
                        else -> "校正上方这次回答，保存后会更新理解。"
                    })
                    OutlinedTextField(human, { human = it }, label = { Text("本人的校正") }, enabled = canCorrect,
                        modifier = Modifier.fillMaxWidth().testTag("agent.correctionInput"))
                    Button(onClick = { scope.launch { repository.submit(human, question) } }, enabled = canCorrect && human.isNotBlank(),
                        modifier = Modifier.testTag("agent.submit")) { Text("保存校正并更新理解") }
                }
                "COMPLETED" -> {
                    state.correction?.let { Text("你的校正：$it", modifier = Modifier.testTag("agent.correction")) }
                    Text("校正已保存。${if (state.snapshot?.revision == calibration.resultingRevision) "理解已更新，可以再次提问。" else "点击刷新已有理解读取更新结果。"}")
                    if (state.snapshot?.revision == calibration.resultingRevision) AgentDetails("查看更新后的理解") {
                        AgentUnderstanding(state.snapshot)
                    }
                }
                "INVALIDATED" -> Text("这次校正记录已失效，请重新提问。")
                else -> Text("先提问，回答出现后即可填写校正。")
            }
            Button(capture, enabled = !state.busy) { Text("再录一段，继续循环") }

            AgentDetails("调试与授权") {
                state.snapshot?.let { Text("Subject ${it.subjectId} · ${it.modelVersion}", style = MaterialTheme.typography.bodySmall) }
                calibration?.let {
                    Text("${it.state} · ${it.id}", style = MaterialTheme.typography.bodySmall)
                    it.diffs.forEach { diff -> Text("${diff.dimension} · ${diff.assessment}\n${diff.reason}") }
                }
                OutlinedTextField(resumeId, { resumeId = it }, label = { Text("恢复校准记录 ID") }, enabled = !state.busy,
                    modifier = Modifier.fillMaxWidth())
                TextButton(onClick = { scope.launch { repository.resume(resumeId.trim()) } }, enabled = resumeId.isNotBlank() && !state.busy) { Text("恢复这次回答") }
                TextButton(onClick = { scope.launch { repository.plan() } }, enabled = !state.busy) { Text("下一次可以聊什么") }
                state.plan?.let { Text(it.question) }
                original?.let { evidence ->
                    TextButton(onClick = { scope.launch { repository.inspect(evidence.id) } }, enabled = !state.busy) { Text("核对录音来源") }
                }
                state.inspectedEvidence?.let { evidence ->
                    Text("${evidence.sourceType} · ${evidence.sourceRef}\n${evidence.excerpt}")
                    evidence.episodeId?.let { id ->
                        TextButton(onClick = { scope.launch { repository.withdraw(id) } }, enabled = !state.busy) { Text("从 Agent 撤除此录音材料") }
                    }
                }
                TextButton(onClick = { scope.launch { repository.revoke() } }, enabled = !state.busy) { Text("撤回 Cloud Twin 同意") }
                AgentDetails("连接设置") { AgentConnection(repository) }
            }
        }
    }
}

@Composable
private fun AgentUnderstanding(snapshot: AgentSnapshot?) {
    snapshot?.let { Text("第 ${it.revision} 版理解", style = MaterialTheme.typography.bodySmall) }
    val traits = snapshot?.traits.orEmpty().filter { it.status != "SUPERSEDED" }
    if (traits.isEmpty()) Text("还没有形成理解，请先上传一段录音。")
    traits.forEach {
        val domain = when (it.domain) {
            "IDENTITY" -> "身份"; "EPISODIC_MEMORY" -> "经历"; "RELATIONSHIPS" -> "关系"
            "PREFERENCES" -> "偏好"; "VALUES" -> "价值与方向"; "DECISION_PATTERNS" -> "决策"; else -> "表达"
        }
        val status = when (it.status) { "CONFLICTED" -> "有冲突"; "SUPPORTED" -> "有依据"; else -> "待确认" }
        Text("$domain · $status", style = MaterialTheme.typography.bodySmall)
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
    Text("连接你的 Backend 会话，读取已有录音与理解。")
    OutlinedTextField(url, { url = it }, label = { Text("Backend 地址") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(token, { token = it }, label = { Text("Actor Token") }, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
    OutlinedTextField(subject, { subject = it }, label = { Text("Subject ID") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(consent, { consent = it }, label = { Text("RECORDING Consent ID") }, modifier = Modifier.fillMaxWidth())
    Row { Checkbox(agreed, { agreed = it }); Text("同意 Cloud Twin 处理，并声明为本人单人表达") }
    Button(onClick = { scope.launch { repository.enable(BackendConnection(url.trim(), token.trim(), subject.trim(), consent.trim(), true)) } },
        enabled = agreed && !state.busy && listOf(url, token, subject, consent).all { it.isNotBlank() }) { Text("连接并读取") }
}

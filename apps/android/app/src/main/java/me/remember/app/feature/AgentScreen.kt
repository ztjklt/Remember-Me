package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import me.remember.app.data.repository.*
import me.remember.app.ui.components.*
import kotlinx.coroutines.launch

/** Minimal functional shell for the loop; all answers and changes come from Backend. */
@Composable
fun AgentScreen(repository: AgentRepository, back: () -> Unit, capture: () -> Unit) {
    val state by repository.state.collectAsState()
    val scope = rememberCoroutineScope()
    var question by remember { mutableStateOf("") }
    var human by remember(state.calibration?.id) { mutableStateOf("") }
    var url by remember { mutableStateOf("http://127.0.0.1:8000") }
    var token by remember { mutableStateOf("") }
    var subject by remember { mutableStateOf("") }
    var resumeId by remember { mutableStateOf("") }
    var consent by remember { mutableStateOf("") }
    var agreed by remember { mutableStateOf(false) }
    RmPage {
        TextButton(back) { Text("← 返回") }
        Text("Agent 闭环", style = MaterialTheme.typography.headlineLarge)
        if (!state.configured) {
            OutlinedTextField(url,{url=it},label={Text("Backend 地址")},modifier=Modifier.fillMaxWidth())
            OutlinedTextField(token,{token=it},label={Text("Actor Token")},visualTransformation=PasswordVisualTransformation(),modifier=Modifier.fillMaxWidth())
            OutlinedTextField(subject,{subject=it},label={Text("Subject ID")},modifier=Modifier.fillMaxWidth())
            OutlinedTextField(consent,{consent=it},label={Text("RECORDING Consent ID")},modifier=Modifier.fillMaxWidth())
            Row { Checkbox(agreed,{agreed=it}); Text("我同意 Cloud Twin 处理，并声明材料是本人单人表达。") }
            Button(onClick={scope.launch { repository.enable(BackendConnection(url.trim(),token.trim(),subject.trim(),consent.trim(),true)) }},
                enabled=agreed && !state.busy && listOf(url,token,subject,consent).all { it.isNotBlank() }) { Text("连接并读取模型") }
        }
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.error?.let { Text(it,color=MaterialTheme.colorScheme.error) }
        if (state.configured) {
            state.snapshot?.let { m ->
                Text("Subject ${m.subjectId} · revision ${m.revision}")
                Text("推理模型 ${m.modelVersion}",style=MaterialTheme.typography.bodySmall)
                if (m.modelVersion.startsWith("fixture-")) Text("当前为离线接线验证，尚未验收真实语音与人格推理。")
                m.traits.forEach { t ->
                    Text("${t.domain} · ${t.status}：${t.statement}")
                    if (t.context.isNotBlank()) Text("情境：${t.context}")
                    t.evidenceIds.firstOrNull()?.let { eid -> TextButton(onClick={scope.launch{repository.inspect(eid)}},enabled=!state.busy) { Text("核对支持原文") } }
                    t.counterEvidenceIds.firstOrNull()?.let { eid -> TextButton(onClick={scope.launch{repository.inspect(eid)}},enabled=!state.busy) { Text("核对反例原文") } }
                    Text("支持：${t.evidenceIds.joinToString()}\n反例：${t.counterEvidenceIds.joinToString()}",style=MaterialTheme.typography.bodySmall)
                }
            }
            state.inspectedEvidence?.let { e ->
                Text("${e.sourceType} · ${e.sourceRef}\n${e.excerpt}")
                e.episodeId?.let { eid -> TextButton(onClick={scope.launch{repository.withdraw(eid)}},enabled=!state.busy) { Text("从 Agent 模型撤除此录音材料") } }
            }
            Button(onClick={scope.launch{repository.refresh()}},enabled=!state.busy) { Text("刷新人格模型") }
            OutlinedTextField(question,{question=it},label={Text("问一个尚未预置的问题")},modifier=Modifier.fillMaxWidth())
            Row {
                Button(onClick={scope.launch{repository.ask(question)}},enabled=question.isNotBlank()&&!state.busy) { Text("问 Twin") }
                TextButton(onClick={scope.launch{repository.lock(question)}},enabled=question.isNotBlank()&&!state.busy) { Text("先锁定，再校准") }
            }
            state.answer?.let { a ->
                Text("${a.type} · revision ${a.revision}")
                Text(a.answer)
                a.evidence.forEach { e -> Text("原文：${e.excerpt}\n${e.sourceType} · ${e.sourceRef}",style=MaterialTheme.typography.bodySmall) }
                a.limitations.forEach { Text(it,style=MaterialTheme.typography.bodySmall) }
            }
            state.calibration?.let { cal ->
                RmDivider()
                Text("${cal.state} · ${cal.lockedAt}\n${cal.id}",style=MaterialTheme.typography.bodySmall)
                Text("问题：${cal.question}\n锁定答案：${cal.lockedAnswer.answer}")
                if (cal.state=="LOCKED") {
                    OutlinedTextField(human,{human=it},label={Text("现在写下本人的答案")},modifier=Modifier.fillMaxWidth())
                    Button(onClick={scope.launch{repository.submit(human)}},enabled=human.isNotBlank()&&!state.busy) { Text("比较并更新理解") }
                }
                cal.diffs.forEach { d -> Text("${d.dimension} · ${d.assessment}\n${d.reason}") }
                cal.resultingRevision?.let { Text("更新至 revision $it") }
            }
            OutlinedTextField(resumeId,{resumeId=it},label={Text("恢复已锁定的 calibration ID（可选）")},modifier=Modifier.fillMaxWidth())
            TextButton(onClick={scope.launch{repository.resume(resumeId.trim())}},enabled=resumeId.isNotBlank()&&!state.busy) { Text("读取该校准记录") }
            Button(onClick={scope.launch{repository.plan()}},enabled=!state.busy) { Text("下一次可以聊什么") }
            state.plan?.let { Text(it.question); Text(it.reason,style=MaterialTheme.typography.bodySmall) }
            Button(onClick=capture,enabled=!state.busy) { Text("再录一段，继续循环") }
            TextButton(onClick={scope.launch{repository.revoke()}},enabled=!state.busy) { Text("撤回 Cloud Twin 授权") }
        }
    }
}

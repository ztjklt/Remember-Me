package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.data.repository.AudioRecording
import me.remember.app.data.repository.BackendConnection
import me.remember.app.data.repository.EpisodeStage
import me.remember.app.data.repository.EpisodeUiState
import me.remember.app.ui.components.RmPage
import me.remember.app.ui.components.RmPrimaryButton
import me.remember.app.ui.components.RmSecondaryButton

@Composable
fun BackendConnectionScreen(
    recording: AudioRecording,
    back: () -> Unit,
    upload: (BackendConnection) -> Unit
) {
    var baseUrl by rememberSaveable { mutableStateOf("") }
    var actorToken by remember { mutableStateOf("") }
    var subjectId by rememberSaveable { mutableStateOf("") }
    var consentId by rememberSaveable { mutableStateOf("") }

    RmPage {
        TextButton(back) { Text("← 返回录音") }
        Text("上传这段录音", style = MaterialTheme.typography.headlineLarge)
        Text("${recording.byteSize} bytes · ${recording.mimeType}", color = RememberMeColors.Muted)
        Text(
            "输入 Backend 签发的 Actor Token、Subject ID 和有效的录音同意 ID。这里不会创建同意，也不会把 Token 写入本地文件。",
            color = RememberMeColors.Muted
        )
        OutlinedTextField(
            value = baseUrl,
            onValueChange = { baseUrl = it },
            label = { Text("Backend 地址") },
            placeholder = { Text("https://backend.example") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag("backend.url")
        )
        OutlinedTextField(
            value = actorToken,
            onValueChange = { actorToken = it },
            label = { Text("Actor Token") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag("backend.token")
        )
        OutlinedTextField(
            value = subjectId,
            onValueChange = { subjectId = it },
            label = { Text("Subject ID") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag("backend.subject")
        )
        OutlinedTextField(
            value = consentId,
            onValueChange = { consentId = it },
            label = { Text("RECORDING Consent ID") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag("backend.consent")
        )
        Button(
            onClick = {
                upload(
                    BackendConnection(
                        baseUrl.trim(), actorToken.trim(), subjectId.trim(), consentId.trim()
                    )
                )
            },
            enabled = listOf(baseUrl, actorToken, subjectId, consentId).all { it.isNotBlank() },
            modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("backend.upload")
        ) { Text("开始上传") }
    }
}

@Composable
fun ProcessingScreen(
    state: EpisodeUiState,
    back: () -> Unit,
    retry: () -> Unit,
    showMemories: () -> Unit
) {
    RmPage {
        TextButton(back) { Text("← 返回") }
        Text("处理进度", style = MaterialTheme.typography.headlineLarge)
        when (state) {
            EpisodeUiState.Idle -> Text("尚无正在处理的 Episode。", color = RememberMeColors.Muted)
            is EpisodeUiState.Uploading -> {
                Text("正在上传原始录音：${state.percent}%", modifier = Modifier.testTag("episode.uploading"))
                LinearProgressIndicator(
                    progress = { state.percent / 100f },
                    modifier = Modifier.fillMaxWidth()
                )
            }
            is EpisodeUiState.Processing -> {
                Text("Episode：${state.episodeId}", style = MaterialTheme.typography.bodySmall)
                Text(state.stage.label(), modifier = Modifier.testTag("episode.processing"))
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                Text("状态来自 Backend；处理完成前不会显示模拟结果。", color = RememberMeColors.Muted)
            }
            is EpisodeUiState.Ready -> {
                Text("Episode：${state.episodeId}", style = MaterialTheme.typography.bodySmall)
                Text("处理完成，得到 ${state.memoryCount} 条真实 Memory。", modifier = Modifier.testTag("episode.ready"))
                RmPrimaryButton("查看记忆", showMemories, Modifier.fillMaxWidth())
            }
            is EpisodeUiState.Error -> {
                state.episodeId?.let { Text("Episode：$it", style = MaterialTheme.typography.bodySmall) }
                Text("${state.code}：${state.message}", color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("episode.error"))
                if (state.retryable) {
                    RmSecondaryButton("重试上传或继续查询", Modifier.fillMaxWidth(), retry)
                } else {
                    Text("原始录音仍保存在此设备，可返回录音页面检查。", color = RememberMeColors.Muted)
                }
            }
        }
    }
}

private fun EpisodeStage.label(): String = when (this) {
    EpisodeStage.UPLOADED -> "已接收录音，等待转录"
    EpisodeStage.TRANSCRIBING -> "正在转录"
    EpisodeStage.EXTRACTING -> "正在提取记忆"
    EpisodeStage.MODELING -> "正在保存结果"
    EpisodeStage.READY -> "处理完成"
    EpisodeStage.FAILED -> "处理失败"
}

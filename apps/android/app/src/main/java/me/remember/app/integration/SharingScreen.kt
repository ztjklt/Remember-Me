package me.remember.app.integration

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import org.json.JSONObject

@Composable fun ClaimInvitationPanel(state: NativeState, model: NativeWorkbenchModel) {
    if(!state.serviceInfo.invitations) return
    var code by remember(state.actor) { mutableStateOf("") }
    Text("亲友邀请", style = MaterialTheme.typography.titleLarge)
    OutlinedTextField(code, { code = it }, label = { Text("粘贴邀请码") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    Button(onClick = { model.claimInvitation(code); code = "" }, enabled = !state.busy && code.trim().length >= 16) { Text("领取邀请") }
    Text("领取不会立即开放故事。记录者确认你的账号后，从顶部空间列表进入。", style = MaterialTheme.typography.bodySmall)
}

@Composable fun SharingPanel(state: NativeState, model: NativeWorkbenchModel, confirm: (String, () -> Unit) -> Unit) {
    val enabled = !state.busy && !state.recording
    Text("与亲友分享", style = MaterialTheme.typography.titleLarge)
    if(state.owner && state.serviceInfo.invitations) {
        var selected by remember(state.subject) { mutableStateOf(setOf<String>()) }
        var stories by remember(state.subject) { mutableStateOf(setOf<String>()) }
        var recipient by remember(state.subject) { mutableStateOf<String?>(null) }
        var audio by remember(state.sharePreview) { mutableStateOf(false) }
        var cloud by remember(state.sharePreview) { mutableStateOf(false) }
        Text("选择故事或录音，下一步核对完整分享范围。")
        state.narrative.rows("records").filter { it.text("kind") in listOf("story", "letter") && it.text("status") == "confirmed" }.forEach { story ->
            val id = story.text("id")
            Row { Checkbox(id in stories, { checked -> stories = if(checked) stories + id else stories - id; model.clearSharePreview() }, enabled = enabled, modifier = Modifier.testTag("share-story-$id"))
                Text(story.text("title"), Modifier.padding(top = 12.dp)) }
        }
        state.stories.filter { it.text("status") == "ready" && it.optBoolean("reviewed") }.forEach { story ->
            val id = story.text("episode_id")
            Row { Checkbox(id in selected, { checked -> selected = if(checked) selected + id else selected - id; model.clearSharePreview() }, enabled = enabled, modifier = Modifier.testTag("share-episode-$id"))
                Text(storyTitle(story), Modifier.padding(top = 12.dp)) }
        }
        Button(onClick = { model.previewShare(ShareSelection(selected.toList(), stories.toList())) }, enabled = enabled && (selected.isNotEmpty() || stories.isNotEmpty())) { Text("预览分享范围") }
        state.sharePreview?.let { preview ->
            Text(preview.text("notice"), style = MaterialTheme.typography.titleMedium)
            preview.rows().forEach { item ->
                Text(recordingDate(item.text("recorded_at")), style = MaterialTheme.typography.labelMedium)
                SelectionContainer { Text(item.text("transcript")) }
                if(item.text("supplement").isNotBlank()) Text("本人书面补充：${item.text("supplement")}")
                OutlinedButton(onClick = { model.playSource(item.text("episode_id")) }, enabled = enabled) { Text("试听这段完整原音") }
                HorizontalDivider()
            }
            Row { RadioButton(recipient == null, { recipient = null }, enabled = enabled); Text("邀请新的亲友", Modifier.padding(top = 12.dp)) }
            state.recipients.forEach { person ->
                Row { RadioButton(recipient == person.text("actor_id"), { recipient = person.text("actor_id") }, enabled = enabled)
                    Text("${person.text("display_name")} · ${person.text("username")}", Modifier.padding(top = 12.dp)) }
            }
            Row { Checkbox(audio, { audio = it }, enabled = enabled, modifier = Modifier.testTag("share-audio-confirmation")); Text("确认开放上述完整原音、核对文字、书面补充及相关记忆。", Modifier.padding(top = 12.dp)) }
            Row { Checkbox(cloud, { cloud = it }, enabled = enabled, modifier = Modifier.testTag("share-cloud-confirmation")); Text("另行允许这些材料参与亲友的云端问答。", Modifier.padding(top = 12.dp)) }
            Button(onClick = { model.createInvitation(audio, cloud, recipient) }, enabled = enabled && audio) { Text(if(recipient == null) "生成一次性邀请" else "选定亲友并继续确认") }
        }
        state.issuedInvitation?.takeIf { it.text("code").isNotBlank() && state.invitations.any { row -> row.text("id") == it.text("id") && row.text("status") == "created" } }?.let { invitation ->
            val clipboard = LocalClipboardManager.current
            Text("邀请码仅显示在本次操作中；24小时后失效。丢失后请取消再生成。")
            SelectionContainer { Text(invitation.text("code")) }
            OutlinedButton(onClick = { clipboard.setText(AnnotatedString(invitation.text("code"))) }) { Text("复制邀请码") }
        }
        state.invitations.forEach { invitation ->
            HorizontalDivider(); Text(invitationStatus(invitation.text("status")), style = MaterialTheme.typography.titleMedium)
            val scope = invitation.rows("scope")
            val scopeLabel = scope.joinToString("\n") { "${recordingDate(it.text("recorded_at"))} · ${it.text("title")}" }
            Text("本次分享范围 · ${scope.size} 段完整原音", style = MaterialTheme.typography.labelLarge)
            if(scope.isEmpty()) Text("旧邀请缺少范围记录，请取消后重新预览。") else Text(scopeLabel)
            val person = invitation.optJSONObject("recipient")
            if(person != null) Text("接收账号：${person.text("username")}（${person.text("display_name")}）")
            Text(if(cloudProcessingAllowed(invitation)) "包含完整原音、文字与云端问答" else "仅浏览和聆听，不允许云端问答")
            val path = "/invitations/${segment(invitation.text("id"))}"
            if(invitation.text("status") == "claimed") {
                Button(onClick = { confirm("接收账号：${person?.text("username")}（${person?.text("display_name")}）\n开放下列完整录音和文字：\n$scopeLabel\n确认这是你要分享的亲友与范围？") { model.mutation("$path/approve", "POST") } }, enabled = enabled && scope.isNotEmpty()) { Text("确认账号并批准") }
                OutlinedButton(onClick = { model.mutation("$path/reject", "POST") }, enabled = enabled) { Text("不是这位亲友，拒绝") }
            }
            if(invitation.text("status") in listOf("created", "claimed")) OutlinedButton(onClick = { model.mutation("$path/cancel", "POST") }, enabled = enabled) { Text("取消这次邀请") }
            if(invitation.text("status") == "approved") OutlinedButton(onClick = { confirm("撤销本次新开放的录音：\n$scopeLabel\n不会撤销更早的独立分享，也无法收回已另行保存的内容。") { model.mutation("$path/revoke", "POST") } }, enabled = enabled) { Text("撤销本次分享") }
        }
    } else if(state.owner) Text("服务器尚未提供新版邀请，请管理员更新服务。")
    state.grants.forEach { grant ->
        val story = state.stories.firstOrNull { it.text("episode_id") == grant.text("episode_id") }
        val person = state.recipients.firstOrNull { it.text("actor_id") == grant.text("reader_actor_id") }
        Text("${story?.let(::storyTitle) ?: "一段已分享录音"} · ${person?.text("display_name") ?: "已授权亲友"}")
        if(state.owner) OutlinedButton(onClick = { confirm("撤销这段完整录音的访问权限？") { model.mutation("/grants/${segment(grant.text("grant_id"))}", "DELETE") } }, enabled = enabled) { Text("撤销这段授权") }
    }
}

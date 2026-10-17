package me.remember.app.integration

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject

@Composable fun CompanionScreen(state: NativeState, model: NativeWorkbenchModel) {
    if(!state.companion.has("role")) { Text("这个空间暂未开放亲友补记与专属信。"); return }
    var section by rememberSaveable(state.actor,state.subject) { mutableIntStateOf(0) }
    Row(Modifier.fillMaxWidth(), horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        listOf("亲友补记","留给你").forEachIndexed { i,title -> FilterChip(section==i,{section=i},label={Text(title)},enabled=!state.recording&&!state.busy) }
    }
    if(section==0) Contributions(state,model) else {
        if(state.owner) {
            ContactEntrustmentScreen(state,model)
            var accounts by rememberSaveable(state.actor,state.subject) { mutableStateOf(false) }
            TextButton(onClick={accounts=!accounts},enabled=!state.busy&&!state.recording) {
                Text(if(accounts) "收起账号专属信" else "已有账号的专属信")
            }
            if(accounts) Letters(state,model)
        } else Letters(state,model)
    }
    state.contributionOriginal?.let { original ->
        NativeDialog("亲友原文",model::closeContributionOriginal) {
            Text(original.text("author_display_name").ifBlank{"亲友"}+"的补记",style=MaterialTheme.typography.titleLarge)
            Text(when(original.text("classification")){"firsthand"->"亲身经历";"reported"->"他人转述";else->"个人看法"})
            Text(original.text("text"),style=MaterialTheme.typography.bodyLarge)
            if(original.text("audio_id").isNotBlank()) RememberActionButton("听原音",!state.busy,
                pendingLabel="正在取回声音…",successLabel="声音已取回") {model.playCompanionAudio(original.text("audio_id"))}
        }
    }
}

@Composable private fun CompanionCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(shape=RoundedCornerShape(22.dp),color=MaterialTheme.colorScheme.surface.copy(alpha=.95f),modifier=modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(10.dp),content=content)
    }
}

@Composable private fun CompanionCheck(text: String, checked: Boolean, enabled: Boolean = true, tag: String = "", changed: (Boolean) -> Unit) {
    Row { Checkbox(checked,changed,enabled=enabled,modifier=if(tag.isBlank()) Modifier else Modifier.testTag(tag));Text(text,Modifier.padding(top=12.dp)) }
}

@Composable internal fun AudioDraft(purpose: String, state: NativeState, model: NativeWorkbenchModel, audioOnly: Boolean = false, useText: (String) -> Unit) {
    val context=LocalContext.current
    val ready=!state.busy&&!state.recording
    val microphone=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if(granted) model.startCompanionRecording(purpose) else model.report("未获得麦克风权限，可以选择音频或填写文字。")
    }
    val picker=rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if(uri!=null) { val type=context.contentResolver.getType(uri) ?: "audio/mp4"
            model.importCompanionAudio(purpose,type) { context.contentResolver.openInputStream(uri)?.use { input ->
                val output=java.io.ByteArrayOutputStream();val buffer=ByteArray(8192)
                while(true) {val size=input.read(buffer);if(size<0)break;require(output.size()+size<=40*1024*1024){"请选择 40 MB 以内的音频。"};output.write(buffer,0,size)}
                output.toByteArray()
            } ?: error("无法读取所选音频。") }
        }
    }
    val draft=state.companionAudio?.takeIf { it.purpose==purpose }
    val other=state.companionAudio!=null&&draft==null
    Text(if(audioOnly) "单独留一段声音" else if(purpose=="letter") "为这封信留一段声音" else "也可以讲出来",style=MaterialTheme.typography.titleMedium)
    if(state.companionRecording==purpose) {
        Text("正在录音 ${state.elapsed/1000} 秒")
        RememberActionButton("结束录音",!state.busy,filled=true,pendingLabel="正在保存原音…",successLabel="原音已保存") {model.finishCompanionRecording()}
    } else Row(Modifier.horizontalScroll(rememberScrollState())) {
        RememberActionButton("录一段声音",ready&&!other,fullWidth=false) {microphone.launch(Manifest.permission.RECORD_AUDIO)}
        RememberActionButton("选择音频",ready&&!other,fullWidth=false) {picker.launch("audio/*")}
    }
    if(other) Text("另一页还有未提交的录音，请先提交或取消附加。")
    if(draft!=null) {
        if(draft.remote==null) RememberActionButton("上传这段声音",ready,filled=true,pendingLabel="正在上传声音…",successLabel="声音已保存",onClick=model::uploadCompanionAudio)
        else {
            val remote=draft.remote
            RememberActionButton("听已保存的声音",ready,pendingLabel="正在取回声音…",successLabel="声音已取回") {model.playCompanionAudio(remote.text("audio_id"))}
            if(audioOnly) Text("声音已保存，可在下面选入托付。")
            else if(remote.text("transcript_text").isBlank()) {
                var cloud by remember(remote.text("audio_id")) { mutableStateOf(false) }
                CompanionCheck("同意将这段声音交给云端转写",cloud,ready,"$purpose-cloud-asr") { cloud=it }
                RememberActionButton(if(remote.text("status")=="failed") "重试转写" else "转为文字",ready&&cloud,filled=true,
                    pendingLabel="正在转写…",successLabel="文字已返回") {model.transcribeCompanionAudio(cloud)}
                if(remote.text("error").isNotBlank()) Text(remote.text("error"),color=MaterialTheme.colorScheme.error)
            } else {
                var reviewed by remember(remote.text("audio_id"),remote.optInt("revision")) { mutableStateOf(remote.text("reviewed_text").ifBlank {remote.text("transcript_text")}) }
                var original by remember { mutableStateOf(false) }
                TextButton(onClick={original=!original}) { Text(if(original) "收起机器稿" else "查看原始机器稿") }
                if(original) Text(remote.text("transcript_text"))
                OutlinedTextField(reviewed,{reviewed=it},label={Text("核对录音文字")},modifier=Modifier.fillMaxWidth(),minLines=3)
                RememberActionButton("确认录音文字",ready&&reviewed.isNotBlank(),filled=true,pendingLabel="正在保存核对稿…",successLabel="核对稿已保存") {model.reviewCompanionAudio(reviewed)}
                if(remote.text("status")=="confirmed") TextButton(onClick={useText(remote.text("reviewed_text"))},enabled=ready) { Text("把已核对文字填入正文") }
            }
        }
        RememberActionButton("取消附加声音",ready,successLabel="已取消附加",onClick=model::clearCompanionAudio)
    }
}

@Composable private fun Contributions(state: NativeState, model: NativeWorkbenchModel) {
    val ready=!state.busy&&!state.recording
    val grants=state.companion.rows("contribution_grants")
    if(state.owner) CompanionCard {
        Text("谁可以补记",style=MaterialTheme.typography.titleLarge)
        state.recipients.forEach { person ->
            val grant=grants.firstOrNull {it.text("actor_id")==person.text("actor_id")}
            RememberToggle(person.text("display_name"),grant?.optBoolean("enabled")==true,enabled=ready,onCheckedChange={ enabled ->
                model.mutation("/companion/contribution-grants/${segment(person.text("actor_id"))}","PUT",JSONObject().put("revision",grant?.optInt("revision")?:0).put("enabled",enabled))
            })
        }
        if(state.recipients.isEmpty()) Text("先在分享中核对亲友账号。")
    }
    if(grants.any {it.text("actor_id")==state.actor&&it.optBoolean("enabled")}) CompanionCard {
        var text by rememberSaveable(state.actor,state.subject) { mutableStateOf("") }
        var classification by rememberSaveable(state.actor,state.subject) { mutableStateOf("firsthand") }
        var links by remember(state.actor,state.subject) { mutableStateOf(setOf<String>()) }
        var selecting by remember { mutableStateOf(false) }
        Text("留下你知道的那一段",style=MaterialTheme.typography.titleLarge)
        Row(Modifier.horizontalScroll(rememberScrollState())) {
            listOf("firsthand" to "亲身经历","reported" to "听他人讲过","opinion" to "个人看法").forEach { (value,title) -> FilterChip(classification==value,{classification=value},label={Text(title)}) }
        }
        AudioDraft("contribution",state,model) {text=it}
        OutlinedTextField(text,{text=it},label={Text("补记正文")},modifier=Modifier.fillMaxWidth().testTag("contribution-text"),minLines=3)
        TextButton(onClick={selecting=!selecting}) { Text("关联一段故事（可选）") }
        if(selecting) state.narrative.rows("records").filter {it.text("status")=="confirmed"&&it.optBoolean("source_valid",true)}.forEach { row ->
            CompanionCheck(row.text("title"),row.text("id") in links,ready) {selected -> links=if(selected) links+row.text("id") else links-row.text("id")}
        }
        RememberActionButton("署名提交，等待审核",ready&&text.isNotBlank(),filled=true,
            pendingLabel="正在提交补记…",successLabel="已提交，等待审核") {
            runCatching { companionPayload(text,state.companionAudio?.takeIf{it.purpose=="contribution"},links.toList()).put("classification",classification) }
                .onSuccess {body -> model.createCompanion("contributions",body) {text="";links=emptySet()} }.onFailure {model.report(it.message?:"请核对补记。")}
        }
    }
    val notes=state.companion.rows("contributions")
    if(notes.isEmpty()) Text("还没有亲友补记。")
    notes.forEach { note -> key(note.text("id")) { CompanionCard(Modifier.testTag("contribution-${note.text("id")}")) {
        Text(note.text("author_display_name").ifBlank {"亲友"}+"的补记",style=MaterialTheme.typography.titleLarge)
        Text(when(note.text("classification")){"firsthand"->"亲身经历";"reported"->"他人转述";else->"个人看法"},style=MaterialTheme.typography.labelLarge)
        Text(when(note.text("status")){"pending"->"待本人审核";"accepted"->"已接受";"disagreement"->"保留不同说法";"rejected"->"已拒绝";else->"已撤回"})
        if(note.text("status")!="withdrawn") {
            Text(note.text("text"))
            if(note.text("status") in setOf("accepted","disagreement")) RememberActionButton("看原文",ready,
                modifier=Modifier.testTag("contribution-original-${note.text("id")}"),pendingLabel="正在读取原文…",successLabel="原文已打开") {model.openContributionOriginal(note.text("id"))}
            if(note.text("audio_id").isNotBlank()) RememberActionButton("听这段补记",ready,pendingLabel="正在取回声音…",successLabel="声音已取回") {model.playCompanionAudio(note.text("audio_id"))}
            if(state.owner) Row(Modifier.horizontalScroll(rememberScrollState())) {
                listOf("accepted" to "接受","disagreement" to "保留不同说法","rejected" to "拒绝").forEach { (decision,title) ->
                    RememberActionButton(title,ready&&note.text("status")!=decision,fullWidth=false,successLabel="已保存") {model.mutation("/companion/contributions/${segment(note.text("id"))}/review","POST",JSONObject().put("revision",note.optInt("revision")).put("decision",decision))}
                }
            }
            if(state.owner||note.text("author_actor_id")==state.actor) {
                val allowed=note.optBoolean(if(state.owner) "model_use_owner_allowed" else "model_use_author_allowed")
                RememberToggle("允许作为署名问答参考",allowed,enabled=ready&&contributionModelUseEditable(note),modifier=Modifier.testTag("contribution-model-use-${note.text("id")}"),onCheckedChange={ value -> model.mutation("/companion/contributions/${segment(note.text("id"))}/model-use","PUT",JSONObject().put("revision",note.optInt("revision")).put("allowed",value)) })
                Text(if(contributionModelUseAllowed(note)) "双方已允许问答参考" else "需要作者与本人分别同意",style=MaterialTheme.typography.bodySmall)
                RememberConfirmedAction("撤回补记","撤回后，正文与附加声音将不再向其他人显示。",true,ready,
                    pendingLabel="正在撤回…",successLabel="已撤回") {model.mutation("/companion/contributions/${segment(note.text("id"))}/withdraw","POST",JSONObject().put("revision",note.optInt("revision")))}
            }
            if(state.owner&&note.text("status") in setOf("accepted","disagreement")) {
                var sharing by remember {mutableStateOf(false)}
                var selected by remember(note.optInt("revision")) {mutableStateOf(note.optJSONArray("recipient_actor_ids")?.let { a -> (0 until a.length()).map {a.getString(it)}.toSet()}?:emptySet())}
                TextButton(onClick={sharing=!sharing},enabled=ready) {Text("选择分享账号")}
                if(sharing) {
                    state.recipients.forEach {person -> val id=person.text("actor_id");CompanionCheck(person.text("display_name"),id in selected,ready){selected=if(it)selected+id else selected-id}}
                    RememberActionButton("保存分享范围",ready,filled=true,successLabel="范围已保存") {model.mutation("/companion/contributions/${segment(note.text("id"))}/recipients","PUT",JSONObject().put("revision",note.optInt("revision")).put("recipient_actor_ids",JSONArray(selected.toList())))}
                }
            }
        }
    } } }
}

@Composable private fun Letters(state: NativeState, model: NativeWorkbenchModel) {
    val ready=!state.busy&&!state.recording
    if(state.owner) CompanionCard {
        var recipient by rememberSaveable(state.actor,state.subject) {mutableStateOf("")}
        var title by rememberSaveable(state.actor,state.subject) {mutableStateOf("")}
        var text by rememberSaveable(state.actor,state.subject) {mutableStateOf("")}
        Text("写一封专属信",style=MaterialTheme.typography.titleLarge)
        Text("这封信只给")
        state.recipients.forEach {person -> Row {RadioButton(recipient==person.text("actor_id"),{recipient=person.text("actor_id")});Text(person.text("display_name"),Modifier.padding(top=12.dp))}}
        if(state.recipients.isEmpty()) Text("先在分享中核对收信账号。")
        OutlinedTextField(title,{title=it},label={Text("标题")},modifier=Modifier.fillMaxWidth())
        AudioDraft("letter",state,model) {text=it}
        OutlinedTextField(text,{text=it},label={Text("想说的话")},modifier=Modifier.fillMaxWidth(),minLines=4)
        RememberActionButton("保存私密草稿",ready&&recipient.isNotBlank()&&title.isNotBlank()&&text.isNotBlank(),filled=true,
            pendingLabel="正在保存草稿…",successLabel="草稿已保存") {
            runCatching { companionPayload(text,state.companionAudio?.takeIf{it.purpose=="letter"}).apply {remove("narrative_ids");put("title",title.trim());put("recipient_actor_id",recipient)} }
                .onSuccess {body->model.createCompanion("letters",body){text="";title=""}}.onFailure {model.report(it.message?:"请核对这封信。")}
        }
    }
    val letters=state.companion.rows("letters")
    if(letters.isEmpty()) Text("目前没有专属信。")
    letters.forEach {letter->key(letter.text("id")) {CompanionCard {
        var editing by remember(letter.optInt("revision")) {mutableStateOf(false)}
        var editedTitle by remember(letter.optInt("revision")) {mutableStateOf(letter.text("title"))}
        var editedText by remember(letter.optInt("revision")) {mutableStateOf(letter.text("text"))}
        Text(letter.text("title"),style=MaterialTheme.typography.titleLarge)
        Text(when(letter.text("status")){"draft"->"私密草稿";"published"->"已发送";else->"已撤销"})
        if(letter.text("status")!="revoked") {
            Text(letter.text("text"))
            if(letter.text("audio_id").isNotBlank()) RememberActionButton("听这封信",ready,pendingLabel="正在取回声音…",successLabel="声音已取回") {model.playCompanionAudio(letter.text("audio_id"))}
            if(state.owner) {
                val name=state.recipients.firstOrNull{it.text("actor_id")==letter.text("recipient_actor_id")}?.text("display_name") ?: "指定收信人"
                Text("收信人：$name")
                if(letter.text("status")=="draft") {
                    TextButton(onClick={editing=!editing},enabled=ready){Text(if(editing) "收起草稿编辑" else "继续写这封信")}
                    if(editing) {
                        OutlinedTextField(editedTitle,{editedTitle=it},label={Text("信的标题")},modifier=Modifier.fillMaxWidth())
                        OutlinedTextField(editedText,{editedText=it},label={Text("信的正文")},modifier=Modifier.fillMaxWidth(),minLines=3)
                        RememberActionButton("保存草稿",ready&&editedTitle.isNotBlank()&&editedText.isNotBlank(),filled=true,successLabel="草稿已保存") {model.mutation("/companion/letters/${segment(letter.text("id"))}","PUT",JSONObject().put("revision",letter.optInt("revision")).put("recipient_actor_id",letter.text("recipient_actor_id")).put("title",editedTitle.trim()).put("text",editedText.trim()).put("audio_id",letter.text("audio_id").takeIf{it.isNotBlank()}?:JSONObject.NULL))}
                    }
                    RememberConfirmedAction("核对收信人后发送","发送给$name？正文与附加声音将一并发送。",false,ready&&!editing,
                        pendingLabel="正在发送…",successLabel="已发送") {model.mutation("/companion/letters/${segment(letter.text("id"))}/publish","POST",JSONObject().put("revision",letter.optInt("revision")).put("confirmed",true))}
                }
                if(letter.text("status")=="published") {
                    val evidence=state.answer?.rows("evidence").orEmpty().map{it.text("evidence_id")}.distinct()
                    if(evidence.isNotEmpty()) RememberConfirmedAction("关联刚才的对话","以后回答引用这段来源时，为本人和指定收信人显示拆信入口。正文仍只在打开信后显示。",false,ready) {
                        model.mutation("/companion/letters/${segment(letter.text("id"))}/recall","PUT",JSONObject().put("revision",letter.optInt("revision")).put("evidence_ids",org.json.JSONArray(evidence)))
                    }
                    TextButton(onClick={model.mutation("/companion/letters/${segment(letter.text("id"))}/recall","PUT",JSONObject().put("revision",letter.optInt("revision")).put("evidence_ids",org.json.JSONArray()))},enabled=ready){Text("取消对话关联")}
                }
                RememberConfirmedAction("撤销这封信","撤销后，收信人将无法继续读取正文与声音。",true,ready,
                    pendingLabel="正在撤销…",successLabel="已撤销") {model.mutation("/companion/letters/${segment(letter.text("id"))}/revoke","POST",JSONObject().put("revision",letter.optInt("revision")))}
            }
        }
    }}}
}

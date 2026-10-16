package me.remember.app.integration

import android.content.Intent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject

private fun sourceKey(row: JSONObject) = row.text("kind")+":"+row.text("id")
internal fun contactSelection(items: List<JSONObject>, selected: Set<String>): JSONObject = JSONObject().put("sources",
    JSONArray(items.filter{sourceKey(it) in selected}.map{JSONObject().put("kind",it.text("kind")).put("id",it.text("id"))}))

internal fun contactPlanStatus(row: JSONObject): String = when(row.text("status")) {
    "revoked" -> "已撤销"
    "expired" -> "已过期"
    "source_changed" -> "原内容已变化，请重新托付"
    else -> when {
        row.text("opened_at").isNotBlank() -> "已打开"
        row.text("claimed_at").isNotBlank() -> "已验证领取"
        row.text("notice_status")=="accepted" -> "通知已提交，待领取"
        row.text("notice_status")=="unconfirmed" -> "通知结果未确认"
        row.text("notice_status")=="sending" -> "通知提交中"
        else -> "待领取"
    }
}

@Composable private fun EntrustCard(content: @Composable ColumnScope.() -> Unit) {
    Surface(Modifier.fillMaxWidth(),shape=RoundedCornerShape(22.dp),color=MaterialTheme.colorScheme.surface.copy(alpha=.96f)) {
        Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp),content=content)
    }
}

@Composable internal fun ContactEntrustmentScreen(state: NativeState, model: NativeWorkbenchModel) {
    key(state.actor,state.subject) { ContactEntrustmentContent(state,model) }
}

@Composable private fun ContactEntrustmentContent(state: NativeState, model: NativeWorkbenchModel) {
    val ready=!state.busy&&!state.recording
    var data by remember {mutableStateOf<JSONObject?>(null)}
    var requested by remember {mutableStateOf(false)}
    var reload by remember {mutableStateOf(false)}
    var step by remember {mutableIntStateOf(-1)}
    var recipient by remember {mutableStateOf("")}
    var channel by remember {mutableStateOf("email")}
    var contact by remember {mutableStateOf("")}
    var title by remember {mutableStateOf("")}
    var message by remember {mutableStateOf("")}
    var days by remember {mutableIntStateOf(30)}
    var selected by remember {mutableStateOf(emptySet<String>())}
    var preview by remember {mutableStateOf<JSONObject?>(null)}
    var confirmed by remember {mutableStateOf(false)}
    var issued by remember {mutableStateOf<JSONObject?>(null)}
    val ownAudio=state.companionAudio?.takeIf{it.purpose=="letter"}?.remote?.text("audio_id").orEmpty()
    var observedAudio by remember {mutableStateOf(ownAudio)}
    val available=data?.rows("sources").orEmpty()
    val capabilities=data?.optJSONObject("capabilities")?:JSONObject()
    val context=LocalContext.current
    val clipboard=LocalClipboardManager.current

    LaunchedEffect(state.busy,state.recording,reload,ownAudio) {
        if(ready&&(!requested||reload||ownAudio!=observedAudio)) {
            requested=true;reload=false
            val added=ownAudio.takeIf{it.isNotBlank()&&it!=observedAudio}
            observedAudio=ownAudio
            model.loadContactEntrustments { result ->
                data=result
                if(added!=null&&step==1&&selected.size<30) selected=selected+("dedicated:$added")
                val channels=result.optJSONObject("capabilities")?:JSONObject()
                if(channel=="email"&&!channels.optBoolean("email")&&channels.optBoolean("sms")) channel="sms"
            }
        }
    }
    EntrustCard {
        Text("把想说的话，留给一个人",style=MaterialTheme.typography.titleLarge)
        Text("一段专属声音，或几段想分享的录音。对方不用注册账号。",style=MaterialTheme.typography.bodyLarge)
        RememberActionButton("新建托付",ready&&data!=null,filled=true,modifier=Modifier.testTag("new-contact-entrustment")) {
            issued=null;step=0;preview=null;confirmed=false
        }
        if(data==null) {
            Text(if(state.busy) "正在读取托付…" else "暂未读取到托付服务。")
            TextButton(onClick={reload=true},enabled=ready) {Text("重新读取")}
        } else if(!capabilities.optBoolean("email")&&!capabilities.optBoolean("sms")) {
            Text("验证码发送服务尚未配置；可先选择内容，配置后再生成领取链接。",color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    val plans=data?.rows("items").orEmpty()
    if(plans.isNotEmpty()) {
        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
            Text("我的托付",Modifier.weight(1f),style=MaterialTheme.typography.titleMedium)
            TextButton(onClick={reload=true},enabled=ready){Text("刷新状态")}
        }
        plans.forEach { row -> EntrustCard {
            Text(row.text("title"),style=MaterialTheme.typography.titleMedium)
            Text("给 ${row.text("recipient_label")} · ${row.text("contact_mask")}")
            Text(contactPlanStatus(row),color=MaterialTheme.colorScheme.primary)
            Text("${row.optInt("source_count")} 段声音 · ${row.text("expires_at").take(10)} 到期",style=MaterialTheme.typography.bodyMedium)
            if(row.text("status")=="active") {
                RememberActionButton("领取链接与通知",ready) {
                    model.contactEntrustmentAction("/${segment(row.text("id"))}/link") {link ->
                        issued=JSONObject(row.toString()).put("claim_url",link.text("claim_url"));step=3
                    }
                }
                RememberConfirmedAction("撤销托付","对方将无法继续领取或请求内容。已听到、复制或下载的内容无法收回。",true,ready) {
                    model.contactEntrustmentAction("/${segment(row.text("id"))}/revoke",JSONObject().put("revision",row.optInt("revision"))) {reload=true}
                }
            }
        } }
    }
    if(step>=0) NativeDialog(if(step==3) "托付已准备好" else "留给你 · ${step+1}/3",{
        if(ready){step=-1;preview=null;confirmed=false}
    }) {
        state.error?.let {Text(it,color=MaterialTheme.colorScheme.error)}
        when(step) {
            0 -> {
                Text("这份内容，留给谁？",style=MaterialTheme.typography.headlineSmall)
                OutlinedTextField(recipient,{recipient=it.take(80)},label={Text("怎么称呼对方")},singleLine=true,enabled=ready,modifier=Modifier.fillMaxWidth())
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    FilterChip(channel=="email",{channel="email";contact=""},label={Text("邮箱")},enabled=ready)
                    FilterChip(channel=="sms",{channel="sms";contact=""},label={Text("手机号")},enabled=ready)
                }
                OutlinedTextField(contact,{contact=it.take(254)},label={Text(if(channel=="email") "对方的邮箱" else "中国大陆手机号")},
                    keyboardOptions=KeyboardOptions(keyboardType=if(channel=="email") KeyboardType.Email else KeyboardType.Phone),
                    singleLine=true,enabled=ready,modifier=Modifier.fillMaxWidth())
                Text("领取时，对方需要用这个联系方式接收验证码。")
                RememberActionButton("选择想留下的内容",ready&&recipient.isNotBlank()&&contact.isNotBlank(),filled=true){step=1}
            }
            1 -> {
                Text("你想留下什么？",style=MaterialTheme.typography.headlineSmall)
                OutlinedTextField(title,{title=it.take(120)},label={Text("给这份托付起个名字")},singleLine=true,enabled=ready,modifier=Modifier.fillMaxWidth())
                AudioDraft("letter",state,model,audioOnly=true) { }
                Text("从已保存的录音选择 · ${selected.size}/30",style=MaterialTheme.typography.titleMedium)
                if(available.isEmpty()) Text("还没有可选录音。可以先录一段，或直接写下留言。")
                available.forEach { row ->
                    val id=sourceKey(row)
                    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                        Checkbox(id in selected,{checked -> selected=if(checked)selected+id else selected-id},enabled=ready&&(id in selected||selected.size<30))
                        Column(Modifier.weight(1f)) {
                            Text(row.text("title"),style=MaterialTheme.typography.titleSmall)
                            if(row.text("text").isNotBlank()) Text(row.text("text"),maxLines=2,style=MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
                OutlinedTextField(message,{message=it.take(10000)},label={Text("想说的话（可选）")},minLines=3,enabled=ready,modifier=Modifier.fillMaxWidth())
                TextButton(onClick={step=0},enabled=ready){Text("返回接收人")}
                RememberActionButton("核对这份托付",ready&&title.isNotBlank()&&(selected.isNotEmpty()||message.isNotBlank()),filled=true) {
                    model.contactEntrustmentAction("/preview",contactSelection(available,selected)) {result ->preview=result;confirmed=false;step=2}
                }
            }
            2 -> {
                Text("${title.trim()} · 给${recipient.trim()}",style=MaterialTheme.typography.headlineSmall)
                Text(contact.trim())
                if(message.isNotBlank()) Text(message.trim())
                preview?.rows("items")?.forEach { row -> EntrustCard {
                    Text(row.text("title"),style=MaterialTheme.typography.titleMedium)
                    Text("完整原音")
                    if(row.text("text").isNotBlank()) Text(row.text("text"))
                    if(row.text("supplement").isNotBlank()) Text(row.text("supplement"))
                    RememberActionButton("试听",ready) {
                        if(row.text("kind")=="dedicated") model.playCompanionAudio(row.text("id")) else model.playSource(row.text("id"))
                    }
                } }
                Text("链接有效期",style=MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    listOf(7,30,90).forEach {d ->FilterChip(days==d,{days=d},label={Text("$d 天")},enabled=ready)}
                }
                Row(verticalAlignment=Alignment.CenterVertically) {
                    Checkbox(confirmed,{confirmed=it},enabled=ready)
                    Text("确认只向这位接收人开放上面的完整原音和文字。",Modifier.weight(1f))
                }
                if(!capabilities.optBoolean(channel)) Text("${if(channel=="sms") "短信" else "邮件"}验证码尚未配置，暂不能生成可领取链接。",color=MaterialTheme.colorScheme.error)
                TextButton(onClick={step=1;confirmed=false},enabled=ready){Text("返回修改")}
                RememberActionButton("确认并生成领取链接",ready&&confirmed&&capabilities.optBoolean(channel),filled=true,
                    pendingLabel="正在保存托付…",successLabel="领取链接已生成") {
                    val body=contactSelection(available,selected).put("recipient_label",recipient.trim()).put("channel",channel)
                        .put("contact",contact.trim()).put("title",title.trim()).put("message",message.trim()).put("days",days)
                        .put("source_version",preview!!.text("source_version")).put("confirmed",true)
                    model.contactEntrustmentAction("",body) { result ->
                        issued=result;step=3;reload=true;recipient="";contact="";title="";message="";selected=emptySet();preview=null;confirmed=false
                    }
                }
            }
            3 -> issued?.let { row ->
                Text(row.text("title"),style=MaterialTheme.typography.headlineSmall)
                Text("留给 ${row.text("recipient_label")} · ${row.text("contact_mask")}")
                Text("对方打开链接并接收验证码，就能听到这份内容。")
                Text(contactPlanStatus(row),style=MaterialTheme.typography.titleMedium)
                RememberActionButton("分享领取链接",ready,filled=true) {
                    context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                        type="text/plain";putExtra(Intent.EXTRA_TEXT,"勿忘我 · 有一份留给你的内容\n${row.text("claim_url")}")
                    },"把领取链接发给对方"))
                }
                TextButton(onClick={
                    clipboard.setText(AnnotatedString(row.text("claim_url")))
                    android.widget.Toast.makeText(context,"领取链接已复制",android.widget.Toast.LENGTH_SHORT).show()
                },enabled=ready) {Text("复制链接")}
                if(capabilities.optBoolean("notice_"+row.text("channel"))) RememberConfirmedAction("发送领取通知",
                    "向 ${row.text("contact_mask")} 发送一条领取链接通知？",false,ready) {
                    model.contactEntrustmentAction("/${segment(row.text("id"))}/notify") {result ->
                        issued=result.put("claim_url",row.text("claim_url"));reload=true
                    }
                }
                Text("你可以在“我的托付”查看领取状态或撤销。",style=MaterialTheme.typography.bodyMedium)
                RememberActionButton("完成",ready){step=-1}
            }
        }
    }
}

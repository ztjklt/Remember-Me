package me.remember.app.integration

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import org.json.JSONArray
import org.json.JSONObject

private val kinds = linkedMapOf("story" to "故事", "person" to "人物", "observation" to "情境观察", "letter" to "给你的话", "style" to "表达范例")
private fun strings(row: JSONObject, key: String): List<String> = row.optJSONArray(key)?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: emptyList()
private fun payload(row: JSONObject): JSONObject = JSONObject().apply {
    listOf("kind","title","text","evidence_ids","facets","time_text","place_text","aliases","same_event","recipient_label").forEach { if(row.has(it)) put(it,row.get(it)) }
}

@Composable fun NarrativeQuestion(state: NativeState, model: NativeWorkbenchModel) {
    val question=state.narrative.optJSONObject("next_question") ?: return
    var answering by remember(state.subject,question.text("id")) { mutableStateOf(false) }
    Text("如果愿意，再聊一点",style=MaterialTheme.typography.titleLarge)
    Text(question.text("text"));Text(question.text("reason"),style=MaterialTheme.typography.bodySmall)
    if(answering) Text("可以在下方录音回答。完成核对后，在待答问题中关联新录音；授权需要另外确认。")
    Row(Modifier.horizontalScroll(rememberScrollState())) {
        TextButton(onClick={answering=true},enabled=!state.busy&&!state.recording){Text("就聊这个")}
        listOf("snoozed" to "稍后","declined" to "跳过").forEach { (value,title) -> TextButton(onClick={model.mutation("/narrative/next-question","POST",JSONObject().put("id",question.text("id")).put("action",value))},enabled=!state.busy&&!state.recording){Text(title)} }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable fun NarrativeScreen(state: NativeState, model: NativeWorkbenchModel, openSource: (String) -> Unit) {
    val data = state.narrative
    if(!data.has("views")) { Text("当前服务尚未提供故事组织，请更新服务后使用。"); return }
    var selectedView by remember(state.subject) { mutableIntStateOf(0) }
    var query by remember(state.subject) { mutableStateOf("") }
    var editor by remember(state.subject) { mutableStateOf<JSONObject?>(null) }
    var history by remember(state.subject) { mutableStateOf<JSONObject?>(null) }
    var relatedId by remember(state.actor,state.subject) { mutableStateOf<String?>(null) }
    var feelingsOnly by remember(state.subject) { mutableStateOf(false) }
    var auditQueue by remember(state.subject) { mutableStateOf(false) }
    val ready = !state.busy && !state.recording
    Text("慢慢认识一个人", style = MaterialTheme.typography.headlineMedium)
    Text("沿着故事，听见经历，也看见变化。", style = MaterialTheme.typography.bodyLarge)
    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), maxItemsInEachRow = 2) {
        data.rows("views").forEachIndexed { index, view -> FilterChip(selectedView == index, { selectedView = index; auditQueue = false }, label = { Text(view.text("title")) }, modifier = Modifier.fillMaxWidth(.47f)) }
    }
    OutlinedTextField(query, { query = it }, label = { Text("找故事、人名或一件旧物") }, modifier = Modifier.fillMaxWidth())
    if(selectedView==0) FilterChip(feelingsOnly,{feelingsOnly=!feelingsOnly},label={Text("本人感受回看")})
    val records = data.rows("records")
    if(state.owner) {
        val availableEpisodes=data.rows("source_evidence").map{it.text("episode_id")}.distinct()
        var episodes by remember(state.subject) { mutableStateOf(availableEpisodes.take(2).toSet()) }
        var choosing by remember(state.subject) { mutableStateOf(false) }
        var toolsExpanded by remember(state.subject) { mutableStateOf(false) }
        val pending = records.count { it.text("status") == "pending" || it.text("status") == "stale" }
        TextButton(onClick = { auditQueue = !auditQueue }) { Text(if(auditQueue) "返回已核对内容" else "待核对 $pending 项") }
        TextButton(onClick={toolsExpanded=!toolsExpanded}){Text(if(toolsExpanded) "收起整理工具" else "整理故事 / 留下寄语")}
        if(toolsExpanded) {
        var consent by remember(state.subject) { mutableStateOf(false) }
        Row { Checkbox(consent, { consent = it }, enabled = ready); Text("将已核对的有效文字交由云端组织故事；不会自动确认或分享。", Modifier.weight(1f)) }
        TextButton(onClick={choosing=!choosing}) { Text("本次对照 ${episodes.size} 段录音 · 建议先选一到两段") }
        if(choosing) state.stories.filter{it.text("episode_id") in availableEpisodes}.forEach { story -> Row {
            Checkbox(story.text("episode_id") in episodes,{episodes=if(it)episodes+story.text("episode_id") else episodes-story.text("episode_id")})
            Text(story.text("recorded_at")+" · "+story.text("transcript").take(40),Modifier.weight(1f))
        } }
        Button(onClick = { model.organizeNarrative(consent,episodes.toList()) }, enabled = ready && consent && episodes.isNotEmpty()) { Text("整理选定讲述") }
        TextButton(onClick = { editor = JSONObject().put("kind","story").put("title","").put("text","").put("facets",JSONArray().put("EXPERIENCE")).put("evidence_ids",JSONArray()) }, enabled = ready) { Text("从原文组织一段故事 / 留下寄语") }
        state.narrativeJobs.take(2).forEach { Text(when(it.text("status")) { "queued" -> "整理已排队"; "running" -> "正在整理，原音已经保留"; "complete" -> "整理完成，请核对建议"; else -> "整理未完成：${it.text("error")}" }, style = MaterialTheme.typography.bodySmall) }
        }
    }
    val currentView = data.rows("views").getOrNull(selectedView)
    val visibleIds = currentView?.let { strings(it,"records").toSet() } ?: emptySet()
    val shown = records.filter { row -> (if(auditQueue) row.text("status") in setOf("pending","stale") else row.text("id") in visibleIds) && (selectedView!=0 || !feelingsOnly || "FEELINGS" in strings(row,"facets")) && (query.isBlank() || (row.text("title")+row.text("text")+row.text("place_text")+row.text("aliases")).contains(query)) }
    if(shown.isEmpty()) Text(if(auditQueue) "暂时没有需要核对的建议。" else "这里尚无已核对的材料。原有录音与记忆仍可在档案中查看。")
    shown.forEach { row -> key(row.text("id")) {
        var expanded by remember { mutableStateOf(false) }
        Column(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(kinds[row.text("kind")].orEmpty()+" · "+statusName(row.text("status")), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(row.text("title"), style = MaterialTheme.typography.titleLarge)
            Text(row.text("text"), style = MaterialTheme.typography.bodyLarge)
            if(row.text("time_text").isNotBlank()) Text("发生时间：${row.text("time_text")}")
            if(row.text("place_text").isNotBlank()) Text("当时地点：${row.text("place_text")}")
            if(row.text("recipient_label").isNotBlank()) Text("想留给：${row.text("recipient_label")} · 仍按录音授权")
            TextButton(onClick = { expanded = !expanded }) { Text(if(expanded) "收起依据" else "为什么这样整理 · 听原声") }
            if(expanded) row.rows("evidence").forEach { source ->
                Text("“${source.text("excerpt")}”", style = MaterialTheme.typography.bodyLarge)
                Text(if(source.text("source_type") == "CALIBRATION") "本人书面补充 / 修订" else "核对文字 · 不代表音频逐字对齐", style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = { openSource(source.text("episode_id")) }, enabled = ready) { Text("打开来源与完整原音") }
            }
            val linked = relatedNarrativeStories(row,records)
            if(linked.isNotEmpty()) {
                Text("从这些故事继续了解",style=MaterialTheme.typography.titleMedium)
                Text("这些内容共用原文依据；不代表系统判定了关系或亲密程度。",style=MaterialTheme.typography.bodySmall)
                linked.forEach { story -> TextButton(onClick={relatedId=story.text("id")},enabled=ready) { Text("读故事："+story.text("title")) } }
            }
            if(state.owner) {
                if(row.text("status") == "pending") Button(onClick = { model.mutation("/narrative/records/${row.text("id")}/confirm","POST",JSONObject().put("revision",row.getInt("revision"))) }, enabled = ready) { Text("核对无误，确认整理") }
                FlowRow(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { editor = row }, enabled = ready) { Text("编辑 / 移出来源") }
                    TextButton(onClick = { model.narrativeHistory(row.text("id")){history=it} }, enabled = ready) { Text("变化历史") }
                    if(row.text("kind") == "story") TextButton(onClick = { editor = JSONObject(row.toString()).put("split",true).put("title",row.text("title")+" · 拆分") }, enabled = ready) { Text("拆出新故事") }
                    TextButton(onClick = { model.mutation("/narrative/records/${row.text("id")}/reject","POST",JSONObject().put("revision",row.getInt("revision"))) }, enabled = ready) { Text("撤回这项整理") }
                    if(row.optInt("revision") > 2) TextButton(onClick = { model.mutation("/narrative/records/${row.text("id")}/undo","POST",JSONObject().put("revision",row.getInt("revision"))) }, enabled = ready) { Text("恢复旧内容再核对") }
                }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        }
    } }
    if(selectedView == 2) data.rows("understandings").forEach { item ->
        var show by remember(item.text("candidate_id")) { mutableStateOf(false) }
        Text(item.text("statement"), style = MaterialTheme.typography.titleMedium)
        Text("适用情境：${item.text("context")}")
        Text(item.text("label")+" · "+statusName(item.text("status")), style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = { show = !show }) { Text("支持、例外与依据") }
        if(show) {
            Text("已确认独立事件：${item.optInt("independent_events")}；材料数量不代表准确率。")
            listOf("支持" to item.rows("evidence"),"例外 / 反例" to item.rows("counter_evidence")).forEach { (label,refs) -> refs.forEach { e -> Text(label+"："+e.text("excerpt")); TextButton(onClick={openSource(e.text("episode_id"))}) { Text("查看这条依据") } } }
        }
    }
    if(selectedView == 3 && state.owner) {
        val pref=data.optJSONObject("style")?:JSONObject()
        Row { Switch(pref.optBoolean("enabled"), { model.mutation("/narrative/style","PUT",JSONObject().put("enabled",it).put("revision",pref.optInt("revision"))) }, enabled=ready)
            Text("允许使用已确认的表达范例；回应仍标明系统生成。",Modifier.weight(1f)) }
    }
    Text(data.text("notice"),style=MaterialTheme.typography.bodySmall)
    relatedId?.let { id ->
        // Look up live state on each render. A cached JSONObject could outlive a
        // revocation or correction during the open sheet.
        val story=records.firstOrNull{it.text("id")==id&&it.text("status")=="confirmed"&&it.optBoolean("source_valid")}
        Dialog(onDismissRequest={relatedId=null}) { Surface(shape=MaterialTheme.shapes.large,color=MaterialTheme.colorScheme.surface.copy(alpha=1f)) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                TextButton(onClick={relatedId=null}) { Text("返回人物") }
                if(story==null) Text("相关内容已经变化，请返回刷新后的资料。") else {
                    Text(story.text("title"),style=MaterialTheme.typography.titleLarge)
                    if(story.text("time_text").isNotBlank()) Text("发生时间："+story.text("time_text"))
                    Text(story.text("text"),style=MaterialTheme.typography.bodyLarge)
                    story.rows("evidence").forEach { source ->
                        Text("“${source.text("excerpt")}”")
                        TextButton(onClick={relatedId=null;openSource(source.text("episode_id"))},enabled=ready){Text("打开故事原音")}
                    }
                }
            }
        } }
    }
    history?.let { log -> Dialog(onDismissRequest={history=null}) { Surface(shape=MaterialTheme.shapes.large,color=MaterialTheme.colorScheme.surface.copy(alpha=1f)) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Text("理解怎样改变",style=MaterialTheme.typography.titleLarge)
            log.rows("items").forEach { item -> Text("版本 ${item.optInt("revision")} · ${item.text("action")} · ${item.text("created_at")}");Text(item.optJSONObject("record")?.text("text").orEmpty()) }
            TextButton(onClick={history=null}) { Text("返回") }
        }
    } } }
    editor?.let { row -> NarrativeEditor(row,data.rows("source_evidence"),data.rows("facets"),{editor=null}) { edited ->
        val id=row.text("id"); if(id.isNotBlank()) edited.put("revision",row.getInt("revision"))
        model.mutation("/narrative/records"+(if(id.isBlank()) "" else "/$id")+(if(row.optBoolean("split")) "/split" else ""),if(id.isBlank() || row.optBoolean("split")) "POST" else "PUT",edited,onSuccess={editor=null})
    } }
}

private fun statusName(value:String)=mapOf("confirmed" to "本人已核对","pending" to "待核对","stale" to "来源已变化","rejected" to "已撤回","conflicted" to "存在不同说法","superseded" to "历史版本")[value]?:value

@Composable private fun NarrativeEditor(row:JSONObject,sources:List<JSONObject>,facets:List<JSONObject>,close:()->Unit,save:(JSONObject)->Unit) {
    var kind by remember { mutableStateOf(row.text("kind")) };var title by remember { mutableStateOf(row.text("title")) }
    var text by remember { mutableStateOf(row.text("text")) };var time by remember { mutableStateOf(row.text("time_text")) }
    var place by remember { mutableStateOf(row.text("place_text")) };var recipient by remember { mutableStateOf(row.text("recipient_label")) }
    var same by remember { mutableStateOf(row.optBoolean("same_event")) };var refs by remember { mutableStateOf(strings(row,"evidence_ids").toSet()) }
    var selectedFacets by remember { mutableStateOf(strings(row,"facets").toSet()) }
    var aliases by remember { mutableStateOf(strings(row,"aliases").joinToString("、")) }
    Dialog(close,properties=DialogProperties(usePlatformDefaultWidth=false)) {
        Surface(Modifier.fillMaxWidth().fillMaxHeight(.92f).padding(12.dp),shape=MaterialTheme.shapes.large,color=MaterialTheme.colorScheme.surface.copy(alpha=1f)) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                Text("让故事更完整",style=MaterialTheme.typography.headlineSmall); TextButton(onClick=close){Text("返回")}
                if(row.text("id").isBlank()) Row(Modifier.horizontalScroll(rememberScrollState())) { kinds.forEach { (id,label) -> FilterChip(kind==id,{kind=id;if(id in setOf("style","letter"))selectedFacets=setOf("EXPRESSION");if(id!="story")same=false},label={Text(label)}) } }
                OutlinedTextField(title,{title=it},label={Text("标题")},modifier=Modifier.fillMaxWidth())
                OutlinedTextField(text,{text=it},label={Text(if(kind in setOf("letter","style")) "逐字选取本人原话" else "内容与适用情境")},minLines=3,modifier=Modifier.fillMaxWidth())
                OutlinedTextField(time,{time=it},label={Text("发生时间原文（可留空）")},modifier=Modifier.fillMaxWidth())
                OutlinedTextField(place,{place=it},label={Text("地点原文（可留空）")},modifier=Modifier.fillMaxWidth())
                if(kind=="person") OutlinedTextField(aliases,{aliases=it},label={Text("明确是同一人的称呼，用顿号分隔")},modifier=Modifier.fillMaxWidth())
                if(kind=="letter") OutlinedTextField(recipient,{recipient=it},label={Text("想留给谁（不会自动授权）")},modifier=Modifier.fillMaxWidth())
                if(kind=="story") Row { Checkbox(same,{same=it});Text("这些来源讲的是同一次事件，重复讲述只算一次。",Modifier.weight(1f)) }
                Text("内容维度，可多选")
                facets.forEach { f -> Row { Checkbox(f.text("id") in selectedFacets,{selectedFacets=if(it)selectedFacets+f.text("id") else selectedFacets-f.text("id")});Text(f.text("title"),Modifier.weight(1f)) } }
                Text("选择依据；移出来源后需要重新核对。",style=MaterialTheme.typography.titleMedium)
                sources.forEach { e -> Row { Checkbox(e.text("evidence_id") in refs,{refs=if(it)refs+e.text("evidence_id") else refs-e.text("evidence_id")});Text(e.text("excerpt"),Modifier.weight(1f)) } }
                Button(onClick={save(JSONObject().put("kind",kind).put("title",title).put("text",text).put("time_text",time).put("place_text",place).put("recipient_label",recipient).put("same_event",same).put("aliases",JSONArray(aliases.split('、').filter{it.isNotBlank()})).put("facets",JSONArray(selectedFacets.toList())).put("evidence_ids",JSONArray(refs.toList())))},enabled=title.isNotBlank()&&text.isNotBlank()&&refs.isNotEmpty()&&selectedFacets.isNotEmpty(),modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text("保存为待核对内容")}
            }
        }
    }
}

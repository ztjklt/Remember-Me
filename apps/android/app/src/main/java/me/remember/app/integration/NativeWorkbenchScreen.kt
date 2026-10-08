package me.remember.app.integration

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.remember.app.core.designsystem.NatureScene
import me.remember.app.core.designsystem.RememberMeBrand
import me.remember.app.core.designsystem.atmosphere
import org.json.JSONObject

@Composable
fun NativeWorkbenchScreen(model: NativeWorkbenchModel) {
    val state by model.ui.collectAsStateWithLifecycle()
    val localPlayer by model.audio.playback.collectAsStateWithLifecycle()
    var server by remember { mutableStateOf("http://127.0.0.1:8877") }
    var token by remember { mutableStateOf("") }
    var tab by remember(state.actor, state.subject) { mutableIntStateOf(0) }
    var detail by remember(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var revision by remember(state.actor, state.subject) { mutableStateOf<RevisionTarget?>(null) }
    var confirm by remember(state.actor, state.subject) { mutableStateOf<Pair<String, () -> Unit>?>(null) }
    val scene = when(tab) { 1 -> NatureScene.Forest; 2 -> NatureScene.Lake; 3 -> NatureScene.Coast; else -> NatureScene.Meadow }
    val ready = !state.busy && !state.recording
    Scaffold(containerColor = androidx.compose.ui.graphics.Color.Transparent) { inset ->
        Column(Modifier.fillMaxSize().atmosphere(scene = scene).padding(inset).padding(horizontal = 16.dp)) {
            Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                RememberMeBrand(size = 42.dp)
                Column { Text("Remember Me", style = MaterialTheme.typography.titleLarge); Text("原音、核对文字与可追溯的记忆", style = MaterialTheme.typography.bodySmall) }
            }
            if(state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(vertical = 8.dp)) }
            if(state.actor.isBlank()) {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("进入自己的空间", style = MaterialTheme.typography.headlineMedium)
                    Text("使用后端签发的身份凭据。当前账号和读者权限由服务器确认。凭据仅存于本次会话。")
                    OutlinedTextField(server, { server = it }, label = { Text("共享后端地址") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                    OutlinedTextField(token, { token = it }, label = { Text("身份凭据") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                        visualTransformation = PasswordVisualTransformation())
                    Button(onClick = { model.connect(server, token); token = "" }, enabled = !state.busy && token.isNotBlank()) { Text("进入空间") }
                    Text("手机和模拟器先运行 adb reverse tcp:8877 tcp:8877，再使用 http://127.0.0.1:8877 连接共享工作台。HTTP 只允许本机或私有局域网。", style = MaterialTheme.typography.bodySmall)
                    Text("每日提醒：关闭。录音、上传和云端文字处理均由你主动发起。", style = MaterialTheme.typography.bodySmall)
                }
            } else {
                Text("${state.actorName} · ${state.actor}", style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = model::refresh, enabled = ready) { Text("刷新") }
                    TextButton(onClick = model::logout, enabled = !state.busy) { Text("退出身份") }
                }
                var spacesExpanded by remember(state.actor) { mutableStateOf(false) }
                Box {
                    OutlinedButton(onClick = { spacesExpanded = true }, enabled = ready) {
                        Text(state.space?.let { "${it.text("display_name")} · ${if(state.owner) "记录者" else "授权读者"}" } ?: "暂无授权空间")
                    }
                    DropdownMenu(spacesExpanded, { spacesExpanded = false }) {
                        state.spaces.forEach { space -> DropdownMenuItem(text = { Text(space.text("display_name") + " · " + space.text("role")) },
                            onClick = { spacesExpanded = false; model.selectSpace(space) }) }
                    }
                }
                if(state.notice.isNotBlank()) Text(state.notice, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 8.dp))
                if(state.player.episode.isNotBlank()) Panel {
                    Text("来源完整原音 · 不提供未经验证的片段时间", style = MaterialTheme.typography.bodySmall)
                    Text("${clock(state.player.position)} / ${clock(state.player.duration)}")
                    if(!state.player.preparing) {
                        Slider(state.player.position.toFloat(), { model.seekSource(it.toLong()) }, valueRange = 0f..state.player.duration.coerceAtLeast(1).toFloat())
                        Row { TextButton(onClick = { if(state.player.playing) model.pauseSource() else model.resumeSource() }) { Text(if(state.player.playing) "暂停" else "继续播放") }
                            TextButton(onClick = model::stopSource) { Text("停止播放") } }
                    } else Text("正在准备原音…")
                }
                if(localPlayer.audioPath != null) Panel {
                    Text("本机原音 ${clock(localPlayer.positionMillis)} / ${clock(localPlayer.durationMillis)}")
                    Slider(localPlayer.positionMillis.toFloat(), { model.audio.seekPlayback(it.toLong()) }, enabled = !localPlayer.preparing,
                        valueRange = 0f..localPlayer.durationMillis.coerceAtLeast(1).toFloat())
                    Row { TextButton(onClick = { if(localPlayer.playing) model.audio.pausePlayback() else model.audio.resumePlayback() }) { Text(if(localPlayer.playing) "暂停" else "继续播放") }
                        TextButton(onClick = model.audio::stopPlayback) { Text("停止本机播放") } }
                }
                if(state.subject.isNotBlank()) {
                    ScrollableTabRow(tab, edgePadding = 0.dp) {
                        listOf("记述", "故事", "提问", "管理").forEachIndexed { index, name ->
                            Tab(tab == index, { tab = index }, enabled = !state.recording, text = { Text(name) })
                        }
                    }
                    Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        when(tab) {
                            0 -> CaptureTab(state, model, revision, { revision = it })
                            1 -> {
                                Text("来自实际录音的故事", style = MaterialTheme.typography.headlineMedium)
                                if(state.stories.isEmpty()) Text("暂无可见故事。")
                                state.stories.forEach { story -> StoryCard(story, state.owner, ready,
                                    { detail = story.text("episode_id") }, { model.review(story.text("episode_id")) }, { model.retry(story.text("episode_id"), story.optBoolean("can_reextract_empty")) }) }
                            }
                            2 -> AskTab(state, model)
                            3 -> ManageTab(state, model) { message, action -> confirm = message to action }
                        }
                        Spacer(Modifier.height(28.dp))
                    }
                }
            }
        }
    }
    detail?.let { id ->
        state.stories.firstOrNull { it.text("episode_id") == id }?.let { story ->
            NativeDialog("故事与来源", { detail = null }) {
                Text(story.text("recorded_at"), style = MaterialTheme.typography.bodySmall)
                if(story.optBoolean("unavailable")) Text(story.text("notice")) else {
                    var showRawTranscript by remember(id) { mutableStateOf(false) }
                    Action("播放完整原音", ready) { detail = null; model.playSource(id) }
                    Text(if(story.optBoolean("waiting_for_review")) "机器转写 · 尚未核对" else "核对文字", style = MaterialTheme.typography.titleMedium)
                    Text(story.text("transcript").ifBlank { "转写尚未完成。" })
                    if(state.owner && story.text("machine_transcript").isNotBlank()) {
                        TextButton(onClick = { showRawTranscript = !showRawTranscript }) {
                            Text(if(showRawTranscript) "收起机器原始输出" else "查看机器原始输出（保留原始字形）")
                        }
                        if(showRawTranscript) Text(story.text("machine_transcript"))
                    }
                    story.rows("memories").forEach { memory -> Panel {
                        Text(memory.text("content"))
                        Text("系统整理 · ${memory.text("source_type")} · ${memory.text("review_state")}", style = MaterialTheme.typography.bodySmall)
                        memory.rows("evidence").forEach { evidence -> Text("依据：${evidence.text("excerpt")}", style = MaterialTheme.typography.bodySmall) }
                        if(state.owner && memory.text("review_state") == "active") {
                            Action("用新录音补充、纠正或说明变化", ready) {
                                revision = RevisionTarget(memory.text("memory_item_id"), "supplement", ""); detail = null; tab = 0
                            }
                            Action("删除这条记忆", ready) {
                                confirm = "删除这条记忆并使相关回答失效？完整原音和核对文字会保留。" to {
                                    detail = null; model.mutation("/memories/${segment(memory.text("memory_item_id"))}", "DELETE", subjectApi = true)
                                }
                            }
                        }
                    } }
                    Text("转写：${story.text("stt_model_version")} · 整理：${story.text("model_version")}", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
    state.reviewEpisode?.let { id ->
        var cloud by remember(id) { mutableStateOf(false) }
        NativeDialog("请听原音并核对文字", model::closeReview) {
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Text("请修正识别错误，保留原意。确认之后才开始记忆整理。")
            Action("播放原音", ready) { model.playSource(id) }
            if(state.player.episode == id) {
                Text("${clock(state.player.position)} / ${clock(state.player.duration)}")
                if(!state.player.preparing) {
                    Slider(state.player.position.toFloat(), { model.seekSource(it.toLong()) }, valueRange = 0f..state.player.duration.coerceAtLeast(1).toFloat())
                    Action(if(state.player.playing) "暂停核对原音" else "继续核对原音") { if(state.player.playing) model.pauseSource() else model.resumeSource() }
                }
                Action("停止核对原音") { model.stopSource() }
            }
            OutlinedTextField(state.reviewText, { model.editReview(id, it) }, label = { Text("核对后的文字") }, modifier = Modifier.fillMaxWidth(), minLines = 6)
            Check("我确认文字已核对，并同意将这些文字交由服务器配置的云端模型整理。", cloud, { cloud = it })
            Action("确认文字并整理", ready && cloud && state.reviewText.isNotBlank()) { model.confirmReview(state.reviewText, cloud) }
        }
    }
    confirm?.let { (message, action) -> AlertDialog(onDismissRequest = { confirm = null }, title = { Text("确认操作") }, text = { Text(message) },
        confirmButton = { TextButton(onClick = { confirm = null; action() }, enabled = ready) { Text("确认") } },
        dismissButton = { TextButton(onClick = { confirm = null }) { Text("取消") } }) }
}

@Composable private fun CaptureTab(state: NativeState, model: NativeWorkbenchModel, revision: RevisionTarget?, setRevision: (RevisionTarget?) -> Unit) {
    if(!state.owner) { Text("这里可以查看记录者授权的故事。你也可以在管理页提出想了解的问题。"); return }
    var localConsent by remember(state.actor, state.subject) { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if(granted) model.start(revision) else model.report("麦克风权限未授予。可在 Android 系统设置中允许后重试。")
    }
    Text("留下一段今天的记述", style = MaterialTheme.typography.headlineMedium)
    Text("先录在本机；停止后原音会保留，上传和文字整理分别确认。")
    revision?.let { selected -> Panel {
        Text("关联旧记忆：${state.stories.flatMap { it.rows("memories") }.firstOrNull { it.text("memory_item_id") == selected.memory }?.text("content") ?: selected.memory}")
        listOf("supplement" to "补充", "correction" to "纠正", "change" to "情况变化").forEach { (kind, label) ->
            Row { RadioButton(selected.kind == kind, onClick = { setRevision(selected.copy(kind = kind)) }, enabled = !state.recording); Text(label, Modifier.padding(top = 12.dp)) }
        }
        if(selected.kind == "change") OutlinedTextField(selected.time, { setRevision(selected.copy(time = it)) }, label = { Text("变化时间（不确定也请说明）") }, modifier = Modifier.fillMaxWidth(), enabled = !state.recording)
        Action("取消关联，记录新故事", !state.recording) { setRevision(null) }
    } }
    Check("我同意本次麦克风录音，原音保存于此设备。", localConsent, { localConsent = it }, !state.recording)
    if(state.recording) {
        Text("${if(state.paused) "已暂停" else "正在录音"} ${clock(state.elapsed)}", style = MaterialTheme.typography.headlineMedium)
        Action(if(state.paused) "继续录音" else "暂停录音", !state.busy) { model.pauseOrResumeRecording() }
        Action("停止并保留原音", !state.busy) { model.finish(); setRevision(null) }
    } else Action("开始录音", !state.busy && localConsent && (revision?.kind != "change" || revision.time.isNotBlank())) {
        permission.launch(Manifest.permission.RECORD_AUDIO)
    }
    Text("本机原音", style = MaterialTheme.typography.titleLarge)
    if(state.local.isEmpty()) Text("当前身份和空间尚无本机录音。")
    state.local.forEach { capture -> Panel {
        var uploadConsent by remember(capture.key) { mutableStateOf(false) }
        Text(capture.recording.createdAt + " · " + clock(capture.recording.durationMillis))
        Text(if(capture.episode.isBlank()) "尚未上传" else if(!capture.linked) "已上传，关联未完成，请重试" else "已上传 · ${capture.episode}", style = MaterialTheme.typography.bodySmall)
        capture.revision?.let { Text("${kindName(it.kind)}旧记忆；关联完成后才可确认转写。", style = MaterialTheme.typography.bodySmall) }
        Action("播放本机原音", !state.busy && !state.recording) { model.playLocal(capture) }
        if(!capture.linked) {
            Check("同意上传这段原音到共享后端并转写（本机文件继续保留）。", uploadConsent, { uploadConsent = it })
            Action(if(capture.episode.isBlank()) "上传并等待核对" else "重试上传与关联", !state.busy && !state.recording && uploadConsent) { model.upload(capture, uploadConsent) }
        }
    } }
}

@Composable private fun StoryCard(story: JSONObject, owner: Boolean, enabled: Boolean, open: () -> Unit, review: () -> Unit, retry: () -> Unit) = Panel {
    Text(storyTitle(story), style = MaterialTheme.typography.titleMedium)
    Text(story.text("recorded_at") + " · " + if(story.optBoolean("waiting_for_review")) "待核对文字" else story.text("status"), style = MaterialTheme.typography.bodySmall)
    if(story.text("error_message").isNotBlank()) Text(story.text("error_message"), color = MaterialTheme.colorScheme.error)
    if(story.optBoolean("unavailable")) Text(story.text("notice")) else {
        Action("打开故事", enabled, open)
        if(owner && !story.optBoolean("reviewed")) Action("核对转写", enabled, review)
        if(owner && story.text("status") == "failed") Action("重试处理", enabled, retry)
        if(owner && story.optBoolean("can_reextract_empty")) Action("未提取到记忆，重新整理", enabled, retry)
    }
}

@Composable private fun AskTab(state: NativeState, model: NativeWorkbenchModel) {
    var question by remember(state.actor, state.subject) { mutableStateOf("") }
    var cloud by remember(state.actor, state.subject) { mutableStateOf(false) }
    Text("从原话寻找答案", style = MaterialTheme.typography.headlineMedium)
    OutlinedTextField(question, { question = it }, label = { Text("想了解什么？") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
    Action("搜索已有记忆", !state.busy && question.isNotBlank()) { model.search(question) }
    Text("搜索会访问后端已有记忆，不触发云端回答。", style = MaterialTheme.typography.bodySmall)
    Check("同意本次将问题和有权访问的核对文字发送给云端文字模型。", cloud, { cloud = it })
    Action("提问", !state.busy && question.isNotBlank() && cloud) { model.ask(question, cloud) }
    state.search.forEach { item -> Panel {
        Text(item.text("content"))
        item.rows("evidence").forEach { evidence -> Evidence(evidence, state, model) }
    } }
    state.answer?.let { answer -> Panel {
        Text(when(answer.text("response_type")) { "ORIGINAL" -> "本人原话 · 核对文字"; "SIMULATION" -> "依据记录生成 · 不是本人原话"; else -> "目前记录还不足以回答" }, style = MaterialTheme.typography.titleMedium)
        Text(answer.text("answer"))
        answer.rows("evidence").forEach { evidence -> Evidence(evidence, state, model) }
        Text("模型：${answer.text("model_version")} · 资料版本：${answer.text("person_model_version")}", style = MaterialTheme.typography.bodySmall)
    } }
}
@Composable private fun Evidence(evidence: JSONObject, state: NativeState, model: NativeWorkbenchModel) {
    Text("依据：${evidence.text("excerpt")}")
    Text("来源 ${evidence.text("source_type")} · ${evidence.text("evidence_id")}", style = MaterialTheme.typography.bodySmall)
    if(evidence.text("episode_id").isNotBlank()) Action("播放来源完整原音", !state.busy) { model.playSource(evidence.text("episode_id")) }
}

@Composable private fun ManageTab(state: NativeState, model: NativeWorkbenchModel, confirm: (String, () -> Unit) -> Unit) {
    val enabled = !state.busy && !state.recording
    var requestText by remember(state.actor, state.subject) { mutableStateOf("") }
    Text("想了解的问题", style = MaterialTheme.typography.titleLarge)
    OutlinedTextField(requestText, { requestText = it }, label = { Text("请记录者补充讲述") }, modifier = Modifier.fillMaxWidth())
    Action("提交问题请求", enabled && requestText.isNotBlank()) { model.mutation("/requests", "POST", JSONObject().put("text", requestText.trim())); requestText = "" }
    state.requests.forEach { request -> Panel {
        Text(request.text("text")); Text("状态：${request.text("status")}", style = MaterialTheme.typography.bodySmall)
        if(state.owner) {
            Action("稍后再答", enabled) { model.mutation("/requests/${segment(request.text("request_id"))}", "PATCH", JSONObject().put("status", "snoozed")) }
            Action("暂不回答", enabled) { model.mutation("/requests/${segment(request.text("request_id"))}", "PATCH", JSONObject().put("status", "declined")) }
            Text("用已核对并整理完成的录音回答：", style = MaterialTheme.typography.bodySmall)
            state.stories.filter { it.text("status") == "ready" && it.optBoolean("reviewed") }.forEach { story ->
                Action(storyTitle(story), enabled) { model.mutation("/requests/${segment(request.text("request_id"))}", "PATCH", JSONObject().put("status", "answered").put("answer_episode_id", story.text("episode_id"))) }
            }
        }
        if(request.text("answer_episode_id").isNotBlank()) Action("听回答原音", enabled) { model.playSource(request.text("answer_episode_id")) }
    } }
    Text("故事授权", style = MaterialTheme.typography.titleLarge)
    if(state.owner) {
        var reader by remember { mutableStateOf("") }
        var chosen by remember { mutableStateOf("") }
        var audioConfirmed by remember { mutableStateOf(false) }
        var cloud by remember { mutableStateOf(false) }
        OutlinedTextField(reader, { reader = it }, label = { Text("读者 actor_id（已有身份）") }, modifier = Modifier.fillMaxWidth())
        state.stories.filter { it.text("status") == "ready" && it.optBoolean("reviewed") }.forEach { story ->
            Row { RadioButton(chosen == story.text("episode_id"), { chosen = story.text("episode_id") }); Text(storyTitle(story), Modifier.padding(top = 12.dp)) }
        }
        Check("确认分享所选故事的完整原音和文字。", audioConfirmed, { audioConfirmed = it })
        Check("额外允许读者将所选故事用于云端文字问答。", cloud, { cloud = it })
        Action("授权选定故事", enabled && audioConfirmed && chosen.isNotBlank() && reader.isNotBlank()) {
            model.mutation("/grants", "POST", JSONObject().put("episode_id", chosen).put("reader_actor_id", reader.trim()).put("include_audio_confirmed", true).put("cloud_processing_allowed", cloud))
            audioConfirmed = false; cloud = false
        }
    }
    state.grants.forEach { grant -> Panel {
        Text("${grant.text("episode_id")} → ${grant.text("reader_actor_id")}")
        Text(if(grant.optBoolean("cloud_processing_allowed")) "故事、原音与云端问答" else "仅故事与原音", style = MaterialTheme.typography.bodySmall)
        if(state.owner) Action("撤销授权", enabled) { confirm("撤销后阻止后续访问，但无法收回对方已看到或保存的内容。") {
            model.mutation("/grants/${segment(grant.text("grant_id"))}", "DELETE")
        } }
    } }
    if(state.owner) {
        val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if(granted) model.setDailyReminder(true) else model.report("系统通知权限未授予，每日提醒仍保持关闭。可在系统设置中允许后重试。")
        }
        Text("本机每日提醒", style = MaterialTheme.typography.titleLarge)
        Check("每天上午 9 点左右显示通用本机通知，不含故事或个人资料，不访问后端。", state.dailyReminder, { enabled ->
            if(!enabled) model.setDailyReminder(false)
            else if(Build.VERSION.SDK_INT >= 33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
            else model.setDailyReminder(true)
        }, enabled)
        Text("退出或切换身份／空间会取消提醒。系统电池策略可能延迟通知。", style = MaterialTheme.typography.bodySmall)
        Text("核对修订关系", style = MaterialTheme.typography.titleLarge)
        state.revisions.forEach { revision -> Panel {
            val old = state.stories.flatMap { it.rows("memories") }.firstOrNull { it.text("memory_item_id") == revision.text("target_memory_id") }
            val next = state.stories.firstOrNull { it.text("episode_id") == revision.text("episode_id") }
            Text("${kindName(revision.text("kind"))} · ${revision.text("status")}")
            Text("原记忆：${old?.text("content") ?: "原记忆已变化"}")
            Text("新记忆：${next?.rows("memories")?.joinToString("；") { it.text("content") }?.ifBlank { "尚待整理" } ?: "尚待整理"}")
            if(revision.text("time_text").isNotBlank()) Text("变化时间：${revision.text("time_text")}")
            if(revision.text("status") == "pending") Action("确认这次关系", enabled && next?.text("status") == "ready") {
                confirm("确认新旧记忆的上述关系？纠正会使旧说法退出当前回答，原音继续保留。") { model.mutation("/revisions/${segment(revision.text("revision_id"))}/confirm", "POST") }
            }
        } }
        Text("人物理解候选", style = MaterialTheme.typography.titleLarge)
        Text("系统推断需要你确认，确认后仍是推断，不能当作本人原话。")
        var cloud by remember(state.subject) { mutableStateOf(false) }
        Check("同意将已核对文字交由云端归纳候选。", cloud, { cloud = it })
        Action("归纳人物候选", enabled && cloud) { model.refreshCandidates(cloud); cloud = false }
        state.candidateJobs.forEach { job -> Text("归纳任务：${job.text("status")} ${job.text("error")}", style = MaterialTheme.typography.bodySmall) }
        state.candidates.forEach { candidate -> Panel {
            Text(candidate.text("statement")); Text("${candidate.text("label")} · ${candidate.text("domain")} · ${candidate.text("status")}", style = MaterialTheme.typography.bodySmall)
            Text("去重材料数：${candidate.optInt("independent_episodes")} · 模型：${candidate.text("model_version")}", style = MaterialTheme.typography.bodySmall)
            Text("重复说法不代表独立经历。", style = MaterialTheme.typography.bodySmall)
            Text("情境：${candidate.text("context")}")
            val evidenceIds = candidate.optJSONArray("evidence_ids")
            if(evidenceIds != null) for(i in 0 until evidenceIds.length()) {
                val evidenceId = evidenceIds.getString(i)
                val evidence = candidate.rows("evidence").firstOrNull { it.text("evidence_id") == evidenceId }
                    ?: state.stories.flatMap { it.rows("memories") }.flatMap { it.rows("evidence") }.firstOrNull { it.text("evidence_id") == evidenceId }
                if(evidence != null) Evidence(evidence, state, model) else Text("依据：$evidenceId（可从故事中核对）", style = MaterialTheme.typography.bodySmall)
            }
            Text("反证：${candidate.optJSONArray("counter_evidence_ids") ?: "[]"}", style = MaterialTheme.typography.bodySmall)
            if(candidate.text("status") == "pending") {
                var action by remember(candidate.text("candidate_id")) { mutableStateOf("ADD") }
                var target by remember(candidate.text("candidate_id")) { mutableStateOf("") }
                var reason by remember(candidate.text("candidate_id")) { mutableStateOf("") }
                var time by remember(candidate.text("candidate_id")) { mutableStateOf("") }
                listOf("ADD" to "新增理解", "SUPPORT" to "支持已有理解", "CONFLICT" to "与已有理解冲突", "CHANGE" to "随时间变化").forEach { (value, label) ->
                    Action((if(action == value) "已选：" else "") + label, enabled) { action = value }
                }
                if(action != "ADD") {
                    Text("请选择旧理解，并核对双方情境。过期理解必须重新验证来源。")
                    state.candidates.filter { it.text("candidate_id") != candidate.text("candidate_id") &&
                        it.text("stored_status") == "confirmed" && it.text("domain") == candidate.text("domain") && it.text("kind") == candidate.text("kind") }.forEach { old ->
                        Action((if(target == old.text("candidate_id")) "已选：" else "") + old.text("statement") + " · " + old.text("context"), enabled) { target = old.text("candidate_id") }
                    }
                }
                OutlinedTextField(value = reason, onValueChange = { reason = it.take(1000) }, label = { Text("关联理由") }, modifier = Modifier.fillMaxWidth())
                if(action == "CHANGE") OutlinedTextField(value = time, onValueChange = { time = it.take(200) }, label = { Text("变化时间，例如退休后") }, modifier = Modifier.fillMaxWidth())
                Action("保存为待确认更新", enabled && reason.isNotBlank() && (action == "ADD" || target.isNotBlank()) && (action != "CHANGE" || time.isNotBlank())) {
                    model.mutation("/profile-candidates/updates", "POST", JSONObject().put("candidate_id", candidate.text("candidate_id"))
                        .put("action", action).put("target_candidate_id", if(action == "ADD") JSONObject.NULL else target)
                        .put("reason", reason).put("time_text", if(action == "CHANGE") time else ""))
                }
                Action("拒绝此候选", enabled) { model.mutation("/profile-candidates/${segment(candidate.text("candidate_id"))}/reject", "POST") }
            }
            if(candidate.text("status") == "confirmed") Action("撤回这项确认", enabled) {
                confirm("撤回此候选的确认并使相关回答失效？") { model.mutation("/profile-candidates/${segment(candidate.text("candidate_id"))}/reject", "POST") }
            }
        } }
        state.profileUpdates.forEach { update -> Panel {
            val actions = mapOf("ADD" to "新增理解", "SUPPORT" to "支持已有理解", "CONFLICT" to "理解冲突", "CHANGE" to "随时间变化")
            Text("${actions[update.text("action")]} · ${update.text("status")}")
            state.candidates.firstOrNull { it.text("candidate_id") == update.text("candidate_id") }?.let { Text("新观察：${it.text("statement")}") }
            state.candidates.firstOrNull { it.text("candidate_id") == update.text("target_candidate_id") }?.let { Text("旧理解：${it.text("statement")}；情境：${it.text("context")}") }
            Text(update.text("reason"))
            if(update.text("time_text").isNotBlank()) Text("变化时间：${update.text("time_text")}")
            if(update.text("question").isNotBlank()) Text(update.text("question"))
            if(update.text("status") == "pending") {
                Action("确认上述更新", enabled) { confirm("已核对双方原文和情境？支持或变化保留历史；冲突暂停使用相关理解。") {
                    model.mutation("/profile-candidates/updates/${segment(update.text("update_id"))}/confirm", "POST")
                } }
                Action("拒绝这次更新", enabled) { model.mutation("/profile-candidates/updates/${segment(update.text("update_id"))}/reject", "POST") }
            }
        } }
    }
    Text("每日提醒：${if(state.dailyReminder) "已主动开启，仅本机通用通知" else "关闭"}；没有后台云端调用。", style = MaterialTheme.typography.bodySmall)
}

@Composable private fun Panel(content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content) }
}
@Composable private fun Action(label: String, enabled: Boolean = true, action: () -> Unit) {
    OutlinedButton(onClick = action, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text(label) }
}
@Composable private fun Check(label: String, checked: Boolean, onChange: (Boolean) -> Unit, enabled: Boolean = true) {
    Row(Modifier.fillMaxWidth()) { Checkbox(checked, onCheckedChange = onChange, enabled = enabled); Text(label, Modifier.weight(1f).padding(top = 12.dp)) }
}
@Composable private fun NativeDialog(title: String, close: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().fillMaxHeight(.92f).padding(12.dp), shape = MaterialTheme.shapes.large) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(title, style = MaterialTheme.typography.titleLarge); TextButton(onClick = close) { Text("关闭") }; content()
            }
        }
    }
}
private fun storyTitle(story: JSONObject): String = story.rows("memories").firstOrNull()?.text("content")?.take(34)
    ?: story.text("transcript").take(34).ifBlank { "一段新的记述" }
private fun kindName(kind: String) = when(kind) { "correction" -> "纠正"; "change" -> "情况变化"; else -> "补充" }
private fun clock(ms: Long): String = "%02d:%02d".format(ms / 60_000, ms / 1000 % 60)

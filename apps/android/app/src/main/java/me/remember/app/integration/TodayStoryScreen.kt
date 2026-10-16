package me.remember.app.integration

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.LocalSimpleMode

@Composable internal fun TodayStoryScreen(state: NativeState, model: NativeWorkbenchModel,
    record: () -> Unit, library: () -> Unit, review: (String) -> Unit) {
    var source by rememberSaveable(state.actor, state.subject) { mutableStateOf(model.preferredCaptureSource()) }
    val recorder by model.recorder().ui.collectAsState()
    val deviceRecording = recorder.recordPhase in setOf(me.remember.app.hardware.DeviceRecordPhase.RECORDING, me.remember.app.hardware.DeviceRecordPhase.PAUSED)
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        listOf("recorder" to "录音豆", "phone" to "手机").forEach { (value, label) ->
            FilterChip(selected = source == value, onClick = { source = value; model.selectCaptureSource(value) },
                enabled = !state.recording && !deviceRecording, label = { Text(label) })
        }
    }
    if (source == "recorder") {
        Work3200Screen(model, compact = true)
        val hardware = state.local.filter { it.source == "WORK_3200" }.take(3)
        if (hardware.isNotEmpty()) CaptureTab(state.copy(local = hardware), model, null, {})
    } else {
    Surface(shape=RoundedCornerShape(32.dp),color=MaterialTheme.colorScheme.secondaryContainer.copy(alpha=.92f)) {
        Column(Modifier.fillMaxWidth().background(Brush.verticalGradient(listOf(
            MaterialTheme.colorScheme.secondaryContainer,MaterialTheme.colorScheme.primaryContainer.copy(alpha=.6f))))
            .padding(24.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
            Icon(Icons.Outlined.Spa,null,Modifier.size(36.dp),tint=MaterialTheme.colorScheme.primary)
            Text("今天，想留下什么？",style=MaterialTheme.typography.headlineSmall)
            Text("一件往事，或一句想说的话。",style=MaterialTheme.typography.bodyLarge)
            RememberActionButton("用手机讲一段", !state.busy, filled=true, icon=Icons.Outlined.Mic, onClick=record)
        }
    }
    }
    state.stories.filter { story -> state.local.any { it.source == "WORK_3200" && it.episode == story.text("episode_id") } }.take(3).forEach { story ->
        Text(if (story.optBoolean("waiting_for_review")) "录音豆录音 · 等待核对文字" else "录音豆录音 · ${processingLabel(story.text("status"))}")
        if (story.text("status") == "ready") story.rows("memories").take(3).forEach { memory ->
            Text(memory.text("content"), style = MaterialTheme.typography.bodyLarge)
        }
        if (story.optBoolean("waiting_for_review")) TextButton(onClick = { review(story.text("episode_id")) }, enabled = !state.busy) { Text("核对本段文字") }
        else if (story.text("status") == "ready") {
            var expanded by rememberSaveable(story.text("episode_id")) { mutableStateOf(false) }
            TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "收起本段文字与全部记忆" else "查看本段文字与全部记忆") }
            if (expanded) {
                Text("已核对的文字", style = MaterialTheme.typography.titleMedium)
                Text(story.text("transcript"), style = MaterialTheme.typography.bodyLarge)
                story.rows("memories").drop(3).forEach { Text(it.text("content"), style = MaterialTheme.typography.bodyLarge) }
            }
        } else if (story.text("status") == "failed") TextButton(onClick = { model.retry(story.text("episode_id")) }, enabled = !state.busy) { Text("重试本段处理") }
    }
    val pending=state.stories.filter{it.optBoolean("waiting_for_review") || it.text("status")!="ready"}
    val unuploaded=state.local.count{it.episode.isBlank()}
    val waiting=pending.firstOrNull{it.optBoolean("waiting_for_review")}
    if(pending.isNotEmpty() || unuploaded>0) OutlinedButton(onClick={if(waiting!=null) review(waiting.text("episode_id")) else library()},modifier=Modifier.fillMaxWidth()) {
        Icon(Icons.Outlined.AutoStories,null);Spacer(Modifier.width(8.dp));Text("继续整理 · ${pending.size+unuploaded} 段")
    }
    TextButton(onClick=library) { Icon(Icons.Outlined.LibraryMusic,null);Spacer(Modifier.width(8.dp));Text("我的录音") }
    if(state.narrative.optJSONObject("next_question")!=null) {
        var expanded by rememberSaveable(state.actor,state.subject) { mutableStateOf(false) }
        TextButton(onClick={expanded=!expanded}) { Text(if(expanded) "收起话题" else "不知道从哪讲？") }
        if(expanded) NarrativeQuestion(state,model)
    }
}

/** A separate recorder: the controls stay reachable independently of content size. */
@Composable internal fun StoryRecordingFlow(state: NativeState, model: NativeWorkbenchModel,
    revision: RevisionTarget?, setRevision: (RevisionTarget?) -> Unit, close: () -> Unit, saved: () -> Unit) {
    val simple = LocalSimpleMode.current
    var confirmClose by remember { mutableStateOf(false) }
    val initialSaved by rememberSaveable(state.actor,state.subject) { mutableStateOf(state.savedCaptureId) }
    LaunchedEffect(state.savedCaptureId) {
        if(state.savedCaptureId.isNotBlank() && state.savedCaptureId!=initialSaved) { setRevision(null);saved() }
    }
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if(granted) model.start(revision) else model.report("请允许麦克风权限后重试。")
    }
    fun leave() { if(state.recording) confirmClose=true else {setRevision(null);close()} }
    fun finish() { model.finish() }
    BackHandler { leave() }
    // A full activity page avoids a floating dialog's display-height/content-
    // origin mismatch on Android 15. Recording controls use the activity insets.
    Box(Modifier.fillMaxSize()) {
        Surface(Modifier.fillMaxSize(),color=MaterialTheme.colorScheme.background) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().padding(20.dp)) {
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                    if(simple) TextButton(onClick={leave()},modifier=Modifier.heightIn(min=60.dp)) {Icon(Icons.Outlined.ArrowBack,null);Text("返回")}
                    else IconButton(onClick={leave()}) { Icon(Icons.Outlined.Close,"关闭录音") }
                    Text("留下一段声音",style=MaterialTheme.typography.titleLarge)
                }
                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()),
                    verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally) {
                    RememberRecordingStatus(state.recording,state.paused,state.elapsed)
                    state.error?.let{Text(it,color=MaterialTheme.colorScheme.error)}
                    revision?.let { target ->
                        Spacer(Modifier.height(24.dp))
                        Text("围绕这条记忆继续讲",style=MaterialTheme.typography.titleMedium)
                        val original=state.stories.flatMap{it.rows("memories")}.firstOrNull{it.text("memory_item_id")==target.memory}
                        Text(original?.text("content") ?: "已选定的记忆",style=MaterialTheme.typography.bodyLarge)
                        if(!state.recording) TextButton(onClick={setRevision(null)}) { Text("取消关联，记录新故事") }
                        listOf("supplement" to "补充", "correction" to "纠正", "change" to "后来变化").forEach{(kind,label)->
                            Row(verticalAlignment=Alignment.CenterVertically){RadioButton(target.kind==kind,{setRevision(target.copy(kind=kind))},enabled=!state.recording);Text(label)}
                        }
                        if(target.kind=="change") OutlinedTextField(target.time,{setRevision(target.copy(time=it))},label={Text("变化时间，可保留模糊表达")},enabled=!state.recording)
                    }
                }
                if(state.recording) {
                    RememberActionButton(if(state.paused) "继续录音" else "暂停", !state.busy,
                        icon=if(state.paused) Icons.Outlined.Mic else Icons.Outlined.Pause, onClick=model::pauseOrResumeRecording)
                    Spacer(Modifier.height(12.dp))
                    RememberActionButton("完成并保存", !state.busy, filled=true, icon=Icons.Outlined.Check,
                        pendingLabel="正在保存原音…", successLabel="原音已保存", onClick={finish()})
                } else RememberActionButton("开始录音", !state.busy && (revision?.kind!="change" || revision.time.isNotBlank()),
                    filled=true, icon=Icons.Outlined.Mic) { permission.launch(Manifest.permission.RECORD_AUDIO) }
            }
        }
        if(confirmClose) AlertDialog(onDismissRequest={confirmClose=false},title={Text("保存这段声音？")},
            confirmButton={TextButton(onClick={confirmClose=false;finish()}){Text("完成并保存")}},
            dismissButton={TextButton(onClick={confirmClose=false}){Text("继续录音")}})
    }
}

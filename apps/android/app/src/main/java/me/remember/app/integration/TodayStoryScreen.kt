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
import androidx.compose.ui.platform.testTag

@Composable internal fun TodayStoryScreen(state: NativeState, model: NativeWorkbenchModel,
    record: () -> Unit, library: () -> Unit, openStory: (String) -> Unit, onStageChanged: () -> Unit = {}) {
    var source by rememberSaveable(state.actor, state.subject) { mutableStateOf(model.preferredCaptureSource()) }
    var manage by remember { mutableStateOf(false) }
    val recorder by model.recorder().ui.collectAsState()
    val deviceRecording = recorder.recordPhase in setOf(me.remember.app.hardware.DeviceRecordPhase.RECORDING, me.remember.app.hardware.DeviceRecordPhase.PAUSED)
    val receiving = deviceRecording || recorder.busy in setOf("download","verify","decode")
    val stage = when {
        deviceRecording -> "recording:${recorder.recordingFileId}"
        recorder.busy in setOf("download","verify","decode") -> "sync:${recorder.recordingFileId}"
        state.local.any {it.needsAutomaticUpload()} -> "upload:${state.local.first {it.needsAutomaticUpload()}.key}"
        state.drafts.isNotEmpty() -> "draft:${state.draftFocus.ifBlank {state.drafts.keys.first()}}"
        state.stories.any {it.text("status") !in setOf("ready","failed")} -> "processing:${state.draftFocus}"
        else -> "ready:${state.draftFocus}"
    }
    var previousStage by remember {mutableStateOf(stage)}
    LaunchedEffect(stage) {
        if(stage!=previousStage) {previousStage=stage;manage=false;onStageChanged()}
    }
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        listOf("recorder" to "录音豆", "phone" to "手机").forEach { (value, label) ->
            FilterChip(selected = source == value, onClick = { source = value; model.selectCaptureSource(value) },
                enabled = !state.recording && !deviceRecording, label = { Text(label) })
        }
    }
    if (source == "recorder") {
        Work3200Screen(model, compact = true, onManage = { manage=true }, condensed=state.drafts.isNotEmpty() ||
            state.local.any { it.needsAutomaticUpload() } || state.stories.isNotEmpty())
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
    val pendingCapture=state.local.firstOrNull { it.autoProcess && !it.linked && it.recording.durationMillis>0 }
    if(pendingCapture!=null && !receiving) Surface(shape=MaterialTheme.shapes.large,color=MaterialTheme.colorScheme.surface.copy(alpha=.94f)) {
        Column(Modifier.fillMaxWidth().padding(20.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            val error=state.captureErrors[pendingCapture.key]
            Text(error ?: if(state.uploadKey==pendingCapture.key) "收到录音，正在上传转写" else "录音已保存，等待转写",style=MaterialTheme.typography.titleMedium)
            if(error!=null) TextButton(onClick={model.upload(pendingCapture,true)}) { Text("重试转写") }
            else if(state.uploadKey==pendingCapture.key) key(pendingCapture.key) { RecorderProgress(state.uploadPercent) }
        }
    }
    val drafts=state.stories.mapNotNull { state.drafts[it.text("episode_id")] }
    val draft=drafts.firstOrNull { it.episode==state.draftFocus } ?: drafts.firstOrNull()
    if(draft!=null && !receiving) {
        if(drafts.size>1) Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            drafts.take(4).forEachIndexed { i,d -> FilterChip(selected=d.episode==draft.episode,onClick={model.focusDraft(d.episode)},label={Text("文字 ${i+1}")}) }
        }
        TranscriptDraftCard(draft,state,model)
    }
    val processing=state.stories.firstOrNull { !it.optBoolean("waiting_for_review") && it.text("status")!="ready" &&
        state.local.any { capture -> capture.episode==it.text("episode_id") } }
    if(processing!=null && !receiving) Panel {
        val failed=processing.text("status")=="failed"
        Text(if(failed) "处理暂未完成" else if(processing.optBoolean("reviewed")) "已保存，正在整理记忆" else "已保存，正在转文字",style=MaterialTheme.typography.titleMedium)
        if(failed) TextButton(onClick={model.retry(processing.text("episode_id"))},enabled=!state.busy) { Text("重试处理") }
        else key(processing.text("episode_id"), processing.optBoolean("reviewed")) {
            RecorderProgress(captureStageProgress(processing.text("status"), processing.optBoolean("reviewed"))?.percent, flow=true)
        }
    }
    val recent=state.stories.firstOrNull { it.text("status")=="ready" && it.text("episode_id")==state.draftFocus }
        ?: state.stories.firstOrNull { it.text("status")=="ready" }
    if(recent!=null && draft==null && processing==null && pendingCapture==null && !receiving)
        CompletedMemoryCard(recent) { openStory(recent.text("episode_id")) }
    if(!receiving) TextButton(onClick=library,modifier=Modifier.fillMaxWidth()) { Icon(Icons.Outlined.AutoStories,null);Spacer(Modifier.width(8.dp));Text("全部录音与记忆") }
    if(manage) RecorderDeviceDialog({manage=false}) { Work3200Screen(model) }
    if(state.narrative.optJSONObject("next_question")!=null && !receiving && draft==null && processing==null && pendingCapture==null && recent==null) {
        var expanded by rememberSaveable(state.actor,state.subject) { mutableStateOf(false) }
        TextButton(onClick={expanded=!expanded}) { Text(if(expanded) "收起话题" else "不知道从哪讲？") }
        if(expanded) NarrativeQuestion(state,model)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable internal fun TranscriptDraftCard(draft: CaptureDraft, state: NativeState, model: NativeWorkbenchModel) {
    var supplement by rememberSaveable(draft.episode) { mutableStateOf(draft.supplement.isNotBlank()) }
    var highlights by remember(draft.episode) { mutableStateOf(false) }
    val saving=state.savingEpisode==draft.episode
    Surface(shape=MaterialTheme.shapes.extraLarge,color=MaterialTheme.colorScheme.surface.copy(alpha=.97f)) {
        Column(Modifier.fillMaxWidth().padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Text("录音文字",style=MaterialTheme.typography.titleLarge)
            OutlinedTextField(draft.text,{model.editDraft(draft.episode,it)},modifier=Modifier.fillMaxWidth().testTag("capture-draft-text"),
                minLines=3,maxLines=6,enabled=!saving,label={Text("可修改")})
            if(supplement) OutlinedTextField(draft.supplement,{model.editDraft(draft.episode,draft.text,it)},
                modifier=Modifier.fillMaxWidth().testTag("capture-draft-supplement"),minLines=2,maxLines=4,enabled=!saving,label={Text("补充信息（选填）")})
            state.draftSaveError?.let { Text(it,color=MaterialTheme.colorScheme.error) }
            Button(onClick={model.saveDraft(draft.episode)},enabled=!state.busy && !saving && draft.text.isNotBlank(),
                modifier=Modifier.fillMaxWidth().heightIn(min=52.dp).testTag("capture-save-memory")) {
                Text(if(saving) "正在保存…" else "保存到记忆")
            }
            FlowRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                if(!supplement) TextButton(onClick={supplement=true}) { Text("补充信息") }
                val local=state.local.firstOrNull { it.episode==draft.episode }
                TextButton(onClick={if(local!=null) model.playLocal(local) else model.playSource(draft.episode)},enabled=!state.recording) { Text("听原音") }
                if(hasRecordingHighlights(draft.highlights)) TextButton(onClick={highlights=!highlights}) { Text(recordingHighlightLabel(draft.highlights)) }
            }
            if(highlights) NativeDialog("标记详情",{highlights=false}) { RecordingHighlights(draft.highlights,draft.text!=draft.initial) }
        }
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

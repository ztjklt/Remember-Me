package me.remember.app.integration

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.text.style.TextAlign

@Composable internal fun TodayStoryScreenExact(state: NativeState, record: () -> Unit) {
    Box(Modifier.fillMaxWidth().fillMaxHeight(.86f).padding(horizontal = 8.dp)) {
        Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.weight(1f))
            Icon(Icons.Outlined.WbSunny, contentDescription = null, modifier = Modifier.size(38.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(24.dp))
            Text("今天想留下些什么？", style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(28.dp))
            Box(
                modifier = Modifier
                    .size(width = 270.dp, height = 138.dp)
                    .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(6.dp))
                    .clickable(enabled = !state.busy, onClick = record),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Outlined.Mic, contentDescription = "录音", modifier = Modifier.size(52.dp), tint = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.weight(1f))
        }
    }
}

@Composable internal fun TodayStoryScreenRedesigned(state: NativeState, model: NativeWorkbenchModel,
    record: () -> Unit, library: () -> Unit, review: (String) -> Unit) {
    Box(Modifier.fillMaxWidth().fillMaxHeight(.82f).padding(horizontal = 8.dp)) {
        Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Icon(Icons.Outlined.WbSunny, contentDescription = null, modifier = Modifier.size(34.dp), tint = MaterialTheme.colorScheme.primary)
            Text("今天想留下些什么？", style = MaterialTheme.typography.headlineSmall)
            Text("一件往事，或一句想说的话。", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(10.dp))
            FilledIconButton(onClick = record, enabled = !state.busy, modifier = Modifier.size(112.dp), shape = RoundedCornerShape(36.dp), colors = IconButtonDefaults.filledIconButtonColors(containerColor = MaterialTheme.colorScheme.primaryContainer, contentColor = MaterialTheme.colorScheme.primary)) {
                Icon(Icons.Outlined.Mic, contentDescription = "开始录音", modifier = Modifier.size(48.dp))
            }
            Text("点击开始录音", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable internal fun TodayStoryScreen(state: NativeState, model: NativeWorkbenchModel,
    record: () -> Unit, library: () -> Unit, review: (String) -> Unit) {
    Surface(shape=RoundedCornerShape(32.dp),color=MaterialTheme.colorScheme.secondaryContainer.copy(alpha=.92f)) {
        Column(Modifier.fillMaxWidth().background(Brush.verticalGradient(listOf(
            MaterialTheme.colorScheme.secondaryContainer,MaterialTheme.colorScheme.primaryContainer.copy(alpha=.6f))))
            .padding(24.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
            Icon(Icons.Outlined.Spa,null,Modifier.size(36.dp),tint=MaterialTheme.colorScheme.primary)
            Text("今天，想留下什么？",style=MaterialTheme.typography.headlineSmall)
            Text("一件往事，或一句想说的话。",style=MaterialTheme.typography.bodyLarge)
            Button(onClick=record,enabled=!state.busy,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp),
                shape=RoundedCornerShape(20.dp)) {
                Icon(Icons.Outlined.Mic,null);Spacer(Modifier.width(10.dp));Text("讲一段",style=MaterialTheme.typography.titleMedium)
            }
        }
    }
    val pending=state.stories.filter{it.optBoolean("waiting_for_review") || it.text("status")!="ready"}
    val unuploaded=state.local.count{it.episode.isBlank()}
    if(state.narrative.optJSONObject("next_question")!=null) {
        var expanded by rememberSaveable(state.actor,state.subject) { mutableStateOf(false) }
        TextButton(onClick={expanded=!expanded}) { Text(if(expanded) "收起话题" else "不知道从哪讲？") }
        if(expanded) NarrativeQuestion(state,model)
    }
}

@Composable internal fun LocalRecordingOrganizerLegacy(
    capture: LocalCapture,
    model: NativeWorkbenchModel,
    close: () -> Unit,
    openArchive: () -> Unit
) {
    var consent by remember(capture.key) { mutableStateOf(false) }
    val currentState = model.ui.collectAsStateWithLifecycle().value
    val caps = currentState.asrCapabilities
    val clientAsr = capture.usesClientTranscript(caps?.text("stt") == "client")
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("整理这段录音", style = MaterialTheme.typography.headlineSmall)
                        Text("确认后才会上传并交给云端模型整理", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    IconButton(onClick = close) { Icon(Icons.Outlined.Close, contentDescription = "关闭") }
                }
                Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(20.dp), color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .55f)) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("录音已保存", style = MaterialTheme.typography.titleMedium)
                        Text("${clock(capture.recording.durationMillis)} · ${capture.recording.createdAt}", style = MaterialTheme.typography.bodySmall)
                        OutlinedButton(onClick = { model.playLocal(capture) }, modifier = Modifier.fillMaxWidth()) {
                            Icon(Icons.Outlined.PlayArrow, contentDescription = null); Spacer(Modifier.width(8.dp)); Text("播放原音")
                        }
                    }
                }
                Text("文字识别", style = MaterialTheme.typography.titleMedium)
                if (capture.transcript != null) {
                    OutlinedTextField(capture.transcript.text, {}, modifier = Modifier.fillMaxWidth(), minLines = 5, readOnly = true, label = { Text("机器转写") })
                } else {
                    Text("上传后会生成机器转写，随后可在档案中核对和修改。", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Spacer(Modifier.weight(1f))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = openArchive, modifier = Modifier.weight(1f)) { Text("稍后整理") }
                    Button(onClick = { model.upload(capture, true); close() }, enabled = !capture.uploadAttempted && !currentState.busy && (clientAsr || caps?.optBoolean("stt_configured") == true) && consent, modifier = Modifier.weight(1f)) { Text("同意并整理") }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(consent, { consent = it })
                    Text("我同意上传完整原音，并用于本次文字识别与后续整理", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable internal fun LocalRecordingOrganizerExact(
    capture: LocalCapture,
    model: NativeWorkbenchModel,
    close: () -> Unit
) {
    var consent by remember(capture.key) { mutableStateOf(false) }
    var supplement by rememberSaveable(capture.key) { mutableStateOf("") }
    val currentState = model.ui.collectAsStateWithLifecycle().value
    val caps = currentState.asrCapabilities
    val clientAsr = capture.usesClientTranscript(caps?.text("stt") == "client")
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().safeDrawingPadding(), contentAlignment = Alignment.Center) {
            Surface(Modifier.fillMaxWidth().fillMaxHeight(.74f).padding(horizontal = 12.dp), shape = RoundedCornerShape(8.dp), color = MaterialTheme.colorScheme.background) {
                Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 10.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("整理这段录音", modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                        IconButton(onClick = close) { Icon(Icons.Outlined.Close, contentDescription = "关闭") }
                    }
                    Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Spacer(Modifier.height(14.dp))
                    OutlinedButton(onClick = { model.playLocal(capture) }, modifier = Modifier.align(Alignment.Start).width(112.dp), shape = RoundedCornerShape(6.dp)) {
                        Icon(Icons.Outlined.PlayArrow, contentDescription = null); Spacer(Modifier.width(6.dp)); Text("播放")
                    }
                    Text("文字识别", style = MaterialTheme.typography.titleMedium)
                    OutlinedTextField(value = capture.transcript?.text.orEmpty(), onValueChange = {}, readOnly = true, modifier = Modifier.fillMaxWidth(), minLines = 6, placeholder = { Text("等待文字识别") })
                    Text("补充说明", style = MaterialTheme.typography.titleMedium, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
                    OutlinedTextField(value = supplement, onValueChange = { if (it.length <= 3000) supplement = it }, modifier = Modifier.fillMaxWidth(), minLines = 9, placeholder = { Text("可选：补充人物、地点或语境") })
                    Text("可选。确认后交由云端模型整理，并用于之后的回答。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(consent, { consent = it })
                        Text("我同意上传完整原音并进行文字识别与整理", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                    }
                    Button(onClick = { model.upload(capture, true, supplement); close() }, enabled = !capture.uploadAttempted && !currentState.busy && (clientAsr || caps?.optBoolean("stt_configured") == true) && consent, modifier = Modifier.width(180.dp).heightIn(min = 52.dp), shape = RoundedCornerShape(6.dp)) { Text("整理") }
                    Spacer(Modifier.height(18.dp))
                    }
                }
            }
        }
    }
}

/** A separate recorder: the controls stay reachable independently of content size. */
@Composable internal fun StoryRecordingFlow(state: NativeState, model: NativeWorkbenchModel,
    revision: RevisionTarget?, setRevision: (RevisionTarget?) -> Unit, close: () -> Unit, saved: () -> Unit) {
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
    Dialog(onDismissRequest={leave()},properties=DialogProperties(usePlatformDefaultWidth=false)) {
        Surface(Modifier.fillMaxSize(),color=MaterialTheme.colorScheme.background) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().padding(20.dp)) {
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                    IconButton(onClick={leave()}) { Icon(Icons.Outlined.Close,"关闭录音") }
                    Text("留下一段声音",style=MaterialTheme.typography.titleLarge)
                }
                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()),
                    verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally) {
                    Icon(Icons.Outlined.Mic, null, Modifier.size(72.dp), tint=MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.height(24.dp))
                    Text(clock(state.elapsed),style=MaterialTheme.typography.displayMedium)
                    Text(if(state.recording) if(state.paused) "已暂停" else "正在录音" else "慢慢说，我在听",style=MaterialTheme.typography.titleMedium)
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
                    OutlinedButton(onClick=model::pauseOrResumeRecording,enabled=!state.busy,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)) { Text(if(state.paused) "继续录音" else "暂停") }
                    Button(onClick={finish()},enabled=!state.busy,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)) { Text("完成并保存") }
                } else Button(onClick={permission.launch(Manifest.permission.RECORD_AUDIO)},
                    enabled=!state.busy && (revision?.kind!="change" || revision.time.isNotBlank()),modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)) { Text("开始录音") }
            }
        }
        if(confirmClose) AlertDialog(onDismissRequest={confirmClose=false},title={Text("保存这段声音？")},
            confirmButton={TextButton(onClick={confirmClose=false;finish()}){Text("完成并保存")}},
            dismissButton={TextButton(onClick={confirmClose=false}){Text("继续录音")}})
    }
}

package me.remember.app.feature

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import me.remember.app.core.designsystem.atmosphere
import me.remember.app.core.designsystem.actionGradient
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.LibraryBooks
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import me.remember.app.data.repository.*
import me.remember.app.core.designsystem.RememberMeBrand
import me.remember.app.R
import androidx.compose.ui.res.painterResource
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

fun durationLabel(milliseconds: Long): String = "%02d:%02d".format(milliseconds / 60000, milliseconds / 1000 % 60)
fun dateLabel(value: String): String = runCatching {
    Instant.parse(value).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("M月d日 HH:mm"))
}.getOrDefault(value.take(16))
fun stageLabel(stage: ProcessingStage) = when (stage) {
    ProcessingStage.Unprocessed -> "原音已保存"
    ProcessingStage.Transcribing -> "正在转成文字"
    ProcessingStage.NeedsReview -> "待核对文字"
    ProcessingStage.Organizing -> "正在整理记忆"
    ProcessingStage.Complete -> "已整理"
    ProcessingStage.Failed -> "需要处理"
}
@Composable private fun pagePadding() = if (LocalConfiguration.current.screenWidthDp < 380) 16.dp else 20.dp
@Composable private fun Page(spacing: androidx.compose.ui.unit.Dp = 24.dp, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal=pagePadding(), vertical=24.dp),
        verticalArrangement=Arrangement.spacedBy(spacing), content=content)
}
@Composable private fun Muted(text: String) { Text(text, style=MaterialTheme.typography.bodySmall, color=MaterialTheme.colorScheme.onSurfaceVariant) }
@Composable private fun Heading(text: String) { Text(text, style=MaterialTheme.typography.headlineLarge, modifier=Modifier.semantics { heading() }) }
@Composable private fun Section(text: String) { Text(text, style=MaterialTheme.typography.titleLarge, modifier=Modifier.semantics { heading() }) }
@Composable private fun Primary(label: String, icon: ImageVector, enabled: Boolean=true, tag: String="", action: () -> Unit) {
    val interactions = remember { MutableInteractionSource() }
    val pressed by interactions.collectIsPressedAsState()
    val shape = MaterialTheme.shapes.medium
    Button(onClick=action, enabled=enabled, shape=shape, interactionSource=interactions,
        colors=ButtonDefaults.buttonColors(containerColor=Color.Transparent),
        modifier=Modifier.fillMaxWidth().heightIn(min=56.dp).testTag(tag)
            .shadow(if(!enabled) 0.dp else if(pressed) 1.dp else 3.dp,shape)
            .clip(shape).then(if(enabled) Modifier.background(actionGradient(pressed)) else Modifier),
        contentPadding=PaddingValues(16.dp)) {
        Icon(icon, contentDescription=null); Spacer(Modifier.width(12.dp)); Text(label)
    }
}
@Composable private fun Notice(title: String, body: String, error: Boolean=false) {
    Row(Modifier.fillMaxWidth().padding(vertical=12.dp),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
        if(error) Icon(Icons.Outlined.ErrorOutline,null,Modifier.size(20.dp),tint=MaterialTheme.colorScheme.error)
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(5.dp)) {
            Text(title,style=MaterialTheme.typography.titleMedium,color=if(error)MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
            Muted(body)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun MobileApp(model: MobileViewModel) {
    val records by model.recordings.collectAsState()
    val capture by model.capture.collectAsState()
    val message by model.message.collectAsState()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var recordingOpen by rememberSaveable { mutableStateOf(false) }
    var detailPath by rememberSaveable { mutableStateOf<String?>(null) }
    var memoryID by rememberSaveable { mutableStateOf<String?>(null) }
    val holder = rememberSaveableStateHolder()
    fun back() { if(memoryID != null) memoryID=null else detailPath=null }
    BackHandler(detailPath != null && !recordingOpen) { back() }
    if (recordingOpen) {
        CapturePage(model, close={recordingOpen=false}, openDetail={detailPath=it.audioPath; recordingOpen=false})
    } else {
        Scaffold(modifier=Modifier.atmosphere(),containerColor=Color.Transparent,
            topBar={ if(detailPath != null) TopAppBar(title={Text(if(memoryID == null) "录音详情" else "记忆详情")},
                navigationIcon={IconButton(onClick={back()}){Icon(Icons.AutoMirrored.Outlined.ArrowBack,"返回")}}) },
            bottomBar={ if(detailPath == null) Surface(modifier=Modifier.navigationBarsPadding(),color=MaterialTheme.colorScheme.background) {
              NavigationBar(containerColor=MaterialTheme.colorScheme.background,windowInsets=WindowInsets(0,0,0,0),tonalElevation=0.dp) {
                listOf("今天" to Icons.Outlined.WbSunny, "档案" to Icons.AutoMirrored.Outlined.LibraryBooks, "我的" to Icons.Outlined.Person).forEachIndexed { index,item ->
                    NavigationBarItem(selected=tab==index,onClick={tab=index},icon={Icon(item.second,null)},label={Text(item.first)},modifier=Modifier.testTag("tab.$index"),colors=NavigationBarItemDefaults.colors(indicatorColor=MaterialTheme.colorScheme.background,selectedIconColor=MaterialTheme.colorScheme.primary,selectedTextColor=MaterialTheme.colorScheme.primary))
                }
            } } }
        ) { padding ->
            Box(Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding)) {
                val record=records.firstOrNull { it.audioPath==detailPath }
                if(detailPath != null) {
                    if(record==null) Page { Notice("找不到这段录音","请返回档案，已有录音不会因此被删除。") }
                    else if(memoryID != null) MemoryPage(model,record,memoryID!!,onDeleted={memoryID=null})
                    else DetailPage(model,record,openMemory={memoryID=it})
                } else holder.SaveableStateProvider(tab) {
                    when(tab) {
                        0 -> TodayPage(records, start={model.newRecording();recordingOpen=true}, open={detailPath=it.audioPath}, archive={tab=1})
                        1 -> ArchivePage(records,open={detailPath=it.audioPath},openMemory={r,id->detailPath=r.audioPath;memoryID=id})
                        else -> ProfilePage(model)
                    }
                }
            }
        }
    }
    if(message != null) AlertDialog(onDismissRequest=model::dismissMessage,title={Text("操作未完成")},text={Text(message!!)},
        confirmButton={TextButton(onClick=model::dismissMessage){Text("知道了")}})
}

@Composable private fun TodayPage(records: List<AudioRecording>,start:()->Unit,open:(AudioRecording)->Unit,archive:()->Unit) {
    Page(spacing=16.dp) {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically) {
            RememberMeBrand(size=32.dp)
            Text("勿忘我",style=MaterialTheme.typography.titleMedium,modifier=Modifier.weight(1f))
            Muted(LocalDate.now().format(DateTimeFormatter.ofPattern("M月d日")))
        }
        Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Heading("今天，想记住什么？")
            Muted("一件小事，也可以慢慢说。")
        }
        Column(verticalArrangement=Arrangement.spacedBy(6.dp),horizontalAlignment=Alignment.CenterHorizontally) {
            Primary("开始录音",Icons.Outlined.Mic,tag="home.record",action=start)
            Muted("原音先留在手机")
        }
        records.firstOrNull { it.processingStage != ProcessingStage.Complete }?.let { item ->
            Column {
                HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
                Row(Modifier.fillMaxWidth().clickable(role=Role.Button){open(item)}.padding(vertical=12.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.Outlined.PendingActions,null,Modifier.size(20.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant)
                    Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text(if(item.processingStage==ProcessingStage.NeedsReview) "继续核对" else "继续处理",style=MaterialTheme.typography.titleMedium)
                        Muted(item.title+" · "+stageLabel(item.processingStage))
                    }
                    Icon(Icons.Outlined.ChevronRight,null,Modifier.size(18.dp))
                }
                HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
            }
        }
        Column {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
                Text("最近记录",style=MaterialTheme.typography.titleLarge,modifier=Modifier.weight(1f).semantics{heading()})
                TextButton(onClick=archive){Text("查看全部",style=MaterialTheme.typography.bodySmall)}
            }
            if(records.isEmpty()) {
                RememberMeBrand(size=80.dp,materialPainter=painterResource(R.drawable.rm_brand_material))
                Notice("从第一段声音开始","不必准备完整的故事。录完之后，可以随时回来听。")
            }
            records.take(3).forEach { RecordingRow(it,onClick={open(it)}) }
        }
    }
}
@Composable private fun RecordingRow(record: AudioRecording,onClick:()->Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick=onClick,role=Role.Button)) {
        Row(Modifier.padding(vertical=14.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) {
            Icon(Icons.Outlined.GraphicEq,null,Modifier.size(22.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant)
            Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(5.dp)) {
                Text(record.title,style=MaterialTheme.typography.titleMedium)
                Muted("${dateLabel(record.createdAt)} · ${durationLabel(record.durationMillis)}")
                Text(stageLabel(record.processingStage),style=MaterialTheme.typography.bodySmall,color=if(record.processingStage==ProcessingStage.NeedsReview || record.processingStage==ProcessingStage.Failed)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.Outlined.ChevronRight,null,Modifier.size(16.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
    }
}
@Composable private fun ArchivePage(records: List<AudioRecording>,open:(AudioRecording)->Unit,openMemory:(AudioRecording,String)->Unit) {
    var mode by rememberSaveable { mutableIntStateOf(0) }
    var query by rememberSaveable { mutableStateOf("") }
    val matching=records.filter { query.isBlank() || (it.title+it.transcript+it.reviewedTranscript.orEmpty()+it.memories.filter { m->m.status=="active" }.joinToString { m->m.content }).contains(query.trim(),ignoreCase=true) }
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(horizontal=pagePadding(),vertical=24.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        item { Heading("档案") }
        item { Muted("说过的话，完整留着。") }
        item { OutlinedTextField(query,{query=it},Modifier.fillMaxWidth(),label={Text("搜索标题、文字或记忆")},leadingIcon={Icon(Icons.Outlined.Search,null)},singleLine=true,shape=MaterialTheme.shapes.medium) }
        item { TabRow(selectedTabIndex=mode,containerColor=MaterialTheme.colorScheme.background) {
            listOf("录音","记忆").forEachIndexed { i,label->Tab(selected=mode==i,onClick={mode=i},text={Text(label)}) }
        } }
        if(mode==0) {
            if(matching.isEmpty()) item { Notice(if(query.isBlank()) "还没有录音" else "没有找到相关内容",if(query.isBlank()) "从今天页录下第一段声音。" else "换个词试试，或清空搜索。") }
            matching.groupBy { runCatching { Instant.parse(it.createdAt).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("yyyy年M月d日")) }.getOrDefault(it.createdAt.take(10)) }.forEach { (date,group)->
                item(key="date$date") { Section(date) }
                items(group,key={it.audioPath}) { record->RecordingRow(record){open(record)} }
            }
        } else {
            val memories=matching.flatMap { r->r.memories.filter { it.status=="active" && (query.isBlank() || (it.content+it.evidence+r.title).contains(query,ignoreCase=true)) }.map { r to it } }
            if(memories.isEmpty()) item { Notice("还没有可显示的记忆","原音仍在。核对文字并完成整理后，记忆会出现在这里。") }
            items(memories,key={it.first.audioPath+it.second.id}) { (record,memory)->
                Column(Modifier.fillMaxWidth().clickable(role=Role.Button){openMemory(record,memory.id)}.padding(vertical=12.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                    Muted(sourceLabel(memory.sourceType)); Text(memory.content,style=MaterialTheme.typography.titleMedium)
                    Muted("来自：${record.title}"); HorizontalDivider()
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun CapturePage(model: MobileViewModel,close:()->Unit,openDetail:(AudioRecording)->Unit) {
    val state by model.capture.collectAsState()
    val context=LocalContext.current
    val view=LocalView.current
    var previousPhase by remember { mutableStateOf(state.phase) }
    LaunchedEffect(state.phase) {
        if(previousPhase==CapturePhase.Saving && state.phase==CapturePhase.Saved) {
            view.performHapticFeedback(if(android.os.Build.VERSION.SDK_INT>=30) android.view.HapticFeedbackConstants.CONFIRM else android.view.HapticFeedbackConstants.KEYBOARD_TAP)
        }
        previousPhase=state.phase
    }
    var denied by rememberSaveable { mutableStateOf(false) }
    var consent by rememberSaveable { mutableStateOf(false) }
    var closing by rememberSaveable { mutableStateOf(false) }
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted -> denied=!granted; if(granted)model.start() }
    fun requestStart() {
        if(ContextCompat.checkSelfPermission(context,Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED)model.start()
        else permission.launch(Manifest.permission.RECORD_AUDIO)
    }
    val active=state.phase in listOf(CapturePhase.Recording,CapturePhase.Paused)
    fun requestClose() { if(active)closing=true else if(state.phase !in listOf(CapturePhase.Starting,CapturePhase.Saving))close() }
    BackHandler { requestClose() }
    Scaffold(modifier=Modifier.atmosphere(),containerColor=Color.Transparent,topBar={TopAppBar(title={Text("留下一段声音")},navigationIcon={IconButton(onClick={requestClose()}){Icon(Icons.Outlined.Close,"关闭录音")}})},
        bottomBar={ Surface(tonalElevation=2.dp) {
            Column(Modifier.navigationBarsPadding().padding(horizontal=20.dp,vertical=16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                when(state.phase) {
                    CapturePhase.Recording,CapturePhase.Paused -> {
                        OutlinedButton(onClick=model::pauseOrResume,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp).testTag(if(state.phase==CapturePhase.Paused)"capture.resume" else "capture.pause")) {
                            Icon(if(state.phase==CapturePhase.Paused)Icons.Filled.PlayArrow else Icons.Filled.Pause,null); Spacer(Modifier.width(8.dp)); Text(if(state.phase==CapturePhase.Paused)"继续录音" else "暂停录音")
                        }
                        Primary("完成并保存",Icons.Filled.Stop,tag="capture.stop"){model.finish()}
                    }
                    CapturePhase.Saved -> state.recording?.let { record->
                        Primary("查看录音与文字",Icons.Outlined.Description){openDetail(record)}
                        TextButton(onClick=model::newRecording,modifier=Modifier.fillMaxWidth()){Text("再录一段")}
                    }
                    CapturePhase.Starting,CapturePhase.Saving -> Primary(if(state.phase==CapturePhase.Starting)"正在启动麦克风…" else "正在保存…",Icons.Outlined.HourglassEmpty,false){}
                    else -> Primary("开始录音",Icons.Filled.Mic,tag="capture.start"){consent=true}
                }
            }
        }}) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(24.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(24.dp)) {
            Spacer(Modifier.height(12.dp))
            Heading(when(state.phase){CapturePhase.Saved->"这一段，留下了。";CapturePhase.Paused->"慢慢来。";CapturePhase.Recording->"我在听。";else->"把此刻，留在这里。"})
            Text(when(state.phase){CapturePhase.Recording->"正在录音";CapturePhase.Paused->"已暂停";CapturePhase.Saved->"录音已保存在手机";else->"由你决定什么时候开始"},color=MaterialTheme.colorScheme.onSurfaceVariant,modifier=Modifier.semantics { liveRegion=LiveRegionMode.Polite })
            Text(durationLabel(state.elapsedMillis),fontSize=52.sp,fontWeight=FontWeight.Light,fontFamily=FontFamily.Monospace)
            val color=MaterialTheme.colorScheme.primary
            Canvas(Modifier.fillMaxWidth().height(130.dp).clearAndSetSemantics { }) {
                val width=size.width*.72f
                val step=width/state.levels.size.coerceAtLeast(1)
                state.levels.forEachIndexed { i,level-> val height=6.dp.toPx()+level.coerceIn(0f,1f)*size.height*.72f
                    val x=size.width*.14f+step*(i+.5f)
                    drawLine(color,androidx.compose.ui.geometry.Offset(x,(size.height-height)/2),androidx.compose.ui.geometry.Offset(x,(size.height+height)/2),strokeWidth=step*.4f,cap=StrokeCap.Round)
                }
            }
            if(state.phase==CapturePhase.Saved)state.recording?.let{AudioPlayer(model,it)}
            else Muted("不必组织完整的句子。\n一个念头，也值得留下。")
            state.error?.let { Notice("操作未完成",it,true) }
            if(denied) {
                Notice("尚未开始录音","麦克风权限被拒绝。你可以重试，或在系统设置中允许麦克风。",true)
                TextButton(onClick={context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:${context.packageName}")))}){Text("前往设置")}
            }
        }
    }
    if(consent)AlertDialog(onDismissRequest={consent=false},title={Text("开始录下这段声音？")},text={Text("原音先保存在这台手机。转写与整理会由你另行操作，不会在录音时上传。")},
        confirmButton={TextButton(onClick={consent=false;requestStart()}){Text("同意并开始")}},dismissButton={TextButton(onClick={consent=false}){Text("暂不录音")}})
    if(closing)AlertDialog(onDismissRequest={closing=false},title={Text("要结束这段录音吗？")},text={Text("完成后原音会保存在手机，不会覆盖已有录音。")},
        confirmButton={TextButton(onClick={closing=false;model.finish(close)}){Text("完成并保存")}},dismissButton={TextButton(onClick={closing=false}){Text("继续录音")}})
}

@Composable fun AudioPlayer(model: MobileViewModel,record: AudioRecording) {
    val state by model.playback.collectAsState()
    val selected=state.audioPath==record.audioPath
    val duration=if(selected && state.durationMillis>0)state.durationMillis else record.durationMillis
    var seek by remember(record.audioPath) { mutableStateOf<Float?>(null) }
    Surface(shape=MaterialTheme.shapes.large,color=MaterialTheme.colorScheme.surface) {
        Column(Modifier.fillMaxWidth().padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) {
                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                    Text("原始录音",fontWeight=FontWeight.Medium)
                    Muted(when { selected&&state.preparing->"正在打开原音…";selected&&state.error!=null->"播放未完成，可重试";selected&&state.playing->"正在播放";selected&&duration>0&&state.positionMillis>=duration->"播放完毕";selected&&state.positionMillis>0->"已暂停";else->"准备好回听" })
                }
                Spacer(Modifier.width(16.dp))
                FilledIconButton(onClick={model.togglePlayback(record)},enabled=!(selected&&state.preparing),colors=IconButtonDefaults.filledIconButtonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.background),modifier=Modifier.size(48.dp).testTag("audio.play")) {
                    if(selected&&state.preparing) CircularProgressIndicator(Modifier.size(20.dp),strokeWidth=2.dp,color=MaterialTheme.colorScheme.background)
                    else Icon(if(selected&&state.playing)Icons.Filled.Pause else Icons.Filled.PlayArrow,if(selected&&state.playing)"暂停原音" else "播放原音")
                }
            }
            Slider(value=seek ?: (if(selected)state.positionMillis.toFloat() else 0f),onValueChange={seek=it},
                onValueChangeFinished={seek?.let{model.audio.seekPlayback(it.toLong())};seek=null},
                colors=SliderDefaults.colors(thumbColor=MaterialTheme.colorScheme.onSurface,activeTrackColor=MaterialTheme.colorScheme.onSurface),valueRange=0f..duration.coerceAtLeast(1).toFloat(),enabled=selected&&duration>0&&!state.preparing&&state.error==null,
                modifier=Modifier.heightIn(min=48.dp).semantics { contentDescription="原音播放进度" })
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Muted(durationLabel(seek?.toLong() ?: if(selected)state.positionMillis else 0)); Muted(durationLabel(duration)) }
            if(selected)state.error?.let { Text(it,color=MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable private fun DetailPage(model: MobileViewModel,record: AudioRecording,openMemory:(String)->Unit) {
    val pending by model.pending.collectAsState()
    val busy=record.audioPath in pending
    var text by rememberSaveable(record.audioPath,record.transcript) { mutableStateOf(record.reviewedTranscript ?: record.transcript) }
    var showConsent by remember { mutableStateOf(false) }
    var technical by rememberSaveable { mutableStateOf(false) }
    Scaffold(bottomBar={ if(record.transcript.isNotBlank()) Surface(tonalElevation=2.dp) {
        Column(Modifier.imePadding().padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Primary(if(busy)"处理中…" else if(model.canOrganize)"确认文字并整理记忆" else "保存核对文字",Icons.Outlined.CheckCircle,!busy&&text.isNotBlank(),"review.confirm") {
                if(model.canOrganize)showConsent=true else model.saveReview(record.audioPath,text)
            }
            if(!model.canOrganize)Muted("整理服务尚未连接，核对文字先保存在手机。")
        }
    } }) { padding -> Box(Modifier.padding(padding)) { Page {
        Heading(record.title)
        Muted("${dateLabel(record.createdAt)} · ${durationLabel(record.durationMillis)}")
        AudioPlayer(model,record)
        Notice(stageLabel(record.processingStage),when(record.processingStage){
            ProcessingStage.Complete->"记忆已整理，可以从下方查看来源。"
            ProcessingStage.Transcribing->"正在本机识别。原音已保存，可以离开页面稍后查看。"
            ProcessingStage.Organizing->"正在整理你确认过的文字。原音与文字已保存。"
            ProcessingStage.Failed->record.processingError ?: "处理未完成，可以重试。"
            ProcessingStage.NeedsReview->if(record.reviewedAt==null)"先听听原音，再核对下面的文字。" else "核对文字已保存。机器原始转写仍保留。"
            else->"原音保存在手机。你可以先听，也可以转成文字。"
        },error=record.processingStage==ProcessingStage.Failed)
        if(busy)LinearProgressIndicator(Modifier.fillMaxWidth().semantics { contentDescription="正在处理" })
        if(record.transcript.isBlank()) Primary(if(busy)"正在转成文字…" else "转成文字",Icons.Outlined.Description,!busy){model.transcribe(record.audioPath)}
        else {
            Section("核对文字")
            OutlinedTextField(text,{text=it},Modifier.fillMaxWidth().heightIn(min=180.dp).testTag("review.text"),label={Text("核对并修改转写文字")},enabled=!busy,shape=MaterialTheme.shapes.medium)
            if(record.reviewedAt!=null)Muted("已保存核对版本 · ${dateLabel(record.reviewedAt)}")
            if(record.memories.any { it.status=="active" }) {
                Section("从这段声音留下的记忆")
                record.memories.filter{it.status=="active"}.forEach { memory->
                    Surface(onClick={openMemory(memory.id)},shape=MaterialTheme.shapes.medium) {
                        Column(Modifier.fillMaxWidth().padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                            Muted(sourceLabel(memory.sourceType)); Text(memory.content); Text("查看来源",color=MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        }
        TextButton(onClick={technical=!technical}){Text(if(technical)"收起来源与处理详情" else "来源与处理详情")}
        if(technical) {
            Muted("机器原始转写：${record.transcript.ifBlank{"暂无"}}")
            Muted("${record.mimeType} · ${record.sampleRate} Hz · ${record.channelCount} 声道")
            if(record.personModelVersion.isNotBlank())Muted("处理版本：${record.personModelVersion}")
        }
    } } }
    if(showConsent)AlertDialog(onDismissRequest={showConsent=false},title={Text("确认文字并整理记忆？")},text={Text(model.dataUseDescription)},
        confirmButton={TextButton(onClick={showConsent=false;model.organize(record.audioPath,text,true)}){Text("同意并整理")}},
        dismissButton={TextButton(onClick={showConsent=false;model.saveReview(record.audioPath,text)}){Text("只保存文字")}})
}
fun sourceLabel(source: String)=when(source){"SUBJECT"->"本人叙述";"THIRD_PARTY"->"他人提供";"AI_INFERENCE"->"AI 推测";else->"来源待核对"}
@Composable private fun MemoryPage(model: MobileViewModel,record: AudioRecording,id: String,onDeleted:()->Unit) {
    val memory=record.memories.firstOrNull { it.id==id&&it.status=="active" }
    var confirm by remember { mutableStateOf(false) }
    val pending by model.pending.collectAsState()
    if(memory==null){Page{Notice("这条记忆已不在当前记录中","原始录音仍保留。")};return}
    Page {
        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
            RememberMeBrand(size=24.dp); Muted(sourceLabel(memory.sourceType))
        }
        Text(memory.content,style=MaterialTheme.typography.headlineMedium.copy(lineHeight=38.sp,fontWeight=FontWeight.Medium))
        Section("当时说过的话")
        HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
        Text(memory.evidence.ifBlank{"这条记忆没有可定位的引文，请听原音核对。"},style=MaterialTheme.typography.bodyLarge.copy(lineHeight=32.sp),color=MaterialTheme.colorScheme.onSurface)
        HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
        Muted("来自：${record.title} · ${dateLabel(record.createdAt)}")
        AudioPlayer(model,record)
        TextButton(onClick={confirm=true},enabled=record.audioPath !in pending){Text("删除这条记忆",color=MaterialTheme.colorScheme.error)}
    }
    if(confirm)AlertDialog(onDismissRequest={confirm=false},title={Text("删除这条记忆？")},text={Text("它将从当前记忆中移除。原始录音、转写和本地历史仍会保留。")},
        confirmButton={TextButton(onClick={confirm=false;model.deleteMemory(record.audioPath,id)}){Text("删除记忆")}},dismissButton={TextButton(onClick={confirm=false}){Text("取消")}})
}
@Composable private fun ProfilePage(model: MobileViewModel) {
    val context=LocalContext.current
    Page {
        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)){RememberMeBrand(size=32.dp);Heading("我的")}
        Notice("原音留在手机","录音与核对文字保存在此应用的私有空间。录音时不会自动上传。")
        Muted("本版不自动备份录音。卸载应用或清除应用数据会删除本机内容。")
        Section("数据与授权")
        Text("每次录音都会询问你的同意。整理文字需要另行确认；录音授权不代表声音克隆授权。")
        OutlinedButton(onClick={context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:${context.packageName}")))},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text("管理系统麦克风权限")}
        HorizontalDivider(); Section("外观"); Text("跟随系统"); Muted("支持深色模式、系统大字号与减少动态效果。")
        HorizontalDivider(); Section("整理服务"); Text(if(model.canOrganize)"已配置" else "尚未连接"); Muted(model.dataUseDescription)
        Muted("勿忘我 · 每一段原音，都值得完整保留。")
    }
}

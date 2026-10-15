package me.remember.app.integration

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable internal fun CalibrationSection(state: NativeState, model: NativeWorkbenchModel, openPerson: () -> Unit) {
    val selected=state.calibrations.firstOrNull{it.text("calibration_id")==state.calibrationId}
    val ready=!state.busy&&!state.recording
    var history by remember(state.subject) { mutableStateOf(false) }
    if(state.calibrations.isNotEmpty()) {
        TextButton(onClick={history=!history},enabled=ready) {Text(if(history) "收起以前的对照" else "以前的对照")}
        if(history) state.calibrations.forEach { run -> key(run.text("calibration_id")) {
            RememberActionButton(run.text("question"),ready,pendingLabel="正在读取对照…",successLabel="对照已打开") {model.openCalibration(run.text("calibration_id"))}
        } }
    }
    selected?.let { run -> Panel {
        val id=run.text("calibration_id")
        val context=LocalContext.current
        val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {allowed ->
            if(allowed) model.start(null,id) else model.report("请允许麦克风权限后重试。")
        }
        val import=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) {uri ->
            if(uri!=null) model.importCalibrationAudio(id,context.contentResolver.getType(uri).orEmpty()) {
                context.contentResolver.openInputStream(uri)?.use {input ->
                    val out=java.io.ByteArrayOutputStream();val buffer=ByteArray(8192)
                    while(true){val read=input.read(buffer);if(read<0)break;require(out.size()+read<=40*1024*1024){"请选择不超过40MB的音频。"};out.write(buffer,0,read)}
                    out.toByteArray()
                } ?: throw IllegalArgumentException("无法打开音频。")
            }
        }
        Text("和我的想法对照",style=MaterialTheme.typography.titleLarge)
        Text(run.text("question"),style=MaterialTheme.typography.titleMedium)
        if(run.text("status")=="stale") Text("原故事已有变化，请重新聊一聊，再开始对照。") else {
            if(!run.optBoolean("answer_hidden")){
                Text("当时的 AI 分身回答",style=MaterialTheme.typography.labelLarge)
                Text(run.text("locked_answer"))
            }
            val episode=run.text("human_episode_id")
            val story=state.stories.firstOrNull{it.text("episode_id")==episode}
            val captures=state.local.filter{it.calibrationId==id}
            if(run.text("status")=="awaiting_human") {
                Text("我的补充",style=MaterialTheme.typography.titleMedium)
                if(episode.isBlank()&&captures.isEmpty()) {
                    Text("想一想这个问题，说说你会怎么做、为什么。")
                    Action("录下我的想法",ready) {permission.launch(Manifest.permission.RECORD_AUDIO)}
                    Action("选择本人音频",ready) {import.launch(arrayOf("audio/*"))}
                }
                if(state.recording) {
                    Text(clock(state.elapsed))
                    Action(if(state.paused) "继续录音" else "暂停录音",!state.busy) {model.pauseOrResumeRecording()}
                    RememberActionButton("完成并保存原音",!state.busy,filled=true,pendingLabel="正在保存原音…",successLabel="原音已保存") {model.finish()}
                }
                if(captures.isNotEmpty()&&!state.recording) CaptureTab(state.copy(local=captures),model,null,{})
                if(episode.isNotBlank()) {
                    RememberActionButton("听我的原音",ready,pendingLabel="正在取回声音…",successLabel="声音已取回") {model.playSource(episode)}
                    if(story?.optBoolean("waiting_for_review")==true) Action("核对我的转写",ready) {model.review(episode)}
                    else Text(if(story?.text("status")=="ready") "我的文字已核对" else "正在整理本人录音")
                    var consent by remember(id) {mutableStateOf(false)}
                    Check("同意将两段回答交由云端比较",consent,{consent=it})
                    RememberActionButton("看看有哪些不同",ready&&consent&&story?.text("status")=="ready"&&story.optBoolean("reviewed"),filled=true,
                        pendingLabel="正在比较…",successLabel="对照已返回") {model.completeCalibration(id,consent)}
                }
            }
            if(run.text("status")=="complete") {
                var speakConsent by remember(id){mutableStateOf(false)}
                RememberActionButton("听听这次对照",ready){speakConsent=true}
                if(speakConsent)AlertDialog(onDismissRequest={speakConsent=false},title={Text("听听这次对照")},
                    text={Text("将差异说明交给云端，用白桦音色播放。")},
                    confirmButton={TextButton(onClick={speakConsent=false;model.beginVoice("evidence",false,id)}){Text("播放")}},
                    dismissButton={TextButton(onClick={speakConsent=false}){Text("取消")}})
                Text("这次对照",style=MaterialTheme.typography.titleMedium)
                Text(run.text("summary"))
                val dimensions=mapOf("DECISION" to "选择","REASONING" to "考虑过程","VALUE_PRIORITY" to "更在意什么","EMOTIONAL_REACTION" to "感受","EXPRESSION" to "表达")
                val alignments=mapOf("MATCH" to "一致","PARTIAL" to "部分相近","DIFFERENT" to "有所不同","NOT_OBSERVED" to "这次没有提到")
                run.rows("dimensions").forEach {item ->
                    Column(Modifier.testTag("calibration-dimension-${item.text("dimension")}"),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                        Text("${dimensions[item.text("dimension")].orEmpty()} · ${alignments[item.text("alignment")].orEmpty()}",style=MaterialTheme.typography.labelLarge)
                        Text(item.text("note"));if(item.text("human_excerpt").isNotBlank()) Text("我的原话：${item.text("human_excerpt")}")
                    }
                }
                if(run.text("suggested_question").isNotBlank()) Text("可以继续聊：${run.text("suggested_question")}")
                if(episode.isNotBlank()) RememberActionButton("听我的原音",ready,pendingLabel="正在取回声音…",successLabel="声音已取回") {model.playSource(episode)}
                Action("查看人物理解与待确认更新",ready,openPerson)
            }
        }
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            RememberActionButton("刷新对照",ready,fullWidth=false,pendingLabel="正在刷新…",successLabel="已刷新",onClick=model::refresh)
            TextButton(onClick=model::closeCalibration,enabled=ready) {Text("收起")}
        }
    } }
}

package me.remember.app.integration

import android.Manifest
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.remember.app.core.designsystem.LocalSimpleMode
import me.remember.app.core.designsystem.NatureScene
import me.remember.app.core.designsystem.atmosphere

@Composable internal fun VoiceCallEntry(state:NativeState,model:NativeWorkbenchModel,mode:String){
    var consent by remember(state.actor,state.subject){mutableStateOf(false)}
    var fast by remember(state.actor,state.subject){mutableStateOf(false)}
    var realtime by remember(state.actor,state.subject){mutableStateOf(false)}
    val useRealtime=realtime&&state.stepVoiceAvailable
    val useFast=fast&&state.fastVoiceAvailable
    val simple=LocalSimpleMode.current
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if(granted)model.beginVoice(mode,simple,responseSpeed=if(useFast)"fast" else "reviewed",voiceEngine=if(useRealtime)"step_realtime" else "pipeline") else model.report("允许麦克风后即可语音聊天。")
    }
    RememberActionButton("语音聊聊",!state.busy&&!state.recording,filled=true,icon=Icons.Outlined.Mic){realtime=false;consent=true;model.loadVoiceCapabilities()}
    if(consent) AlertDialog(onDismissRequest={consent=false},title={Text("开始语音聊聊")},
        text={Column(verticalArrangement=Arrangement.spacedBy(12.dp)){
            Text("通话声音会发送到云端识别，并结合你可访问的记忆回答。回答使用合成声音播放，通话不会自动存成记忆。")
            if(state.stepVoiceAvailable)Row(verticalAlignment=Alignment.CenterVertically){Text("实时试用",Modifier.weight(1f));Switch(checked=realtime,onCheckedChange={realtime=it},modifier=Modifier.testTag("voice-realtime"))}
            if(!useRealtime&&state.fastVoiceAvailable)Row(verticalAlignment=Alignment.CenterVertically){Text("快速回复",Modifier.weight(1f));Switch(checked=fast,onCheckedChange={fast=it},modifier=Modifier.testTag("voice-fast"))}
        }},
        confirmButton={TextButton(enabled=!state.busy,onClick={consent=false;permission.launch(Manifest.permission.RECORD_AUDIO)}){Text("开始")}},
        dismissButton={TextButton(onClick={consent=false}){Text("暂不")}})
}

@Composable internal fun VoiceCallScreen(engine:VoiceCallEngine,onEnd:()->Unit){
    val state by engine.ui.collectAsStateWithLifecycle()
    var captions by remember{mutableStateOf(false)}
    var sources by remember{mutableStateOf(false)}
    BackHandler{onEnd()}
    Column(Modifier.fillMaxSize().atmosphere(scene=NatureScene.Lake).systemBarsPadding().padding(24.dp),
        horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(20.dp)){
        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){
            Text("语音聊聊",style=MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.weight(1f));SuggestionChip(onClick={},label={Text("AI 分身")})
        }
        Spacer(Modifier.weight(.5f))
        Box(Modifier.size(128.dp).background(MaterialTheme.colorScheme.primaryContainer.copy(alpha=.85f),CircleShape),contentAlignment=Alignment.Center){
            Icon(if(state.paused)Icons.Outlined.MicOff else Icons.Outlined.GraphicEq,null,
                Modifier.size(58.dp),tint=MaterialTheme.colorScheme.onPrimaryContainer)
        }
        Text(state.status,style=MaterialTheme.typography.headlineMedium)
        if(state.error.isNotBlank())Text(state.error,color=MaterialTheme.colorScheme.error)
        Row(horizontalArrangement=Arrangement.spacedBy(16.dp)){
            TextButton(onClick={captions=!captions}){Text(if(captions)"收起字幕" else "字幕")}
            if(state.sources!=null)TextButton(onClick={sources=!sources}){Text("相关故事")}
        }
        if(captions||sources)Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)){
            if(captions){
                if(state.transcript.isNotBlank())Card{Text(state.transcript,Modifier.padding(16.dp))}
                if(state.answer.isNotBlank())Card{Text(state.answer,Modifier.padding(16.dp))}
            }
            if(sources)state.sources?.rows("evidence")?.forEach{e->Card{Text(e.text("excerpt"),Modifier.padding(16.dp))}}
        }else Spacer(Modifier.weight(1f))
        if(state.active&&state.inputEnabled)Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceEvenly){
            FilledTonalButton(onClick={engine.toggleMute()}){Text(if(state.muted)"取消静音" else "静音")}
            FilledTonalButton(onClick={if(state.paused)engine.resume() else engine.pause()}){Text(if(state.paused)"继续" else "暂停")}
        }
        Button(onClick=onEnd,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp),colors=ButtonDefaults.buttonColors(containerColor=MaterialTheme.colorScheme.errorContainer,contentColor=MaterialTheme.colorScheme.onErrorContainer)){Text("结束")}
    }
}

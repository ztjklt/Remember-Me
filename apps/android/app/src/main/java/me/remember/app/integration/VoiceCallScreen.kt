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
    VoiceCallContent(state,{if(state.paused)engine.resume() else engine.pause()},engine::interrupt,onEnd)
}

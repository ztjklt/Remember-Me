package me.remember.app.integration

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import me.remember.app.core.designsystem.LocalSimpleMode

/** Project choices, not platform mandates. Share timing across functional transitions. */
internal object RememberMotion {
    const val EnterMillis=200
    const val FeedbackMillis=220
    const val LoadingDelayMillis=180L
}

/** Animate only the CURRENT content; never retain a previous identity's outgoing page. */
@Composable internal fun Modifier.rememberPageEntrance(page: Any): Modifier {
    val motion=interactionMotion()
    val progress=remember {Animatable(1f)}
    val distance=with(LocalDensity.current) {6.dp.toPx()}
    LaunchedEffect(page,motion) {
        if(motion) {progress.snapTo(0f);progress.animateTo(1f,tween(RememberMotion.EnterMillis))}
        else progress.snapTo(1f)
    }
    return graphicsLayer {
        alpha=if(motion) .7f+.3f*progress.value else 1f
        translationY=if(motion) distance*(1f-progress.value) else 0f
    }
}

/** Fixed layout slot prevents a fast refresh from moving every control below it. */
@Composable internal fun RememberLoadingSlot(busy: Boolean, modifier: Modifier=Modifier) {
    var visible by remember {mutableStateOf(false)}
    LaunchedEffect(busy) {
        visible=false
        if(busy) {delay(RememberMotion.LoadingDelayMillis);visible=true}
    }
    Box(modifier.fillMaxWidth().height(6.dp)) {
        if(busy && visible) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("workbench-loading"))
    }
}

/** Preserve the real error in a readable detail view rather than filling the whole page. */
@Composable internal fun RememberIssue(message: String, dismiss: () -> Unit) {
    var details by remember(message) {mutableStateOf(false)}
    Surface(shape=RoundedCornerShape(20.dp),color=MaterialTheme.colorScheme.errorContainer,
        contentColor=MaterialTheme.colorScheme.onErrorContainer) {
        Column(Modifier.fillMaxWidth().padding(start=16.dp,end=8.dp,top=8.dp,bottom=8.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) {
                Icon(Icons.Outlined.Info,null,Modifier.size(20.dp))
                Text("这一步没有完成",Modifier.weight(1f).padding(horizontal=8.dp)
                    .semantics {liveRegion=LiveRegionMode.Polite},style=MaterialTheme.typography.titleMedium)
                IconButton(onClick=dismiss) {Icon(Icons.Outlined.Close,"关闭提示")}
            }
            Text(message,Modifier.padding(end=8.dp),maxLines=2,overflow=TextOverflow.Ellipsis,
                style=MaterialTheme.typography.bodyMedium)
            TextButton(onClick={details=true}) {Text("查看原因")}
        }
    }
    if(details) AlertDialog(onDismissRequest={details=false},title={Text("未完成的原因")},
        text={Text(message,Modifier.heightIn(max=360.dp).verticalScroll(rememberScrollState()))},
        confirmButton={TextButton(onClick={details=false}) {Text("返回")}})
}

/** No server/model timeouts and no waveform amplitude are simulated by this graphic. */
@Composable internal fun RememberRecordingStatus(recording: Boolean, paused: Boolean, elapsed: Long) {
    val motion=interactionMotion()
    val active=recording && !paused
    val color by animateColorAsState(if(active) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainerHigh,
        if(motion) tween(RememberMotion.FeedbackMillis) else snap(),label="recording state")
    Column(Modifier.fillMaxWidth(),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(16.dp)) {
        Surface(shape=CircleShape,color=color) {
            Box(Modifier.size(96.dp),contentAlignment=Alignment.Center) {
                Icon(if(paused && recording) Icons.Outlined.Pause else Icons.Outlined.Mic,
                    null,Modifier.size(40.dp),tint=MaterialTheme.colorScheme.primary)
            }
        }
        Text(clock(elapsed),style=(if(LocalSimpleMode.current) MaterialTheme.typography.headlineLarge else MaterialTheme.typography.displayMedium).copy(fontFeatureSettings="tnum"))
        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp),
            modifier=Modifier.semantics(mergeDescendants=true) {liveRegion=LiveRegionMode.Polite}) {
            Surface(shape=CircleShape,color=if(active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline) {Box(Modifier.size(8.dp))}
            Text(if(recording) if(paused) "已暂停，随时继续" else "正在录音" else "准备好就开始",style=MaterialTheme.typography.titleMedium)
        }
    }
}

/** During a drag the UI owns the thumb, and sends one seek on release. A source/identity
 * change disposes the entire gesture; old drag data must never seek the next recording. */
@Composable internal fun RememberAudioScrubber(sourceKey: String, position: Long, duration: Long,
    enabled: Boolean, seek: (Long) -> Unit, modifier: Modifier=Modifier,
    colors: SliderColors=SliderDefaults.colors()) {
    key(sourceKey) {
        var draft by remember {mutableStateOf<Float?>(null)}
        val valid=enabled && duration>0
        val interactions=remember {MutableInteractionSource()}
        LaunchedEffect(valid) {if(!valid) draft=null}
        LaunchedEffect(interactions) {interactions.interactions.collect {if(it is DragInteraction.Cancel) draft=null}}
        val value=(draft ?: position.toFloat()).coerceIn(0f,duration.coerceAtLeast(1).toFloat())
        Slider(value,{if(valid) draft=it},modifier.heightIn(min=48.dp).semantics {contentDescription="播放进度"},
            enabled=valid,valueRange=0f..duration.coerceAtLeast(1).toFloat(),colors=colors,interactionSource=interactions,
            onValueChangeFinished={
                val target=draft
                draft=null
                if(valid && target!=null) seek(target.toLong().coerceIn(0,duration))
            })
    }
}

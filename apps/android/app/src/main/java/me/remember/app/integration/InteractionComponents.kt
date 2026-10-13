package me.remember.app.integration

import android.animation.ValueAnimator
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import me.remember.app.core.designsystem.LocalSimpleMode

internal data class InteractionContext(
    val identity: String = "",
    val operation: OperationFeedback = OperationFeedback(),
    val latest: () -> OperationFeedback = { operation },
    val reduceMotion: Boolean = false,
)
internal val LocalInteractions = staticCompositionLocalOf { InteractionContext() }

@Composable internal fun interactionMotion(): Boolean =
    !LocalInteractions.current.reduceMotion && !LocalSimpleMode.current && ValueAnimator.areAnimatorsEnabled()

/** Press feedback without changing the semantic target or minimum hit area. */
@Composable internal fun RememberActionButton(
    label: String,
    enabled: Boolean = true,
    modifier: Modifier = Modifier,
    fullWidth: Boolean = true,
    filled: Boolean = false,
    icon: ImageVector? = null,
    pendingLabel: String = "正在提交…",
    successLabel: String = "已提交",
    requestTicket: Long? = null,
    onClick: () -> Unit,
) {
    val context = LocalInteractions.current
    var ticket by remember(context.identity, label) { mutableStateOf<Long?>(null) }
    val phase = actionPhase(requestTicket ?: ticket, context.operation)
    val running = phase == ActionPhase.RUNNING
    val interactions = remember { MutableInteractionSource() }
    val pressed by interactions.collectIsPressedAsState()
    val motion = interactionMotion()
    val scale by animateFloatAsState(if(pressed && enabled && motion) .985f else 1f,
        if(motion) spring(dampingRatio = .85f, stiffness = 550f) else snap(), label = "button press")
    val target = when(phase) {
        ActionPhase.SUCCEEDED -> MaterialTheme.colorScheme.primaryContainer
        ActionPhase.FAILED -> MaterialTheme.colorScheme.errorContainer
        else -> if(filled || running) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface.copy(alpha=.92f)
    }
    val color by animateColorAsState(target, if(motion) tween(RememberMotion.FeedbackMillis) else snap(), label="button state")
    val foreground = when(phase) {
        ActionPhase.SUCCEEDED -> MaterialTheme.colorScheme.onPrimaryContainer
        ActionPhase.FAILED -> MaterialTheme.colorScheme.onErrorContainer
        else -> if(filled || running) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.primary
    }
    val status = when(phase) {
        ActionPhase.RUNNING -> pendingLabel
        ActionPhase.SUCCEEDED -> successLabel
        ActionPhase.FAILED -> "未完成 · 重试"
        ActionPhase.CANCELLED -> "已中断 · 重试"
        else -> label
    }
    Button(onClick = {
        // Only the operation started by THIS tap can produce this button's result.
        if(actionPhase(requestTicket ?: ticket, context.latest()) != ActionPhase.RUNNING) {
            val before = context.latest().id
            onClick()
            ticket = context.latest().takeIf { it.id > before }?.id
        }
    }, enabled = enabled && !running, interactionSource = interactions,
        shape = RoundedCornerShape(22.dp),
        border = if(!filled && !running) BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant) else null,
        colors = ButtonDefaults.buttonColors(containerColor=color, contentColor=foreground,
            disabledContainerColor=if(running) color else MaterialTheme.colorScheme.surfaceVariant,
            disabledContentColor=if(running) foreground else MaterialTheme.colorScheme.onSurfaceVariant),
        contentPadding = PaddingValues(horizontal=18.dp, vertical=14.dp),
        modifier=modifier.then(if(fullWidth) Modifier.fillMaxWidth() else Modifier).heightIn(min=if(LocalSimpleMode.current) 60.dp else 52.dp)
            .graphicsLayer { scaleX=scale; scaleY=scale }
            .semantics { stateDescription=status; liveRegion=LiveRegionMode.Polite }) {
        when(phase) {
            ActionPhase.RUNNING -> CircularProgressIndicator(Modifier.size(22.dp).clearAndSetSemantics {}, color=foreground,strokeWidth=2.dp)
            ActionPhase.SUCCEEDED -> Icon(Icons.Outlined.CheckCircle,null,Modifier.size(22.dp))
            ActionPhase.FAILED, ActionPhase.CANCELLED -> Icon(Icons.Outlined.Refresh,null,Modifier.size(22.dp))
            else -> icon?.let { Icon(it,null,Modifier.size(22.dp)) }
        }
        if(icon != null || phase != ActionPhase.IDLE) Spacer(Modifier.width(10.dp))
        // Keep the name during loading: shrinking to an unlabeled dot loses context.
        Text(if(phase == ActionPhase.IDLE) label else "$label · $status")
    }
}

/** A controlled switch: only persisted/system-confirmed checked state moves the thumb. */
@Composable internal fun RememberToggle(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    supporting: String? = null,
    enabled: Boolean = true,
) {
    val context=LocalInteractions.current
    var ticket by remember(context.identity,label) {mutableStateOf<Long?>(null)}
    val phase=actionPhase(ticket,context.operation)
    val running=phase==ActionPhase.RUNNING
    val motion = interactionMotion()
    val position by animateFloatAsState(if(checked) 1f else 0f,
        if(motion) spring(dampingRatio=.8f,stiffness=520f) else snap(), label="switch position")
    val targetColor = if(checked) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline
    val color by animateColorAsState(targetColor,if(motion) tween(240) else snap(),label="switch track")
    val density=LocalDensity.current
    val rtl=LocalLayoutDirection.current == LayoutDirection.Rtl
    val travel=with(density) { 22.dp.toPx() }
    val amount=position.coerceIn(0f,1f)
    Row(modifier.fillMaxWidth().heightIn(min=if(LocalSimpleMode.current) 64.dp else 56.dp)
        .toggleable(checked,enabled=enabled&&!running,role=Role.Switch,onValueChange={value ->
            if(actionPhase(ticket,context.latest())!=ActionPhase.RUNNING) {
                val before=context.latest().id
                onCheckedChange(value)
                ticket=context.latest().takeIf{it.id>before}?.id
            }
        })
        .semantics { stateDescription=if(running) "正在保存" else if(checked) "已开启" else "已关闭";liveRegion=LiveRegionMode.Polite }
        .padding(vertical=10.dp),verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(16.dp)) {
        Column(Modifier.weight(1f)) {
            Text(label,style=MaterialTheme.typography.titleMedium)
            supporting?.let { Text(it,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        if(running) CircularProgressIndicator(Modifier.size(20.dp).clearAndSetSemantics {},strokeWidth=2.dp)
        Box(Modifier.size(56.dp,34.dp).clip(CircleShape).background(if(enabled) color else color.copy(alpha=.45f)).clearAndSetSemantics {}) {
            Box(Modifier.padding(4.dp).size(26.dp).graphicsLayer {
                translationX=if(rtl) -travel*amount else travel*amount
                scaleX=if(motion) 1f+.16f*4f*amount*(1f-amount) else 1f
            }.background(if(checked) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.surface,CircleShape),contentAlignment=Alignment.Center) {
                if(checked) Icon(Icons.Outlined.Check,null,Modifier.size(16.dp),tint=MaterialTheme.colorScheme.primary)
            }
        }
    }
}

/** Confirm first, then associate this button with the request started by that confirmation. */
@Composable internal fun RememberConfirmedAction(
    label: String, message: String, destructive: Boolean, enabled: Boolean=true,
    modifier: Modifier=Modifier, fullWidth: Boolean=true,
    pendingLabel: String="正在提交…", successLabel: String="已提交", action: () -> Unit,
) {
    val context=LocalInteractions.current
    var asking by remember(context.identity,label) {mutableStateOf(false)}
    var ticket by remember(context.identity,label) {mutableStateOf<Long?>(null)}
    RememberActionButton(label,enabled,modifier,fullWidth=fullWidth,pendingLabel=pendingLabel,
        successLabel=successLabel,requestTicket=ticket) {asking=true}
    if(asking) RememberConfirmationDialog(message,destructive,enabled,
        dismiss={asking=false},confirm={
            asking=false
            val before=context.latest().id
            action()
            ticket=context.latest().takeIf{it.id>before}?.id
        })
}

/** Optional hold inside an explicit confirmation; tap remains available to everyone. */
@Composable internal fun RememberConfirmationDialog(
    message: String, destructive: Boolean, enabled: Boolean=true,
    dismiss: () -> Unit, confirm: () -> Unit,
) {
    var committed by remember { mutableStateOf(false) }
    fun commit() { if(enabled && !committed) { committed=true; confirm() } }
    AlertDialog(onDismissRequest=dismiss,containerColor=MaterialTheme.colorScheme.surface,
        iconContentColor=MaterialTheme.colorScheme.primary,shape=RoundedCornerShape(28.dp),
        icon={Icon(if(destructive) Icons.Outlined.Shield else Icons.Outlined.CheckCircle,null)},
        title={Text(if(destructive) "确认这项操作？" else "请核对后确认")},
        text={Column(verticalArrangement=Arrangement.spacedBy(20.dp)) {
            Text(message)
            if(destructive && !LocalSimpleMode.current) HoldConfirmation(enabled && !committed) { commit() }
        }},
        confirmButton={TextButton(onClick={commit()},enabled=enabled && !committed,
            modifier=Modifier.heightIn(min=if(LocalSimpleMode.current)60.dp else 48.dp)) {Text("确认")} },
        dismissButton={TextButton(onClick=dismiss,modifier=Modifier.heightIn(min=if(LocalSimpleMode.current)60.dp else 48.dp)) {Text("取消")} })
}

@Composable private fun HoldConfirmation(enabled: Boolean, confirm: () -> Unit) {
    val progress=remember { Animatable(0f) }
    val latestConfirm by rememberUpdatedState(confirm)
    val owner=LocalLifecycleOwner.current
    var activeHold by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }
    var foreground by remember { mutableStateOf(owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    DisposableEffect(owner) {
        val observer=LifecycleEventObserver { _, _ ->
            foreground=owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
            // A background window may not recompose promptly. Cancel immediately
            // in the lifecycle callback, without waiting for pointerInput restart.
            if(!foreground) activeHold?.cancel()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { activeHold?.cancel(); owner.lifecycle.removeObserver(observer) }
    }
    val ink=MaterialTheme.colorScheme.primary
    val track=MaterialTheme.colorScheme.outlineVariant
    LaunchedEffect(enabled,foreground) { if(!enabled || !foreground) progress.snapTo(0f) }
    Column(Modifier.fillMaxWidth(),horizontalAlignment=Alignment.CenterHorizontally) {
        Box(Modifier.size(88.dp).testTag("hold-confirm")
            // The ordinary confirm button supplies accessible click/keyboard access.
            .clearAndSetSemantics { contentDescription="长按确认，也可使用下方确认按钮" }
            .pointerInput(enabled,foreground) {
                if(enabled && foreground) detectTapGestures(onPress={
                    coroutineScope {
                        progress.snapTo(0f)
                        val timer=launch {
                            // Do not use animation duration: system motion settings must
                            // never turn 1.5s of intentional holding into instant deletion.
                            val started=android.os.SystemClock.elapsedRealtime()
                            while(true) {
                                val fraction=((android.os.SystemClock.elapsedRealtime()-started)/1500f).coerceAtMost(1f)
                                progress.snapTo(fraction)
                                if(fraction>=1f) break
                                kotlinx.coroutines.delay(16)
                            }
                            if(owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) latestConfirm()
                        }
                        activeHold=timer
                        try { tryAwaitRelease() } finally {
                            timer.cancel()
                            activeHold=null
                            kotlinx.coroutines.withContext(kotlinx.coroutines.NonCancellable) { progress.snapTo(0f) }
                        }
                    }
                })
            },contentAlignment=Alignment.Center) {
            Canvas(Modifier.fillMaxSize().padding(4.dp)) {
                drawArc(track,-90f,360f,false,style=Stroke(4.dp.toPx(),cap=StrokeCap.Round))
                drawArc(ink,-90f,360f*progress.value,false,
                    style=Stroke(4.dp.toPx(),cap=StrokeCap.Round))
            }
            Icon(Icons.Outlined.TouchApp,null,Modifier.size(30.dp),tint=ink)
        }
        Text("长按 1.5 秒确认",style=MaterialTheme.typography.labelLarge)
        Text("松手取消，也可点下方确认",style=MaterialTheme.typography.bodySmall)
    }
}

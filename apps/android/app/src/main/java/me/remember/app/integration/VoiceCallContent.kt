package me.remember.app.integration

import android.app.Activity
import android.content.ContextWrapper
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import me.remember.app.core.designsystem.NatureScene
import me.remember.app.core.designsystem.RememberMeBrand
import me.remember.app.core.designsystem.atmosphere

/** Production presentation; fixtures enter here without enabling any microphone or cloud call. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun VoiceCallContent(
    state: CallUi, onPause: () -> Unit,
    onInterrupt: () -> Unit, onEnd: () -> Unit,
) {
    var details by remember { mutableStateOf(false) }
    val view = LocalView.current
    val surface = MaterialTheme.colorScheme.background
    SideEffect {
        val activity = generateSequence(view.context) { (it as? ContextWrapper)?.baseContext }
            .filterIsInstance<Activity>().firstOrNull()
        activity?.window?.let { window ->
            WindowCompat.setDecorFitsSystemWindows(window, false)
            @Suppress("DEPRECATION")
            run { window.statusBarColor = surface.toArgb(); window.navigationBarColor = surface.toArgb() }
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = surface.luminance() > .5f
                isAppearanceLightNavigationBars = surface.luminance() > .5f
            }
        }
    }
    BackHandler { if (details) details = false else onEnd() }
    Column(Modifier.fillMaxSize().atmosphere(scene = NatureScene.Lake).systemBarsPadding().padding(horizontal = 24.dp)) {
        Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("语音聊聊", style = MaterialTheme.typography.titleLarge)
                Text("AI 分身", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            IconButton(onClick = { details = true }, modifier = Modifier.size(52.dp).testTag("voice-details")) {
                Icon(Icons.AutoMirrored.Outlined.Chat, "本轮对话")
            }
        }
        Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            VoicePresence(state.phase)
            Spacer(Modifier.height(28.dp))
            Text(state.status.ifBlank { "正在连接" }, style = MaterialTheme.typography.headlineLarge,
                textAlign = TextAlign.Center, modifier = Modifier.testTag("voice-status").semantics { liveRegion = LiveRegionMode.Polite })
            val hint = when {
                state.error.isNotBlank() -> state.error
                state.paused -> "准备好了，点继续"
                !state.inputEnabled -> "听完后可以返回"
                state.phase == CallPhase.LISTENING -> "慢慢说，我在这里"
                state.phase == CallPhase.THINKING -> "正在查找相关记忆"
                state.phase == CallPhase.PREPARING -> "回答已就绪"
                state.phase == CallPhase.SPEAKING -> "你可以随时接着说"
                else -> ""
            }
            if (hint.isNotBlank()) Text(hint, Modifier.padding(top = 12.dp), textAlign = TextAlign.Center,
                style = MaterialTheme.typography.bodyLarge,
                color = if (state.error.isNotBlank()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
            // Reserve the slot so the main status never jumps as a round changes.
            Box(Modifier.fillMaxWidth().heightIn(min = 76.dp).padding(top = 16.dp), contentAlignment = Alignment.Center) {
                if (state.canInterrupt) OutlinedButton(onClick = onInterrupt, modifier = Modifier.testTag("voice-interrupt")) {
                    Icon(Icons.Outlined.RecordVoiceOver, null, Modifier.size(20.dp)); Spacer(Modifier.width(8.dp)); Text("我来说")
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(bottom = 24.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (state.active && state.inputEnabled) {
                VoiceControl(if (state.paused) "继续" else "暂停", if (state.paused) Icons.Outlined.PlayArrow else Icons.Outlined.Pause,
                    state.ready, Modifier.weight(1f), onPause)
            }
            VoiceControl(if (state.active) "结束" else "返回", Icons.Outlined.CallEnd, true, Modifier.weight(1f), onEnd, end = true)
        }
    }
    if (details) ModalBottomSheet(onDismissRequest = { details = false }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.fillMaxHeight(.84f).padding(horizontal = 24.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("本轮对话", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                TextButton(onClick = { details = false }) { Text("收起") }
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(20.dp)) {
                if (state.transcript.isBlank() && state.answer.isBlank()) Text("开始说话后，文字会出现在这里。", Modifier.padding(vertical = 24.dp))
                if (state.transcript.isNotBlank()) VoiceTextBlock("你刚才说", state.transcript)
                if (state.answer.isNotBlank()) VoiceTextBlock(state.sources?.let(::voiceAnswerLabel) ?: "回答", state.answer)
                val evidence = state.sources?.rows("evidence").orEmpty()
                if (evidence.isNotEmpty()) {
                    var expanded by remember(state.sources) { mutableStateOf(false) }
                    TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "收起依据" else "查看回答依据") }
                    if (expanded) evidence.forEach { VoiceTextBlock("相关记忆", it.text("excerpt")) }
                }
                Spacer(Modifier.height(16.dp))
            }
            Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (state.canInterrupt) OutlinedButton(onClick = onInterrupt, modifier = Modifier.weight(1f)) { Text("我来说") }
                Button(onClick = onEnd, modifier = Modifier.weight(1f)) { Text(if (state.active) "结束通话" else "返回") }
            }
        }
    }
}

@Composable private fun VoiceTextBlock(label: String, text: String) {
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceContainerHigh, RoundedCornerShape(20.dp)).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(label, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary)
        SelectionContainer { Text(text, style = MaterialTheme.typography.bodyLarge) }
    }
}

@Composable private fun VoicePresence(phase: CallPhase) {
    val moving = interactionMotion() && phase in setOf(CallPhase.LISTENING, CallPhase.THINKING, CallPhase.PREPARING, CallPhase.SPEAKING)
    val scale = if (moving) {
        val transition = rememberInfiniteTransition(label = "conversation-presence")
        val value by transition.animateFloat(.97f, 1.03f,
            infiniteRepeatable(tween(2200, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "presence-breath")
        value
    } else 1f
    val accent = MaterialTheme.colorScheme.primary
    Box(Modifier.size(232.dp), contentAlignment = Alignment.Center) {
        // Ambient state animation only; never presented as measured microphone amplitude.
        Box(Modifier.size(224.dp).graphicsLayer { scaleX = scale; scaleY = scale }
            .background(Brush.radialGradient(listOf(accent.copy(alpha = .16f), accent.copy(alpha = 0f))), CircleShape))
        Box(Modifier.size(192.dp).border(1.dp, accent.copy(alpha = .16f), CircleShape))
        Box(Modifier.size(152.dp).background(MaterialTheme.colorScheme.surface.copy(alpha = .9f), CircleShape)
            .border(1.dp, accent.copy(alpha = .24f), CircleShape), contentAlignment = Alignment.Center) {
            RememberMeBrand(size = 96.dp)
        }
    }
}

@Composable private fun VoiceControl(label: String, icon: ImageVector, enabled: Boolean, modifier: Modifier, action: () -> Unit, end: Boolean = false) {
    Column(modifier.clip(RoundedCornerShape(20.dp)).clickable(enabled = enabled, role = Role.Button, onClick = action).padding(vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(Modifier.size(60.dp).background(if (end) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surfaceContainerHigh, CircleShape),
            contentAlignment = Alignment.Center) {
            Icon(icon, null, Modifier.size(26.dp), tint = (if (end) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onSurface).copy(alpha = if(enabled) 1f else .38f))
        }
        Text(label, style = MaterialTheme.typography.labelLarge, textAlign = TextAlign.Center)
    }
}

package me.remember.app.integration

import android.animation.ValueAnimator
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import me.remember.app.R
import me.remember.app.core.designsystem.LocalSimpleMode
import me.remember.app.hardware.NearbyRecorder
import org.json.JSONObject
import kotlin.math.roundToInt

/** Equal completed checkpoints, not an estimate of model runtime or remaining time. */
internal data class CaptureStageProgress(val complete: Int, val total: Int) {
    val percent: Int get() = (100f * complete / total).roundToInt()
}

internal fun captureStageProgress(status: String, reviewed: Boolean): CaptureStageProgress? = when {
    // The review boundary starts a new workflow: saved text -> extraction -> modeling.
    reviewed && status == "ready" -> CaptureStageProgress(3, 3)
    reviewed && status == "modeling" -> CaptureStageProgress(2, 3)
    reviewed && status in setOf("uploaded", "transcribing", "extracting") -> CaptureStageProgress(1, 3)
    !reviewed && status in setOf("extracting", "modeling", "ready") -> CaptureStageProgress(2, 2)
    !reviewed && status in setOf("uploaded", "transcribing") -> CaptureStageProgress(1, 2)
    else -> null // Unknown/failure is never presented as success.
}

/** Smooth only between observed values. No timed creep, shimmer or looping stripe. */
@Composable internal fun RecorderProgress(percent: Int?, flow: Boolean = false) {
    if (percent == null) return
    val target = percent.coerceIn(0, 100) / 100f
    val progress by animateFloatAsState(target, tween(900, easing = FastOutSlowInEasing), label = "observed-progress")
    val displayed = (progress.coerceAtMost(target) * 100).roundToInt()
    val ink = MaterialTheme.colorScheme.primary
    val track = MaterialTheme.colorScheme.onSurface.copy(alpha = .12f)
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Canvas(Modifier.weight(1f).height(7.dp).semantics { progressBarRangeInfo = ProgressBarRangeInfo(target, 0f..1f) }) {
            drawRoundRect(track, cornerRadius = CornerRadius(size.height / 2))
            if (progress > 0) drawRoundRect(ink, size = Size(size.width * progress.coerceIn(0f, target), size.height), cornerRadius = CornerRadius(size.height / 2))
        }
        Text("${if (flow) "流程 " else ""}$displayed%", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable internal fun RecorderDeviceDialog(close: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    val maxHeight = LocalConfiguration.current.screenHeightDp.dp * .88f
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.padding(16.dp).widthIn(max = 480.dp).fillMaxWidth().heightIn(max = maxHeight),
            shape = RoundedCornerShape(32.dp), tonalElevation = 4.dp) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("录音豆", Modifier.weight(1f), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    TextButton(onClick = close) { Text("关闭") }
                }
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
            }
        }
    }
}

@Composable internal fun RecorderProductHero(searching: Boolean = false, compact: Boolean = false) {
    val simple = LocalSimpleMode.current
    val animate = !simple && ValueAnimator.areAnimatorsEnabled()
    val float: () -> Float = if (animate) {
        val transition = rememberInfiniteTransition(label = "recorder-float")
        val pose = transition.animateFloat(-1f, 1f,
            infiniteRepeatable(tween(2800, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "product-pose")
        val readPose: () -> Float = { pose.value }
        readPose
    } else { { 0f } }
    val sweep = if (searching && animate) {
        val transition = rememberInfiniteTransition(label = "nearby-scan")
        val angle = transition.animateFloat(0f, 360f, infiniteRepeatable(tween(5000, easing = LinearEasing)), label = "scan-angle")
        val read: () -> Float = { angle.value }
        read
    } else { { 0f } }
    val ink = MaterialTheme.colorScheme.primary
    val stage = MaterialTheme.colorScheme.primaryContainer
    val base = MaterialTheme.colorScheme.surface
    // A transparent product cutout on the same green palette as the app.
    // The subtle GPU transforms are decorative, independent of device telemetry.
    Surface(Modifier.fillMaxWidth().testTag("recorder-product-hero"), shape = RoundedCornerShape(24.dp), color = base) {
        Box(Modifier.fillMaxWidth().height(if (compact) 112.dp else 216.dp)
            .background(Brush.radialGradient(listOf(stage.copy(alpha = .9f), base))), contentAlignment = Alignment.Center) {
            Canvas(Modifier.fillMaxSize()) {
                val radius = size.minDimension * .43f
                if (searching) {
                    drawCircle(ink.copy(alpha = .15f), radius, style = Stroke(1.dp.toPx()))
                    drawCircle(ink.copy(alpha = .08f), radius * .74f, style = Stroke(1.dp.toPx()))
                    rotate(sweep()) {
                        drawCircle(Brush.sweepGradient(listOf(Color.Transparent, ink.copy(alpha = .20f), Color.Transparent)), radius)
                    }
                } else {
                    drawOval(Color.Black.copy(alpha = .10f), topLeft = Offset(center.x - 62.dp.toPx(), size.height * .88f),
                        size = Size(124.dp.toPx(), 10.dp.toPx()))
                }
            }
            Image(painterResource(R.drawable.soundcore_work_cutout), "soundcore Work 录音豆与充电盒",
                Modifier.padding(12.dp).height(if (compact) 100.dp else if (searching) 134.dp else 184.dp).graphicsLayer {
                    if (animate) {
                        translationY = float() * 4.dp.toPx()
                        rotationY = float() * 5f
                        rotationZ = float() * 1.5f
                        cameraDistance = 16 * density
                    }
                }, contentScale = ContentScale.Fit)
        }
    }
}

@Composable internal fun NearbyRecorderCard(device: NearbyRecorder, enabled: Boolean, connect: () -> Unit) {
    Surface(onClick = connect, enabled = enabled, shape = RoundedCornerShape(22.dp),
        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = .65f)) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Image(painterResource(R.drawable.soundcore_work_cutout), null, Modifier.size(64.dp), contentScale = ContentScale.Fit)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(device.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                // The SDK scan identifier is not a verified serial number.
                Text("标识 · ${device.mac.takeLast(5)}", style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.Outlined.ChevronRight, null, Modifier.size(20.dp))
        }
    }
}

@Composable internal fun RecorderMenuRow(label: String, icon: ImageVector, expanded: Boolean = false,
    enabled: Boolean = true, onClick: () -> Unit) {
    Surface(onClick = onClick, enabled = enabled, shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.onSurface.copy(alpha = .04f)) {
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(icon, null, Modifier.size(22.dp), tint = MaterialTheme.colorScheme.primary)
            Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
            Icon(if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ChevronRight, null, Modifier.size(20.dp))
        }
    }
}

@Composable internal fun CompletedMemoryCard(story: JSONObject, open: () -> Unit) {
    val memories = story.rows("memories")
    Surface(onClick = open, shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = .96f)) {
        Column(Modifier.fillMaxWidth().padding(24.dp).testTag("completed-memory-card"), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Outlined.CheckCircle, null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
                Text(if (memories.isEmpty()) "录音已保存" else "已加入记忆", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary)
            }
            // One faithful excerpt. The complete source and other memories stay in detail.
            Text(memories.firstOrNull()?.text("content") ?: "这段暂未提取出记忆。",
                style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (story.optJSONObject("cumulative_analysis")?.text("status") in setOf("failed", "authorization_required"))
                Text("累计分析暂未完成", style = MaterialTheme.typography.bodyLarge)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(if (memories.isEmpty()) "查看录音" else "查看这条记忆", Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                Icon(Icons.Outlined.ArrowForward, null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

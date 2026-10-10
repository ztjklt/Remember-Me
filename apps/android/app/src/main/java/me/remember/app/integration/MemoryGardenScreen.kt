package me.remember.app.integration

import android.animation.ValueAnimator
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import me.remember.app.core.designsystem.RememberMeBrand
import kotlin.math.cos
import kotlin.math.sin

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MemoryGardenScreen(state: NativeState, model: NativeWorkbenchModel, reduceMotion: Boolean,
    scroll: ScrollState, openSource: (String) -> Unit, openPeople: () -> Unit, openPending: () -> Unit) {
    val clusters = remember(state.stories, state.narrative) { projectGarden(state.stories, state.narrative) }
    var selected by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var selectedPetal by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var query by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var facet by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var listMode by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
    var page by rememberSaveable(state.actor, state.subject, selected) { mutableIntStateOf(0) }
    var rootPosition by rememberSaveable(state.actor, state.subject) { mutableIntStateOf(0) }
    LaunchedEffect(selected) { withFrameNanos { }; scroll.scrollTo(if(selected == null) rootPosition else 0) }
    fun choose(id: String) { rootPosition = scroll.value; selected = id }
    val cluster = clusters.firstOrNull { it.id == selected }
    val petal = cluster?.petals?.firstOrNull { it.id == selectedPetal }
    val motion = if(reduceMotion || !ValueAnimator.areAnimatorsEnabled() || (selected != null && cluster == null)) 0 else 220
    LaunchedEffect(clusters.map { it.id }, cluster?.petals?.map { it.id }) {
        if(selected != null && cluster == null) { selected = null; selectedPetal = null }
        if(selectedPetal != null && petal == null) selectedPetal = null
        if(cluster != null) page = page.coerceAtMost((cluster.petals.size - 1).coerceAtLeast(0) / 5)
    }
    BackHandler(selected != null && petal == null) { selected = null }
    Text("记忆花田", style = MaterialTheme.typography.headlineMedium)
    Text("从一段故事，走近一个人。", style = MaterialTheme.typography.bodyMedium)
    AnimatedContent(cluster, transitionSpec = { fadeIn(tween(motion)) togetherWith fadeOut(tween(motion)) },
        label = "garden-story", contentKey = { it?.id }) { current ->
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if(current == null) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(!listMode, { listMode = false }, label = { Text("花田") }, leadingIcon = { Icon(Icons.Outlined.LocalFlorist, null) })
                    FilterChip(listMode, { listMode = true }, label = { Text("列表") }, leadingIcon = { Icon(Icons.Outlined.ViewList, null) })
                    TextButton(onClick = openPeople) { Text("了解这个人") }
                }
                OutlinedTextField(query, { query = it }, label = { Text("找故事、人物或一句话") },
                    leadingIcon = { Icon(Icons.Outlined.Search, null) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if(state.narrative.rows("facets").isNotEmpty()) {
                    var filters by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
                    TextButton(onClick = { filters = !filters }) { Text(if(filters) "收起内容侧面" else "按记忆侧面筛选") }
                    if(filters) {
                        state.narrative.rows("facets").chunked(2).forEach { pair -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            pair.forEach { f -> FilterChip(facet == f.text("id"), { facet = if(facet == f.text("id")) "" else f.text("id") }, label = { Text(f.text("title")) }) }
                        } }
                        if(facet.isNotBlank()) Text("尚未归组的记录没有侧面标签，可以清除筛选后查看。", style = MaterialTheme.typography.bodySmall)
                    }
                }
                val visible = clusters.filter { (facet.isBlank() || facet in it.facets) && (query.isBlank() ||
                    (it.title + " " + it.petals.joinToString(" ") { p -> p.content }).contains(query, true)) }
                if(visible.isEmpty()) {
                    Surface(shape = RoundedCornerShape(24.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = .88f)) {
                        Column(Modifier.fillMaxWidth().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            RememberMeBrand(size = 64.dp)
                            Text(if(clusters.isEmpty()) "故事会在这里慢慢留下" else "没有找到匹配的故事", style = MaterialTheme.typography.titleMedium)
                            Text(if(clusters.isEmpty()) "完成文字核对与整理后，真实记忆会出现在花田。" else "试试别的词，或清除内容侧面筛选。")
                            if(query.isNotBlank() || facet.isNotBlank()) TextButton(onClick = { query = ""; facet = "" }) { Text("清除筛选") }
                        }
                    }
                }
                if(listMode) visible.forEach { c -> GardenListItem(c) { choose(c.id) } }
                else visible.chunked(2).forEach { row -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { c -> GardenFlowerCard(c, Modifier.weight(1f)) { choose(c.id) } }
                    if(row.size == 1) Spacer(Modifier.weight(1f))
                } }
                if(state.owner) {
                    val pending = state.stories.count { it.text("status") != "ready" || it.optBoolean("waiting_for_review") }
                    TextButton(onClick = openPending) { Text("待处理录音 $pending 段 · 查看核对与失败原因") }
                }
                Text("花朵代表可查阅的内容，不表示人格准确度。", style = MaterialTheme.typography.bodySmall)
            } else {
                TextButton(onClick = { selected = null }) { Icon(Icons.Outlined.ArrowBack, null); Spacer(Modifier.width(8.dp)); Text("返回花田") }
                Text(current.title, style = MaterialTheme.typography.titleLarge)
                Text(if(current.organized) "本人核对的故事 · ${current.episodeIds.size} 段来源" else "尚未归组的记录 · 已完成记忆整理", style = MaterialTheme.typography.bodySmall)
                Text(if(current.petals.isEmpty()) "尚未提取到记忆。原音仍在，可以查看来源或在录音页重试整理。" else "点一片花瓣，读其中的记忆。", style = MaterialTheme.typography.bodyMedium)
                val pages = current.petals.chunked(5)
                val shown = pages.getOrElse(page) { pages.firstOrNull().orEmpty() }
                if(shown.isNotEmpty()) GardenPetals(shown) { selectedPetal = it.id }
                if(pages.size > 1) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    TextButton(onClick = { page-- }, enabled = page > 0) { Text("上一组") }
                    Text("${page + 1} / ${pages.size} 组", Modifier.padding(top = 12.dp))
                    TextButton(onClick = { page++ }, enabled = page + 1 < pages.size) { Text("下一组") }
                }
                Text("也可以直接选择内容", style = MaterialTheme.typography.titleMedium)
                shown.forEach { p -> Surface(onClick = { selectedPetal = p.id }, shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.surface.copy(alpha = .9f)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp)) { Text(p.title); Text(p.sourceLabel, style = MaterialTheme.typography.bodySmall) }
                } }
                current.episodeIds.forEach { id -> TextButton(onClick = { openSource(id) }) { Text("查看来源 · ${state.stories.firstOrNull { it.text("episode_id") == id }?.let { recordingDate(it.text("recorded_at")) }.orEmpty()}") } }
            }
        }
    }
    if(petal != null) GardenPetalReader(petal, state, model) { selectedPetal = null }
}

@Composable private fun GardenListItem(cluster: GardenCluster, select: () -> Unit) {
    Surface(onClick = select, shape = RoundedCornerShape(20.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = .9f)) {
        Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            RememberMeBrand(size = 44.dp)
            Column(Modifier.weight(1f)) { Text(cluster.title, style = MaterialTheme.typography.titleMedium)
                Text("${cluster.petals.size} 个内容入口 · ${if(cluster.organized) "已组织故事" else "尚未归组"}", style = MaterialTheme.typography.bodySmall) }
            Icon(Icons.Outlined.ChevronRight, null)
        }
    }
}

@Composable private fun GardenFlowerCard(cluster: GardenCluster, modifier: Modifier, select: () -> Unit) {
    Surface(onClick = select, modifier = modifier.testTag("garden-cluster-${cluster.id}"), shape = RoundedCornerShape(26.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = .62f), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f))) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            BotanicalBloom(Modifier.fillMaxWidth().height(134.dp))
            Text(cluster.title, style = MaterialTheme.typography.titleMedium, maxLines = 3, overflow = TextOverflow.Ellipsis)
            Text("${cluster.petals.size} 个内容入口", style = MaterialTheme.typography.bodySmall)
            Text(if(cluster.organized) "已组织的故事" else "尚未归组", style = MaterialTheme.typography.labelSmall)
        }
    }
}

/** A quiet botanical illustration. Its five decorative lobes never imply five facts. */
@Composable private fun BotanicalBloom(modifier: Modifier) {
    val stem = MaterialTheme.colorScheme.primary
    val blue = Color(0xFF779DA9)
    Canvas(modifier) {
        val center = Offset(size.width * .5f, size.height * .36f)
        val radius = size.minDimension * .17f
        val stalk = Path().apply { moveTo(center.x, center.y); cubicTo(center.x - radius, size.height * .62f, center.x + radius, size.height * .72f, center.x - radius * .3f, size.height * .94f) }
        drawPath(stalk, stem.copy(alpha = .8f), style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.3.dp.toPx()))
        val leaf = Path().apply { moveTo(center.x, size.height * .73f); quadraticTo(center.x + radius * 2, size.height * .58f, center.x + radius * 1.65f, size.height * .84f); quadraticTo(center.x + radius * .5f, size.height * .88f, center.x, size.height * .73f) }
        drawPath(leaf, Brush.linearGradient(listOf(stem.copy(alpha = .6f), stem.copy(alpha = .18f))))
        repeat(5) { index ->
            val angle = (index * 72.0 - 90) * Math.PI / 180
            val petal = center + Offset(cos(angle).toFloat() * radius, sin(angle).toFloat() * radius)
            drawCircle(blue.copy(alpha = .09f), radius * 1.05f, petal + Offset(0f, 3.dp.toPx()))
            drawCircle(Brush.radialGradient(listOf(Color(0xFFDAEAF0), blue.copy(alpha = .85f)), petal, radius), radius, petal)
        }
        drawCircle(stem.copy(alpha = .1f), radius * .45f, center + Offset(0f, 2.dp.toPx()))
        drawCircle(Color(0xFFE5CA82), radius * .36f, center)
        drawCircle(Color(0xFFF9EFCB), radius * .12f, center)
    }
}

@Composable private fun GardenPetals(petals: List<GardenPetal>, select: (GardenPetal) -> Unit) {
    if(LocalDensity.current.fontScale >= 1.5f) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { petals.forEach { p ->
            Button(onClick = { select(p) }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text(p.title) }
        } }
        return
    }
    BoxWithConstraints(Modifier.fillMaxWidth().height(330.dp), contentAlignment = Alignment.Center) {
        BotanicalBloom(Modifier.width(135.dp).height(160.dp))
        val radiusX = maxWidth * .29f
        petals.forEachIndexed { index, p ->
            val angle = (index * 360.0 / petals.size.coerceAtLeast(1) - 90) * Math.PI / 180
            Surface(onClick = { select(p) }, modifier = Modifier.offset(x = radiusX * cos(angle).toFloat(), y = 105.dp * sin(angle).toFloat()).width(100.dp).heightIn(min = 72.dp),
                shape = RoundedCornerShape(38.dp), color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = .95f),
                shadowElevation = 4.dp, border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .15f))) {
                Column(Modifier.padding(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("${index + 1}", style = MaterialTheme.typography.labelSmall)
                    Text(p.title, style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

@Composable private fun GardenPetalReader(petal: GardenPetal, state: NativeState, model: NativeWorkbenchModel, close: () -> Unit) {
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().fillMaxHeight(.93f).padding(12.dp), shape = RoundedCornerShape(24.dp), color = MaterialTheme.colorScheme.surface) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("一片记忆", style = MaterialTheme.typography.titleLarge)
                    TextButton(onClick = close) { Text("返回花朵") }
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(petal.content, style = MaterialTheme.typography.bodyLarge)
                    Text(petal.sourceLabel, style = MaterialTheme.typography.bodySmall)
                    HorizontalDivider()
                    Text("它的来处", style = MaterialTheme.typography.titleMedium)
                    petal.evidence.forEach { e -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(e.excerpt, style = MaterialTheme.typography.bodyLarge)
                        Text("${if(e.sourceType == "CALIBRATION") "本人书面补充 / 修订依据" else "核对文字依据"} · ${recordingDate(state.stories.firstOrNull { it.text("episode_id") == e.episodeId }?.text("recorded_at").orEmpty())}", style = MaterialTheme.typography.bodySmall)
                    } }
                }
                if(state.player.episode in petal.episodeIds) {
                    Text("${state.player.position / 1000} / ${state.player.duration / 1000} 秒 · 完整原音", style = MaterialTheme.typography.bodySmall)
                    Slider(state.player.position.toFloat(), { model.seekSource(it.toLong()) }, enabled = !state.player.preparing,
                        valueRange = 0f..state.player.duration.coerceAtLeast(1).toFloat())
                    TextButton(onClick = { if(state.player.playing) model.pauseSource() else model.resumeSource() }, enabled = !state.player.preparing) { Text(if(state.player.playing) "暂停" else "继续播放") }
                }
                petal.episodeIds.forEach { id -> Button(onClick = { model.playSource(id) }, enabled = !state.busy && !state.recording,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Icon(Icons.Outlined.PlayArrow, null); Spacer(Modifier.width(8.dp)); Text("听完整原音 · ${recordingDate(state.stories.firstOrNull { it.text("episode_id") == id }?.text("recorded_at").orEmpty())}", maxLines = 2) } }
                Text(if(petal.evidence.any { it.sourceType == "CALIBRATION" }) "书面补充不在原音中；这里播放来源故事的完整原音。" else "没有可靠时间对齐时，播放整段原音。", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

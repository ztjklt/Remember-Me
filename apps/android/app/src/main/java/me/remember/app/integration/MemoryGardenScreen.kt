package me.remember.app.integration

import android.animation.ValueAnimator
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
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
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import me.remember.app.core.designsystem.RememberMeBrand
import me.remember.app.core.designsystem.NatureScene
import kotlinx.coroutines.delay

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MemoryGardenScreen(state: NativeState, model: NativeWorkbenchModel, appearance: AppearanceChoice, updateAppearance: (AppearanceChoice) -> Unit,
    scroll: ScrollState, openSource: (String) -> Unit, openPeople: () -> Unit, openPending: () -> Unit,
    onStoryOpenChanged: (Boolean) -> Unit = {}) {
    val clusters = remember(state.stories, state.narrative) { projectGarden(state.stories, state.narrative) }
    var selected by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var selectedPetal by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var query by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var facet by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var listMode by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
    var searchOpen by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
    val scene = appearance.scene.scene ?: NatureScene.Meadow
    var page by rememberSaveable(state.actor, state.subject, selected) { mutableIntStateOf(0) }
    var rootPosition by rememberSaveable(state.actor, state.subject) { mutableIntStateOf(0) }
    var returnTo by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    LaunchedEffect(selected) { onStoryOpenChanged(selected != null) }
    LaunchedEffect(selected) { withFrameNanos { }; scroll.scrollTo(if(selected == null) rootPosition else 0) }
    fun choose(id: String) { rootPosition = scroll.value; selected = id }
    fun returnGarden() { returnTo = selected; selected = null }
    val cluster = clusters.firstOrNull { it.id == selected }
    val petal = cluster?.petals?.firstOrNull { it.id == selectedPetal }
    val motion = if(appearance.reduceMotion || !ValueAnimator.areAnimatorsEnabled() || (selected != null && cluster == null)) 0 else 220
    LaunchedEffect(clusters.map { it.id }, cluster?.petals?.map { it.id }) {
        if(selected != null && cluster == null) { selected = null; selectedPetal = null }
        if(selectedPetal != null && petal == null) selectedPetal = null
        if(cluster != null) page = page.coerceAtMost((cluster.petals.size - 1).coerceAtLeast(0) / 5)
    }
    BackHandler(selected != null && petal == null) { returnGarden() }
    if(cluster == null) {
        Text("A GARDEN OF MOMENTS", fontSize = 10.sp, letterSpacing = 2.sp, color = gardenMuted,
            modifier = Modifier.padding(top = 12.dp))
        Text("日子慢慢过去，\n有些话，留下来。", fontFamily = FontFamily.Serif, fontSize = 28.sp, lineHeight = 40.sp, color = gardenInk)
        Text("一朵花，一段还能听得见的回忆。", fontSize = 14.sp, color = gardenMuted)
    }
    AnimatedContent(cluster, transitionSpec = { fadeIn(tween(motion)) togetherWith fadeOut(tween(motion)) },
        label = "garden-story", contentKey = { it?.id }) { current ->
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if(current == null) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val chips = FilterChipDefaults.filterChipColors(containerColor = gardenGlass.copy(alpha = .55f),
                        labelColor = gardenInk, iconColor = gardenInk, selectedContainerColor = gardenGlass.copy(alpha = .94f),
                        selectedLabelColor = gardenInk, selectedLeadingIconColor = gardenInk)
                    FilterChip(!listMode, { listMode = false }, label = { Text("花田") }, leadingIcon = { Icon(Icons.Outlined.LocalFlorist, null) }, colors = chips)
                    FilterChip(listMode, { listMode = true }, label = { Text("列表") }, leadingIcon = { Icon(Icons.Outlined.ViewList, null) }, colors = chips)
                    TextButton(onClick = { searchOpen = !searchOpen }) { Text(if(searchOpen) "收起查找" else "查找", color = gardenInk) }
                }
                if(searchOpen || query.isNotBlank()) OutlinedTextField(query, { query = it }, label = { Text("找故事、人物或一句话") },
                    leadingIcon = { Icon(Icons.Outlined.Search, null) }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = gardenGlass.copy(alpha = .75f),
                        unfocusedContainerColor = gardenGlass.copy(alpha = .65f), focusedTextColor = gardenInk,
                        unfocusedTextColor = gardenInk, focusedLabelColor = gardenMuted, unfocusedLabelColor = gardenMuted,
                        focusedBorderColor = gardenMuted, unfocusedBorderColor = gardenMuted.copy(alpha = .45f)))
                val visible = clusters.filter { (facet.isBlank() || facet in it.facets) && (query.isBlank() ||
                    (it.title + " " + it.petals.joinToString(" ") { p -> p.content }).contains(query, true)) }
                if(visible.isEmpty()) {
                    Surface(shape = RoundedCornerShape(24.dp), color = gardenGlass.copy(alpha = .88f), contentColor = gardenInk) {
                        Column(Modifier.fillMaxWidth().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            RememberMeBrand(size = 64.dp)
                            Text(if(clusters.isEmpty()) "故事会在这里慢慢留下" else "没有找到匹配的故事", style = MaterialTheme.typography.titleMedium)
                            Text(if(clusters.isEmpty()) "完成文字核对与整理后，真实记忆会出现在花田。" else "试试别的词，或清除内容侧面筛选。")
                            if(query.isNotBlank() || facet.isNotBlank()) TextButton(onClick = { query = ""; facet = "" }) { Text("清除筛选") }
                        }
                    }
                }
                if(listMode) visible.forEach { c -> GardenListItem(c, returnTo == c.id, { returnTo = null }) { choose(c.id) } }
                else visible.chunked(2).forEach { row -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    if(row.size == 1) ReviewedGardenFlower(row.single(), Modifier.fillMaxWidth().padding(horizontal = 40.dp),
                        returnIntoView = returnTo == row.single().id, onReturned = { returnTo = null }) { choose(row.single().id) }
                    else row.forEachIndexed { index, c -> ReviewedGardenFlower(c, Modifier.weight(1f).padding(top = if(index == 1) 30.dp else 0.dp), side = index == 1,
                        returnIntoView = returnTo == c.id, onReturned = { returnTo = null }) { choose(c.id) } }
                } }
                TextButton(onClick = openPeople) { Text("了解故事里的人", color = gardenInk) }
                if(state.narrative.rows("facets").isNotEmpty()) {
                    var filters by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
                    TextButton(onClick = { filters = !filters }) { Text(if(filters) "收起内容侧面" else "按记忆侧面筛选", color = gardenMuted, fontSize = 12.sp) }
                    if(filters) {
                        state.narrative.rows("facets").chunked(2).forEach { pair -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            pair.forEach { f -> FilterChip(facet == f.text("id"), { facet = if(facet == f.text("id")) "" else f.text("id") }, label = { Text(f.text("title")) }) }
                        } }
                        if(facet.isNotBlank()) Text("尚未归组的记录没有侧面标签，可以清除筛选后查看。", color = gardenMuted, style = MaterialTheme.typography.bodySmall)
                    }
                }
                if(state.owner) {
                    val pending = state.stories.count { it.text("status") != "ready" || it.optBoolean("waiting_for_review") }
                    TextButton(onClick = openPending) { Text("待处理录音 $pending 段 · 查看核对与失败原因", color = gardenMuted, fontSize = 12.sp) }
                }
                Text("花朵代表可查阅的内容，不表示人格准确度。", color = gardenMuted, fontSize = 11.sp)
            } else {
                TextButton(onClick = { returnGarden() }) { Icon(Icons.Outlined.ArrowBack, null, tint = gardenInk); Spacer(Modifier.width(8.dp)); Text("返回花田", color = gardenInk) }
                Text(current.title, fontFamily = FontFamily.Serif, fontSize = 24.sp, lineHeight = 33.sp, color = gardenInk)
                Text(if(current.organized) "本人核对的故事 · ${current.episodeIds.size} 段来源" else "尚未归组的记录 · 已完成记忆整理", fontSize = 12.sp, color = gardenMuted)
                Text(if(current.petals.isEmpty()) "尚未提取到记忆。原音仍在，可以查看来源或在录音页重试整理。" else "一片花瓣，一段值得停留的瞬间。", fontSize = 14.sp, color = gardenMuted)
                val pages = current.petals.chunked(5)
                val shown = pages.getOrElse(page) { pages.firstOrNull().orEmpty() }
                if(shown.isNotEmpty()) ReviewedGardenPetals(shown, scene) { selectedPetal = it.id }
                if(pages.size > 1) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    TextButton(onClick = { page-- }, enabled = page > 0) { Text("上一组") }
                    Text("${page + 1} / ${pages.size} 组", Modifier.padding(top = 12.dp))
                    TextButton(onClick = { page++ }, enabled = page + 1 < pages.size) { Text("下一组") }
                }
                var directList by rememberSaveable(current.id) { mutableStateOf(false) }
                TextButton(onClick = { directList = !directList }) { Text(if(directList) "收起内容列表" else "用列表阅读这些记忆", color = gardenInk) }
                if(directList) shown.forEach { p -> Surface(onClick = { selectedPetal = p.id }, shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.surface.copy(alpha = .9f)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp)) { Text(p.title); Text(p.sourceLabel, style = MaterialTheme.typography.bodySmall) }
                } }
                current.episodeIds.forEach { id -> TextButton(onClick = { openSource(id) }) { Text("查看来源 · ${state.stories.firstOrNull { it.text("episode_id") == id }?.let { recordingDate(it.text("recorded_at")) }.orEmpty()}", color = gardenMuted) } }
            }
            TextButton(onClick = {
                val places = listOf(SceneChoice.MEADOW, SceneChoice.LAKE, SceneChoice.FOREST, SceneChoice.COAST, SceneChoice.NIGHT)
                val next = places[(places.indexOf(appearance.scene).coerceAtLeast(0) + 1) % places.size]
                updateAppearance(appearance.copy(scene = next))
            }) { Text("换一处花园 · ${if(appearance.scene == SceneChoice.AUTO) "草地" else appearance.scene.title}", color = gardenMuted, fontSize = 12.sp) }
        }
    }
    if(petal != null) GardenPetalReader(petal, state, model) { selectedPetal = null }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable private fun GardenListItem(cluster: GardenCluster, returnIntoView: Boolean, onReturned: () -> Unit, select: () -> Unit) {
    val row = remember { BringIntoViewRequester() }
    LaunchedEffect(returnIntoView) { if(returnIntoView) { delay(250); row.bringIntoView(); onReturned() } }
    Surface(onClick = select, modifier = Modifier.bringIntoViewRequester(row), shape = RoundedCornerShape(20.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = .9f)) {
        Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            RememberMeBrand(size = 44.dp)
            Column(Modifier.weight(1f)) { Text(cluster.title, style = MaterialTheme.typography.titleMedium)
                Text("${cluster.petals.size} 个内容入口 · ${if(cluster.organized) "已组织故事" else "尚未归组"}", style = MaterialTheme.typography.bodySmall) }
            Icon(Icons.Outlined.ChevronRight, null)
        }
    }
}

@Composable private fun GardenPetalReader(petal: GardenPetal, state: NativeState, model: NativeWorkbenchModel, close: () -> Unit) {
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().fillMaxHeight(.93f).padding(12.dp), shape = RoundedCornerShape(24.dp), color = if(MaterialTheme.colorScheme.background.luminance() < .5f) Color(0xFF243B32) else Color(0xFFE9EDDA), contentColor = MaterialTheme.colorScheme.onSurface) {
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

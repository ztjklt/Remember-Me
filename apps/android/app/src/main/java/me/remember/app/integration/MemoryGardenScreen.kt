package me.remember.app.integration

import android.animation.ValueAnimator
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
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
    ask: (String) -> Unit = {}, onStoryOpenChanged: (Boolean) -> Unit = {}) {
    val clusters = remember(state.stories, state.narrative) { projectGarden(state.stories, state.narrative) }
    var selected by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var selectedPetal by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var query by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var facet by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var listMode by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
    var searchOpen by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
    var showScenes by rememberSaveable { mutableStateOf(false) }
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
    val reduceMotion = appearance.reduceMotion || appearance.simpleMode
    val motion = if(reduceMotion || !ValueAnimator.areAnimatorsEnabled() || (selected != null && cluster == null)) 0 else 620
    LaunchedEffect(clusters.map { it.id }, cluster?.petals?.map { it.id }) {
        if(selected != null && cluster == null) { selected = null; selectedPetal = null }
        if(selectedPetal != null && petal == null) selectedPetal = null
        if(cluster != null) page = page.coerceAtMost((cluster.petals.size - 1).coerceAtLeast(0) / 5)
    }
    BackHandler(selected != null && petal == null) { returnGarden() }
    if(cluster == null) {
        Text("沿着花径，重温往事。",fontFamily=FontFamily.Serif,fontSize=24.sp,lineHeight=34.sp,color=gardenInk,
            modifier=Modifier.padding(top=8.dp))

    }
    AnimatedContent(cluster, transitionSpec = { (fadeIn(tween(motion)) + scaleIn(tween(motion),initialScale=if(targetState!=null) .78f else 1.08f)) togetherWith (fadeOut(tween(motion)) + scaleOut(tween(motion),targetScale=if(targetState!=null) 1.08f else .78f)) },
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
                    (it.title + " " + it.petals.joinToString(" ") { p -> p.content + " " + p.evidence.joinToString(" ") { e -> e.excerpt } }).contains(query.trim(), true)) }
                if(searchOpen && query.isNotBlank()) {
                    TextButton(onClick={model.search(query.trim())},enabled=!state.busy) {
                        Text(if(state.busy) "查找中…" else "查找相关内容",color=gardenInk)
                    }
                    TextButton(onClick={ask(query.trim())},enabled=!state.busy) { Text("问一问",color=gardenInk) }
                    if(visible.isNotEmpty()) Text("精准匹配",color=gardenMuted,style=MaterialTheme.typography.labelLarge)
                }
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
                else GardenMeadow(visible,"${state.actor}:${state.subject}",returnTo,{returnTo=null}) { choose(it) }
                if(searchOpen && query.isNotBlank() && state.searchQuery==query.trim()) {
                    Text("相关内容",color=gardenInk,style=MaterialTheme.typography.titleMedium)
                    if(state.search.isEmpty()) Text("暂未找到更多相关内容",color=gardenMuted)
                    state.search.forEach { hit ->
                        val sources=hit.rows("evidence").filter { e -> state.stories.any { story -> story.text("episode_id")==e.text("episode_id") && story.optBoolean("reviewed") && !story.optBoolean("unavailable") && story.text("status")=="ready" } }
                        if(sources.isNotEmpty()) Surface(shape=RoundedCornerShape(20.dp),color=gardenGlass.copy(alpha=.94f),contentColor=gardenInk) {
                            Column(Modifier.fillMaxWidth().padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                                Text(hit.text("statement"))
                                sources.forEach { evidence ->
                                    Text("“${evidence.text("excerpt")}”",style=MaterialTheme.typography.bodyMedium)
                                    TextButton(onClick={openSource(evidence.text("episode_id"))}) { Text("打开来源",color=gardenMuted) }
                                }
                            }
                        }
                    }
                }
                TextButton(onClick = openPeople) { Text("了解故事里的人", color = gardenInk) }
                if(state.narrative.rows("facets").isNotEmpty()) {
                    var filters by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
                    TextButton(onClick = { filters = !filters }) { Text(if(filters) "收起内容侧面" else "按记忆侧面筛选", color = gardenMuted, fontSize = 12.sp) }
                    if(filters) {
                        state.narrative.rows("facets").chunked(2).forEach { pair -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            pair.forEach { f -> FilterChip(facet == f.text("id"), { facet = if(facet == f.text("id")) "" else f.text("id") }, label = { Text(memorySideTitles[f.text("id")] ?: f.text("title")) }) }
                        } }
                    }
                }
                if(state.owner) {
                    val pending = state.stories.count { it.text("status") != "ready" || it.optBoolean("waiting_for_review") }
                    TextButton(onClick = openPending) { Text("待整理 · $pending 段", color = gardenMuted, fontSize = 12.sp) }
                }
            } else {
                TextButton(onClick = { returnGarden() }) { Icon(Icons.Outlined.ArrowBack, null, tint = gardenInk); Spacer(Modifier.width(8.dp)); Text("返回花田", color = gardenInk) }
                Text(current.title, fontFamily = FontFamily.Serif, fontSize = 24.sp, lineHeight = 33.sp, color = gardenInk)
                Text(if(current.organized) "已核对 · ${current.episodeIds.size} 段来源" else "系统整理", fontSize = 12.sp, color = gardenMuted)
                Text(if(current.petals.isEmpty()) "尚未提取到记忆。原音仍在，可以查看来源或在录音页重试整理。" else "一片花瓣，一段值得停留的瞬间。", fontSize = 14.sp, color = gardenMuted)
                val pages = current.petals.chunked(5)
                val shown = pages.getOrElse(page) { pages.firstOrNull().orEmpty() }
                if(shown.isNotEmpty()) ReviewedGardenPetals(shown, scene,
                    form=gardenBloom(current.id),reduceMotion=reduceMotion) { selectedPetal = it.id }
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
            TextButton(onClick = { showScenes = true }, modifier = Modifier.testTag("garden-change-scene")) {
                Text("换一处花园 · ${if(appearance.scene == SceneChoice.AUTO) "草地" else appearance.scene.title}", color = gardenMuted, fontSize = 12.sp) }
        }
    }
    if(petal != null) GardenPetalReader(petal, state, model) { selectedPetal = null }
    if(showScenes) GardenScenePicker(appearance.scene, { updateAppearance(appearance.copy(scene = it)) }, { showScenes = false })
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

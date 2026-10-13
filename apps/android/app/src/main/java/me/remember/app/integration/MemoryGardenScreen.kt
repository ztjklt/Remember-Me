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
    var facet by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var listMode by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
    var showScenes by rememberSaveable { mutableStateOf(false) }
    var presentationMenu by remember { mutableStateOf(false) }
    var filtersMenu by remember { mutableStateOf(false) }
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
    val motion = if(appearance.reduceMotion || !ValueAnimator.areAnimatorsEnabled() || (selected != null && cluster == null)) 0 else 620
    LaunchedEffect(clusters.map { it.id }, cluster?.petals?.map { it.id }) {
        if(selected != null && cluster == null) { selected = null; selectedPetal = null }
        if(selectedPetal != null && petal == null) selectedPetal = null
        if(cluster != null) page = page.coerceAtMost((cluster.petals.size - 1).coerceAtLeast(0) / 5)
    }
    BackHandler(selected != null && petal == null) { returnGarden() }
    AnimatedContent(cluster, transitionSpec = { (fadeIn(tween(motion)) + scaleIn(tween(motion),initialScale=if(targetState!=null) .78f else 1.08f)) togetherWith (fadeOut(tween(motion)) + scaleOut(tween(motion),targetScale=if(targetState!=null) 1.08f else .78f)) },
        label = "garden-story", contentKey = { it?.id }) { current ->
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if(current == null) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Spacer(Modifier.weight(1f))
                    Box {
                        TextButton(onClick = { presentationMenu = true }) {
                            Text("记忆花田", color = gardenInk)
                            Icon(Icons.Outlined.ExpandMore, contentDescription = "展开展示方式", tint = gardenInk)
                        }
                        DropdownMenu(expanded = presentationMenu, onDismissRequest = { presentationMenu = false }) {
                            DropdownMenuItem(text = { Text("列表") }, onClick = { listMode = true; presentationMenu = false })
                            DropdownMenuItem(text = { Text("花田") }, onClick = { listMode = false; presentationMenu = false })
                        }
                    }
                    Spacer(Modifier.weight(1f))
                }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { showScenes = true }, modifier = Modifier.testTag("garden-change-scene")) {
                        Text("换一处花园", color = gardenInk)
                    }
                    Spacer(Modifier.weight(1f))
                    Box {
                        IconButton(onClick = { filtersMenu = true }, modifier = Modifier.testTag("garden-filter")) {
                            Icon(Icons.Outlined.FilterList, contentDescription = "筛选", tint = gardenInk)
                        }
                        DropdownMenu(expanded = filtersMenu, onDismissRequest = { filtersMenu = false }) {
                            DropdownMenuItem(text = { Text("全部") }, onClick = { facet = ""; filtersMenu = false })
                            memorySideTitles.forEach { (id, title) ->
                                DropdownMenuItem(text = { Text(title) }, onClick = { facet = id; filtersMenu = false })
                            }
                        }
                    }
                }
                val visible = clusters.filter { facet.isBlank() || facet in it.facets }
                if(listMode) visible.forEach { c -> GardenListItem(c, returnTo == c.id, { returnTo = null }) { choose(c.id) } }
                else GardenMeadow(visible,"${state.actor}:${state.subject}",returnTo,{returnTo=null}) { choose(it) }
            } else {
                TextButton(onClick = { returnGarden() }) { Icon(Icons.Outlined.ArrowBack, null, tint = gardenInk); Spacer(Modifier.width(8.dp)); Text("返回花田", color = gardenInk) }
                Text(current.title, fontFamily = FontFamily.Serif, fontSize = 24.sp, lineHeight = 33.sp, color = gardenInk)
                Text(if(current.organized) "已核对 · ${current.episodeIds.size} 段来源" else "系统整理", fontSize = 12.sp, color = gardenMuted)
                Text(if(current.petals.isEmpty()) "尚未提取到记忆。原音仍在，可以查看来源或在录音页重试整理。" else "一片花瓣，一段值得停留的瞬间。", fontSize = 14.sp, color = gardenMuted)
                val pages = current.petals.chunked(5)
                val shown = pages.getOrElse(page) { pages.firstOrNull().orEmpty() }
                if(shown.isNotEmpty()) ReviewedGardenPetals(shown, scene,
                    form=gardenBloom(current.id),reduceMotion=appearance.reduceMotion) { selectedPetal = it.id }
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

package me.remember.app.integration

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import org.json.JSONObject

/** Only projects the current server-visible state; never grants access or confirms text. */
internal fun simpleListeningStories(stories: List<JSONObject>) = stories.filter {
    it.text("episode_id").isNotBlank() && it.text("status") == "ready" && it.optBoolean("reviewed") &&
        !it.optBoolean("waiting_for_review") && !it.optBoolean("unavailable")
}.distinctBy { it.text("episode_id") }

internal fun simplePendingCount(state: NativeState): Int {
    if(!state.owner) return 0
    val remote = state.stories.filter { !it.optBoolean("unavailable") &&
        (it.optBoolean("waiting_for_review") || it.text("status") != "ready") }.map { it.text("episode_id") }.toSet()
    return remote.size + state.local.count { !it.linked && (it.episode.isBlank() || it.episode !in remote) }
}

@Composable internal fun SimpleHome(state: NativeState, record: () -> Unit, listen: () -> Unit,
    pending: () -> Unit, ask: () -> Unit) {
    val ready = !state.busy && !state.recording
    Surface(shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.primaryContainer) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Icon(Icons.Outlined.LocalFlorist, null, Modifier.size(38.dp), tint = MaterialTheme.colorScheme.primary)
            Text(if(state.owner) "想说的时候，就讲一段" else "熟悉的声音，慢慢听", style = MaterialTheme.typography.headlineMedium)
            Text(if(state.owner) "一件往事，一句牵挂。" else "这里是分享给你的故事。", style = MaterialTheme.typography.bodyLarge)
            SimpleButton(if(state.owner) "讲一段故事" else "听故事", if(state.owner) Icons.Outlined.Mic else Icons.Outlined.Headphones,
                ready, primary = true, action = if(state.owner) record else listen)
        }
    }
    if(state.owner) SimpleButton("听我的故事", Icons.Outlined.Headphones, ready, action = listen)
    else SimpleButton("问一问", Icons.Outlined.ChatBubbleOutline, ready, action = ask)
    if(simplePendingCount(state) > 0) {
        SimpleButton("继续整理", Icons.Outlined.EditNote, ready, action = pending)
        Text("还有 ${simplePendingCount(state)} 段没整理完，可以稍后再来。", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable internal fun SimpleButton(title: String, icon: ImageVector, enabled: Boolean = true,
    primary: Boolean = false, modifier: Modifier = Modifier, action: () -> Unit) {
    val content: @Composable RowScope.() -> Unit = {
        Icon(icon, null, Modifier.size(28.dp)); Spacer(Modifier.width(12.dp))
        Text(title, Modifier.weight(1f), style = MaterialTheme.typography.labelLarge)
    }
    if(primary) Button(onClick = action, enabled = enabled, modifier = modifier.fillMaxWidth().heightIn(min = 64.dp),
        shape = RoundedCornerShape(20.dp), contentPadding = PaddingValues(18.dp), content = content)
    else OutlinedButton(onClick = action, enabled = enabled, modifier = modifier.fillMaxWidth().heightIn(min = 64.dp),
        shape = RoundedCornerShape(20.dp), contentPadding = PaddingValues(18.dp), content = content)
}

@Composable internal fun SimpleStories(state: NativeState, model: NativeWorkbenchModel, open: (String) -> Unit,
    garden: () -> Unit, people: () -> Unit, library: () -> Unit) {
    var query by rememberSaveable(state.actor, state.subject) { mutableStateOf("") }
    var finding by rememberSaveable(state.actor, state.subject) { mutableStateOf(false) }
    val clusters = projectGarden(state.stories, state.narrative)
    fun title(story: JSONObject): String = clusters.firstOrNull { story.text("episode_id") in it.episodeIds }?.title
        ?: "${recordingDate(story.text("recorded_at"))}的讲述"
    val available = simpleListeningStories(state.stories)
    // Search only current titles; don't resurrect invalidated text through a new full-transcript search.
    val matches = available.filter { query.isBlank() || title(it).contains(query.trim(), ignoreCase = true) }
    Text("听故事", style = MaterialTheme.typography.headlineMedium)
    SimpleButton("去花田看看", Icons.Outlined.LocalFlorist, action = garden)
    TextButton(onClick = { finding = !finding; if(!finding) query = "" }) {
        Icon(Icons.Outlined.Search, null); Spacer(Modifier.width(8.dp)); Text(if(finding) "收起查找" else "按标题找故事")
    }
    if(finding) OutlinedTextField(query, { query = it }, label = { Text("故事标题中的字") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    if(matches.isEmpty()) Text(if(query.isNotBlank()) "没有找到这个标题，换个词试试。" else if(state.owner) "整理完的故事会出现在这里。" else "这里还没有分享给你的故事。")
    matches.forEach { story ->
        val id = story.text("episode_id")
        Surface(shape = RoundedCornerShape(24.dp), color = MaterialTheme.colorScheme.surface) {
            Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(title(story), style = MaterialTheme.typography.titleLarge)
                Text(recordingDate(story.text("recorded_at")), style = MaterialTheme.typography.bodySmall)
                SimpleButton("听这段原音", Icons.Outlined.PlayArrow, !state.busy, primary = true,
                    modifier = Modifier.testTag("simple-play-$id")) { model.playSource(id) }
                TextButton(onClick = { open(id) }, enabled = !state.busy, modifier = Modifier.heightIn(min = 60.dp)) { Text("读故事与记忆") }
            }
        }
    }
    SimpleButton("了解这个人", Icons.Outlined.PersonOutline, action = people)
    SimpleButton("全部录音", Icons.Outlined.LibraryMusic, action = library)
}

@Composable internal fun SimpleSourcePlayer(state: NativeState, model: NativeWorkbenchModel) {
    var expanded by remember(state.actor, state.subject) { mutableStateOf(false) }
    if(state.player.episode.isNotBlank()) SimpleButton("播放控制", Icons.Outlined.Headphones) { expanded = true }
    if(expanded) NativeDialog(sourcePlaybackLabel(state.player), { expanded = false }) {
        val player = state.player
        if(player.episode.isBlank()) Text("播放已结束。") else {
            Text(if(player.preparing) "正在准备声音…" else if(player.playing) "正在播放${sourcePlaybackLabel(player)}" else "已暂停", style = MaterialTheme.typography.titleLarge)
            Text("${clock(player.position)} / ${clock(player.duration)}")
            SimpleButton(if(player.playing) "暂停" else "继续播放", if(player.playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,
                !player.preparing, primary = true) { if(player.playing) model.pauseSource() else model.resumeSource() }
            SimpleButton("从头再听", Icons.Outlined.Replay, !player.preparing) { model.seekSource(0); model.resumeSource() }
            SimpleButton("停止播放", Icons.Outlined.Stop) { model.stopSource() }
        }
    }
}

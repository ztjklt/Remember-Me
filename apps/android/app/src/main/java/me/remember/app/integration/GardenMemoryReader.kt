package me.remember.app.integration

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

@Composable internal fun GardenPetalReader(petal: GardenPetal, state: NativeState, model: NativeWorkbenchModel, close: () -> Unit) {
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        GardenMemoryReaderContent(petal, state, model::playSource, model::pauseSource, model::resumeSource, model::seekSource, close)
    }
}

/** The scrolling document owns all citations. One fixed transport serves the selected source,
 * so additional recordings cannot push the text and return action off a small screen. */
@Composable internal fun GardenMemoryReaderContent(petal: GardenPetal, state: NativeState, play: (String) -> Unit,
    pause: () -> Unit, resume: () -> Unit, seek: (Long) -> Unit, close: () -> Unit) {
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    val paper = if(dark) Color(0xFF233B32) else Color(0xFFE9EDDA)
    val ink = if(dark) gardenInk else Color(0xFF253C31)
    val quiet = if(dark) gardenMuted else Color(0xFF51664F)
    var source by rememberSaveable(petal.id) { mutableStateOf(state.player.episode.takeIf { it in petal.episodeIds } ?: petal.episodeIds.firstOrNull().orEmpty()) }
    var selecting by remember { mutableStateOf(false) }
    LaunchedEffect(petal.episodeIds) { if(source !in petal.episodeIds) source = petal.episodeIds.firstOrNull().orEmpty() }
    val active = source.isNotBlank() && state.player.episode == source
    fun date(id: String) = recordingDate(state.stories.firstOrNull { it.text("episode_id") == id }?.text("recorded_at").orEmpty())
    Surface(Modifier.fillMaxWidth().fillMaxHeight(.93f).padding(12.dp), shape = RoundedCornerShape(28.dp), color = paper, contentColor = ink) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("一片记忆", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                TextButton(onClick = close) { Text("返回花朵") }
            }
            Column(Modifier.weight(1f).testTag("garden-reader-document").verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(20.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    ReviewedGardenPlant(Modifier.size(52.dp), flowerOnly = true)
                    Text(petal.sourceLabel, color = quiet, style = MaterialTheme.typography.bodySmall)
                }
                Text(petal.content, fontSize = 20.sp, lineHeight = 32.sp)
                HorizontalDivider(color = quiet.copy(alpha = .22f))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.Outlined.FormatQuote, null, tint = quiet)
                    Text("它的来处", style = MaterialTheme.typography.titleMedium)
                    Text("${petal.evidence.size} 条依据", color = quiet, style = MaterialTheme.typography.bodySmall)
                }
                petal.evidence.forEachIndexed { index, evidence ->
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("${index + 1} · ${if(evidence.sourceType == "CALIBRATION") "本人书面补充 / 修订依据" else "核对文字依据"}", color = quiet, style = MaterialTheme.typography.labelLarge)
                        Surface(shape = RoundedCornerShape(topEnd = 20.dp, bottomEnd = 20.dp), color = quiet.copy(alpha = .07f)) {
                            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
                                Box(Modifier.width(3.dp).fillMaxHeight().background(quiet.copy(alpha = .50f)))
                                Text(evidence.excerpt, Modifier.padding(16.dp), fontSize = 17.sp, lineHeight = 28.sp, color = ink)
                            }
                        }
                        Text(date(evidence.episodeId), color = quiet, style = MaterialTheme.typography.bodySmall)
                    }
                }
                Text(if(petal.evidence.any { it.sourceType == "CALIBRATION" })
                    "书面补充不在原音中；下方可播放来源故事的完整原音。" else "依据来自核对文字。没有可靠时间对齐时，播放整段原音。",
                    color = quiet, style = MaterialTheme.typography.bodySmall)
                state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                Spacer(Modifier.height(4.dp))
            }
            HorizontalDivider(color = quiet.copy(alpha = .20f))
            if(source.isNotBlank()) {
                if(petal.episodeIds.size > 1) Box {
                    TextButton(onClick = { selecting = true }, modifier = Modifier.testTag("garden-source-selector")) {
                        Text("选择原音 · ${petal.episodeIds.indexOf(source) + 1} / ${petal.episodeIds.size}")
                        Icon(Icons.Outlined.ExpandMore, null)
                    }
                    DropdownMenu(selecting, { selecting = false }) {
                        petal.episodeIds.forEachIndexed { index, id -> DropdownMenuItem(
                            text = { Text("原音 ${index + 1} · ${date(id)}") },
                            onClick = { if(active && state.player.playing) pause(); source = id; selecting = false },
                            modifier = Modifier.testTag("garden-source-option-$index")) }
                    }
                } else Text(date(source), color = quiet, style = MaterialTheme.typography.bodySmall)
                if(active && !state.player.preparing) {
                    RememberAudioScrubber("${state.actor}:${state.subject}:$source",state.player.position,state.player.duration,
                        enabled=!state.recording,seek=seek,modifier=Modifier.testTag("garden-reader-seek"))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(gardenClock(state.player.position), style = MaterialTheme.typography.bodySmall)
                        Text("${gardenClock(state.player.duration)} · 完整原音", style = MaterialTheme.typography.bodySmall)
                    }
                }
                // Keep pause available while unrelated server refreshes run.
                // Starting a new download still waits for the current request.
                val loading = (!active && state.busy) || (active && state.player.preparing)
                val playing = active && state.player.playing
                Button(onClick = { if(!active) play(source) else if(playing) pause() else resume() },
                    enabled = !loading && !state.recording, shape = RoundedCornerShape(18.dp),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("garden-source-play")) {
                    if(loading) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    else Icon(if(playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow, null)
                    Spacer(Modifier.width(8.dp))
                    Text(if(loading) "正在准备原音…" else if(playing) "暂停" else if(active) "继续播放" else "听完整原音")
                }
            }
        }
    }
}

/** Keep the garden visible when listening; the source reader owns the detailed controls. */
@Composable internal fun GardenMiniPlayer(player: SourcePlayback, toggle: () -> Unit, seek: (Long) -> Unit, stop: () -> Unit) {
    Surface(shape = RoundedCornerShape(20.dp), color = gardenGlass.copy(alpha = .95f), contentColor = gardenInk) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                FilledIconButton(onClick=toggle,enabled=!player.preparing,modifier=Modifier.size(52.dp),
                    colors=IconButtonDefaults.filledIconButtonColors(containerColor=gardenInk,contentColor=gardenGlass)) {
                    if(player.preparing) CircularProgressIndicator(Modifier.size(22.dp),color=gardenMuted,strokeWidth=2.dp)
                    else Icon(if(player.playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow, if(player.playing) "暂停" else "继续播放")
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(if(player.preparing) "正在准备声音…" else if(player.playing) "正在听 · ${sourcePlaybackLabel(player)}" else "${sourcePlaybackLabel(player)}已暂停",style=MaterialTheme.typography.titleMedium)
                    Text("${gardenClock(player.position)} / ${gardenClock(player.duration)}",style=MaterialTheme.typography.bodySmall,color=gardenMuted)
                }
                IconButton(onClick = stop) { Icon(Icons.Outlined.Close, "停止播放") }
            }
            RememberAudioScrubber("${LocalInteractions.current.identity}:${player.episode}",player.position,player.duration,
                enabled=!player.preparing,seek=seek,
                colors = SliderDefaults.colors(thumbColor = gardenInk, activeTrackColor = gardenMuted, inactiveTrackColor = gardenMuted.copy(alpha = .25f)))
        }
    }
}

private fun gardenClock(ms: Long): String = "%02d:%02d".format(ms / 60_000, ms / 1000 % 60)

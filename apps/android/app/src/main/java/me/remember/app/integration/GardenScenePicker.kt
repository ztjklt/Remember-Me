package me.remember.app.integration

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

/** Existing bundled artwork only. Selecting a landscape changes device decoration, never story facts. */
@Composable internal fun GardenSceneOptions(current: SceneChoice, choose: (SceneChoice) -> Unit) {
    TextButton(onClick = { choose(SceneChoice.AUTO) }, modifier = Modifier.semantics { selected = current == SceneChoice.AUTO }) {
        if(current == SceneChoice.AUTO) { Icon(Icons.Outlined.CheckCircle, null); Spacer(Modifier.width(8.dp)) }
        Text(SceneChoice.AUTO.title)
    }
    val columns = if(LocalDensity.current.fontScale >= 1.5f) 1 else 2
    SceneChoice.entries.filter { it.scene != null }.chunked(columns).forEach { row ->
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            row.forEach { choice ->
                Surface(onClick = { choose(choice) }, modifier = Modifier.weight(1f).semantics { selected = choice == current }
                    .testTag("garden-scene-${choice.name}"), shape = RoundedCornerShape(20.dp),
                    border = BorderStroke(if(choice == current) 2.dp else 1.dp,
                        if(choice == current) gardenMuted else gardenMuted.copy(alpha = .25f))) {
                    Box(Modifier.height(108.dp)) {
                        Image(painterResource(gardenLandscape(checkNotNull(choice.scene))), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, gardenGlass.copy(alpha = .90f)))))
                        Row(Modifier.align(Alignment.BottomStart).fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(choice.title, color = gardenInk, fontSize = 16.sp, modifier = Modifier.weight(1f))
                            if(choice == current) Icon(Icons.Outlined.CheckCircle, "已选", tint = gardenInk)
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable internal fun GardenScenePicker(current: SceneChoice, choose: (SceneChoice) -> Unit, close: () -> Unit) {
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().padding(16.dp).heightIn(max = 640.dp), shape = RoundedCornerShape(28.dp),
            color = if(MaterialTheme.colorScheme.background.luminance() < .5f) Color(0xFF233B32) else Color(0xFFE9EDDA)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("在喜欢的地方重温", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                    TextButton(onClick = close) { Text("关闭") }
                }
                Text("只改变背景，故事和分享范围保持原样。", style = MaterialTheme.typography.bodySmall)
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                    GardenSceneOptions(current) { choose(it); close() }
                }
            }
        }
    }
}

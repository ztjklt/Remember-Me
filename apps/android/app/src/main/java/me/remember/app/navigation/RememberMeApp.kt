package me.remember.app.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.material3.TopAppBarDefaults
import me.remember.app.core.designsystem.NatureScene
import me.remember.app.core.designsystem.atmosphere
import me.remember.app.feature.AgentsDashboardScreen
import me.remember.app.feature.ArchivePage
import me.remember.app.feature.BottomTabs
import me.remember.app.feature.CapturePage
import me.remember.app.feature.ChatHistoryScreen
import me.remember.app.feature.DetailPage
import me.remember.app.feature.GraphDashboardScreen
import me.remember.app.feature.MeDashboardScreen
import me.remember.app.feature.MemoryPage
import me.remember.app.feature.MobileViewModel
import me.remember.app.feature.PortraitScreen

/** PR #81's latest portrait navigation, backed by PR #79's real local recording flow. */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun RememberMeApp(model: MobileViewModel) {
    val records by model.recordings.collectAsState()
    val message by model.message.collectAsState()
    var route by remember { mutableStateOf(Routes.Portrait) }
    var recordingOpen by remember { mutableStateOf(false) }
    var detailPath by remember { mutableStateOf<String?>(null) }
    var memoryID by remember { mutableStateOf<String?>(null) }
    val tabState = rememberSaveableStateHolder()

    fun go(destination: String) {
        when (destination) {
            Routes.Recording -> { model.newRecording(); recordingOpen = true }
            Routes.Home -> route = Routes.Portrait
            else -> route = destination
        }
    }
    fun back() {
        when {
            memoryID != null -> memoryID = null
            detailPath != null -> detailPath = null
            else -> route = Routes.Portrait
        }
    }
    BackHandler(detailPath != null || (route != Routes.Portrait && !recordingOpen)) { back() }

    when {
        recordingOpen -> CapturePage(model, close = { recordingOpen = false }, openDetail = {
            detailPath = it.audioPath
            memoryID = null
            recordingOpen = false
        })
        detailPath != null -> {
            val record = records.firstOrNull { it.audioPath == detailPath }
            Scaffold(modifier = Modifier.atmosphere(scene = NatureScene.Forest), containerColor = Color.Transparent, topBar = {
                TopAppBar(title = { Text(if (memoryID == null) "录音详情" else "记忆详情") },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent),
                    navigationIcon = { IconButton(onClick = ::back) {
                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回")
                    } })
            }) { padding ->
                androidx.compose.foundation.layout.Box(Modifier.padding(padding)) {
                    when {
                        record == null -> Text("找不到这段录音。原有文件不会因此删除。")
                        memoryID != null -> MemoryPage(model, record, memoryID!!, onDeleted = { memoryID = null })
                        else -> DetailPage(model, record, openMemory = { memoryID = it })
                    }
                }
            }
        }
        else -> Column(Modifier.fillMaxSize()) {
            // The dock stays mounted. Only browse destinations take part in this transition;
            // capture and detail retain a single instance above this branch.
            AnimatedContent(targetState = route, modifier = Modifier.weight(1f),
                transitionSpec = {
                    val order = listOf(Routes.Portrait, Routes.Graph, Routes.Memories, Routes.Agents, Routes.Me, Routes.Twin)
                    val direction = if (order.indexOf(targetState) >= order.indexOf(initialState)) 1 else -1
                    (fadeIn(tween(260)) + slideInHorizontally(tween(280)) { direction * it / 24 }) togetherWith
                        (fadeOut(tween(160)) + slideOutHorizontally(tween(240)) { -direction * it / 32 })
                }, label = "browse destination") { destination ->
                tabState.SaveableStateProvider(destination) {
                    when (destination) {
                        Routes.Graph -> GraphDashboardScreen(::go, showBottomTabs = false)
                        Routes.Memories -> Scaffold(modifier = Modifier.atmosphere(scene = NatureScene.Lake), containerColor = Color.Transparent) { padding ->
                            Box(Modifier.padding(padding)) {
                                ArchivePage(records, open = { detailPath = it.audioPath },
                                    openMemory = { recording, id -> detailPath = recording.audioPath; memoryID = id })
                            }
                        }
                        Routes.Agents -> AgentsDashboardScreen(::go, showBottomTabs = false)
                        Routes.Me -> MeDashboardScreen(::go, records, showBottomTabs = false)
                        Routes.Twin -> ChatHistoryScreen(back = ::back, go = ::go, showBottomTabs = false)
                        else -> PortraitScreen(::go, showBottomTabs = false)
                    }
                }
            }
            BottomTabs(route, ::go)
        }
    }
    if (message != null) AlertDialog(onDismissRequest = model::dismissMessage,
        title = { Text("操作未完成") }, text = { Text(message!!) },
        confirmButton = { TextButton(onClick = model::dismissMessage) { Text("知道了") } })
}

package me.remember.app.feature

import androidx.compose.foundation.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import kotlinx.coroutines.delay
import kotlin.random.Random
import androidx.compose.ui.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.BuildConfig
import me.remember.app.R
import me.remember.app.data.repository.MemoryRepository
import me.remember.app.model.*
import me.remember.app.navigation.Routes
import me.remember.app.ui.components.*

@Composable
fun PortraitScreen(go: (String) -> Unit) {
    val topics = listOf(
        "Is this your psychological feeling?" to Routes.Memories,
        "Things you mentioned these days" to Routes.Memories,
        "Your physical health, checked by your voice" to Routes.Recording,
        "Your identity defines who you are" to Routes.Memories,
        "Maybe you will talk about it in this way" to Routes.Twin,
        "What has been quietly changing?" to Routes.Memories,
        "A person who appeared in your thoughts" to Routes.Memories,
        "A decision worth remembering" to Routes.Memories
    )
    var visibleTopics by remember { mutableStateOf(topics.take(5)) }
    var portraitQuery by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        while (true) {
            delay(Random.nextLong(18_000L, 32_000L))
            visibleTopics = topics.shuffled().take(5)
        }
    }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
      Column(
        Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
      ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            TextButton({ go(Routes.Twin) }, Modifier.weight(.8f)) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    HugeIcon(R.drawable.hg_chat, "Chat history", Modifier.size(18.dp))
                    Text("Chat history", style = MaterialTheme.typography.labelSmall, maxLines = 1)
                }
            }
            OutlinedTextField(
                value = portraitQuery,
                onValueChange = { portraitQuery = it },
                modifier = Modifier.weight(1.8f).padding(horizontal = 8.dp),
                singleLine = true,
                leadingIcon = { HugeIcon(R.drawable.hg_search, "Search", Modifier.size(18.dp)) },
                placeholder = { Text("Search portraits", style = MaterialTheme.typography.bodySmall) }
            )
            TextButton({}, Modifier.weight(.8f)) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    HugeIcon(R.drawable.hg_download, "Export", Modifier.size(18.dp))
                    Text("Export", style = MaterialTheme.typography.labelSmall, maxLines = 1)
                }
            }
        }
        BrandHeader("A quiet map of you")
        Text("Portrait", style = MaterialTheme.typography.headlineLarge)
        Text("画像布局预览。真实记忆请到档案查看；图中的示例内容不代表已分析你的录音。", color = RememberMeColors.Muted)
        Button(onClick = { go(Routes.Recording) }, modifier = Modifier.fillMaxWidth()) { Text("开始录音") }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PortraitCard("Thing memory", "events and facts", Routes.Memories, go, Modifier.weight(1f))
            PortraitCard("Mood memory", "feelings over time", Routes.Memories, go, Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PortraitCard("Psycho memory", "patterns and values", Routes.Memories, go, Modifier.weight(1f))
            PortraitCard("Filter memory", "search the archive", Routes.Memories, go, Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PortraitCard("Status memory", "health and life", Routes.Recording, go, Modifier.weight(1f))
            PortraitCard("Environment", "places and context", Routes.Memories, go, Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PortraitCard("Identity memory", "who you are", Routes.Memories, go, Modifier.weight(1f))
            PortraitCard("Expression", "how you speak", Routes.Memories, go, Modifier.weight(1f))
        }
        RmDivider()
        Text("Today", style = MaterialTheme.typography.titleLarge)
        Text("话题示例", style = MaterialTheme.typography.bodyMedium, color = RememberMeColors.Muted)
        visibleTopics.filter { portraitQuery.isBlank() || it.first.contains(portraitQuery, ignoreCase = true) }.forEachIndexed { index, (topic, route) ->
            Row(Modifier.fillMaxWidth().clickable { go(route) }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("0${index + 1}", color = RememberMeColors.Clay, modifier = Modifier.width(34.dp))
                Text(topic, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                Text(">", color = RememberMeColors.Moss, style = MaterialTheme.typography.titleLarge)
            }
            if (index < visibleTopics.lastIndex) RmDivider()
        }
        if (portraitQuery.isNotBlank() && visibleTopics.none { it.first.contains(portraitQuery, ignoreCase = true) }) {
            Text("No portraits found", color = RememberMeColors.Muted)
        }
      }
      BottomTabs(Routes.Portrait, go)
    }
}

@Composable
private fun PortraitCard(title: String, subtitle: String, route: String, go: (String) -> Unit, modifier: Modifier) {
    Column(modifier.clip(MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface)
        .clickable { go(route) }.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(subtitle, style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
        Text(">", color = RememberMeColors.Moss, modifier = Modifier.align(Alignment.End))
    }
}

@Composable
fun BottomTabs(selected: String, go: (String) -> Unit) {
    val tabs = listOf("Portrait" to Routes.Portrait, "Graphs" to Routes.Graph, "Memories" to Routes.Memories, "Agents" to Routes.Agents, "Me" to Routes.Me)
    Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        tabs.forEach { (label, route) ->
            val icon = when (route) {
                Routes.Portrait -> R.drawable.hg_home
                Routes.Graph -> R.drawable.hg_chart
                Routes.Memories -> R.drawable.hg_book
                Routes.Agents -> R.drawable.hg_brain
                else -> R.drawable.hg_user
            }
            val tint = if (selected == route) RememberMeColors.Clay else RememberMeColors.Muted
            TextButton(
                onClick = { go(route) },
                modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(horizontal = 1.dp, vertical = 6.dp)
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    HugeIcon(icon, label, Modifier.size(16.dp), tint)
                    Text(label, color = tint, style = MaterialTheme.typography.labelSmall, maxLines = 1, softWrap = false)
                }
            }
        }
    }
}

@Composable
private fun SectionTopNav(searchPlaceholder: String, go: (String) -> Unit, titleOnly: Boolean = false) {
    var query by remember { mutableStateOf("") }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        TextButton({ go(Routes.Twin) }, Modifier.weight(.8f)) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                HugeIcon(R.drawable.hg_chat, "Chat history", Modifier.size(18.dp))
                Text("Chat history", style = MaterialTheme.typography.labelSmall, maxLines = 1)
            }
        }
        if (titleOnly) {
            Text("REMEMBER ME", Modifier.weight(1.8f), textAlign = androidx.compose.ui.text.style.TextAlign.Center, style = MaterialTheme.typography.labelLarge, color = RememberMeColors.Moss)
        } else {
            OutlinedTextField(query, { query = it }, Modifier.weight(1.8f).padding(horizontal = 8.dp), singleLine = true, leadingIcon = { HugeIcon(R.drawable.hg_search, "Search", Modifier.size(18.dp)) }, placeholder = { Text(searchPlaceholder, style = MaterialTheme.typography.bodySmall) })
        }
        TextButton({}, Modifier.weight(.8f)) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                HugeIcon(R.drawable.hg_download, "Export", Modifier.size(18.dp))
                Text("Export", style = MaterialTheme.typography.labelSmall, maxLines = 1)
            }
        }
    }
}

@Composable
private fun BrandHeader(slogan: String) {
    Column(
        Modifier.fillMaxWidth()
            .clip(MaterialTheme.shapes.medium)
            .border(1.dp, RememberMeColors.Line, MaterialTheme.shapes.medium)
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HugeIcon(R.drawable.hg_brain, "Remember Me logo", Modifier.size(20.dp), RememberMeColors.Moss)
            Text("REMEMBER ME", style = MaterialTheme.typography.labelLarge, color = RememberMeColors.Moss)
        }
        Text(slogan, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
fun AgentsDashboardScreen(go: (String) -> Unit) {
    var showDetails by remember { mutableStateOf(false) }
    var controllerMessage by remember { mutableStateOf("") }
    var controllerAsked by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
      Column(
        Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
      ) {
        SectionTopNav("Search agents", go)
        BrandHeader("Agents behind your memories")
        Text("Each agent has one job, a clear source, and a visible confidence level.", color = RememberMeColors.Muted)
        Text("Agents list", style = MaterialTheme.typography.titleLarge)
        AgentCard("Memory keeper", "录音和核对文字已保存在本机。", "整理未连接", RememberMeColors.Moss)
        AgentCard("Portrait reader", "真实画像需要由已核对的记忆生成。", "尚无结果", RememberMeColors.Clay)
        AgentCard("Twin guide", "Android Twin 服务尚未接入。", "待接入", RememberMeColors.Moss)
        RmDivider()
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Recent work", style = MaterialTheme.typography.titleLarge)
            Text("暂无真实运行记录", color = RememberMeColors.Muted, style = MaterialTheme.typography.bodySmall)
        }
        Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).border(1.dp, RememberMeColors.Line, MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("You are the master controller", style = MaterialTheme.typography.titleLarge)
            Text("这是界面预览，当前 Android 构建未连接代理服务。", color = RememberMeColors.Muted, style = MaterialTheme.typography.bodyMedium)
            if (controllerAsked) Text("问题没有发送；请先接入服务。", style = MaterialTheme.typography.bodyMedium)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(controllerMessage, { controllerMessage = it }, Modifier.weight(1f), minLines = 1, maxLines = 2, placeholder = { Text("Ask the main agent anything") })
                IconButton(onClick = { controllerAsked = true }, modifier = Modifier.size(52.dp)) { HugeIcon(R.drawable.hg_chat, "Send question", Modifier.size(24.dp), RememberMeColors.Moss) }
            }
        }
        RmSecondaryButton(if (showDetails) "Hide evidence" else "View evidence", Modifier.fillMaxWidth()) { showDetails = !showDetails }
        if (showDetails) {
            Text("Evidence stays linked to the original recording. Nothing is added to your portrait without your confirmation.", color = RememberMeColors.Muted, style = MaterialTheme.typography.bodyMedium)
        }
      }
      BottomTabs(Routes.Agents, go)
    }
}

@Composable
private fun AgentCard(name: String, description: String, status: String, color: androidx.compose.ui.graphics.Color) {
    val icon = when (name) {
        "Memory keeper" -> R.drawable.hg_book
        "Portrait reader" -> R.drawable.hg_chart
        else -> R.drawable.hg_chat
    }
    val tint = when (name) {
        "Memory keeper" -> RememberMeColors.SageTint
        "Portrait reader" -> RememberMeColors.LilacTint
        else -> RememberMeColors.SkyTint
    }
    Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).border(1.dp, color.copy(alpha = .35f), MaterialTheme.shapes.medium).background(tint).padding(14.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                HugeIcon(icon, name, Modifier.size(20.dp), color)
                Text(name, style = MaterialTheme.typography.titleMedium, maxLines = 1)
            }
            Text(status, color = color, style = MaterialTheme.typography.labelSmall, maxLines = 1)
        }
        Text(description, color = RememberMeColors.Muted, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun MeDashboardScreen(go: (String) -> Unit, recordings: List<me.remember.app.data.repository.AudioRecording>) {
    var localOnly by remember { mutableStateOf(true) }
    var notifications by remember { mutableStateOf(false) }
    var darkMode by remember { mutableStateOf(false) }
    var characterSize by remember { mutableFloatStateOf(.5f) }
    var settingsQuery by remember { mutableStateOf("") }
    val today = java.time.LocalDate.now()
    val todayRecords = recordings.filter { recording ->
        runCatching { java.time.Instant.parse(recording.createdAt).atZone(java.time.ZoneId.systemDefault()).toLocalDate() == today }.getOrDefault(false)
    }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
      Column(
        Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
      ) {
        SectionTopNav("", go, titleOnly = true)
        Text("Settings", style = MaterialTheme.typography.headlineLarge)
        Text("设置控件仍是界面预览，尚未保存到账号或改变系统设置。", color = RememberMeColors.Muted)
        OutlinedTextField(settingsQuery, { settingsQuery = it }, Modifier.fillMaxWidth(), singleLine = true, leadingIcon = { HugeIcon(R.drawable.hg_search, "Search settings", Modifier.size(18.dp)) }, placeholder = { Text("Search settings") })
        ProfileRow()
        Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            SettingRow("Light or dark", if (darkMode) "Dark appearance" else "Light appearance", darkMode, R.drawable.hg_settings) { darkMode = it }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Character size", style = MaterialTheme.typography.bodyLarge)
                Text("Adjust reading size", color = RememberMeColors.Muted, style = MaterialTheme.typography.bodySmall)
                Slider(value = characterSize, onValueChange = { characterSize = it }, valueRange = 0f..1f)
            }
            RmSecondaryButton("Exit login", Modifier.fillMaxWidth()) { }
        }
        RmDivider()
        Text("Today's data", style = MaterialTheme.typography.titleLarge)
        TodayDataCard("今日录音", "${todayRecords.size} 段")
        TodayDataCard("已核对文字", "${todayRecords.sumOf { it.reviewedTranscript?.length ?: 0 }} 字")
        TodayDataCard("真实记忆", "${todayRecords.sumOf { r -> r.memories.count { it.status == "active" } }} 条")
        Text("Today's words to you", style = MaterialTheme.typography.titleLarge)
        Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface).padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("当前没有根据真实录音生成的话语。", style = MaterialTheme.typography.bodyLarge)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton({ }) { Text("How do we collect data?") }
            TextButton({ }) { Text("About us") }
        }
        RmDivider()
      }
      BottomTabs(Routes.Me, go)
    }
}

@Composable
private fun TodayDataCard(title: String, value: String) {
    val icon = when (title) {
        "Words you said today" -> R.drawable.hg_chat
        "Your feelings" -> R.drawable.hg_brain
        else -> R.drawable.hg_book
    }
    val tint = when (title) {
        "Words you said today" -> RememberMeColors.SkyTint
        "Your feelings" -> RememberMeColors.ClayTint
        else -> RememberMeColors.SageTint
    }
    Row(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).background(tint).padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            HugeIcon(icon, title, Modifier.size(20.dp), RememberMeColors.Moss)
            Text(title, style = MaterialTheme.typography.bodyMedium, maxLines = 1)
        }
        Text(value, color = RememberMeColors.Moss, style = MaterialTheme.typography.labelLarge, maxLines = 1)
    }
}

@Composable
private fun ProfileRow() {
    Row(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).border(1.dp, RememberMeColors.Line, MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface).padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(52.dp).clip(androidx.compose.foundation.shape.CircleShape).background(RememberMeColors.Clay), contentAlignment = Alignment.Center) {
            HugeIcon(R.drawable.hg_user, "Profile picture", Modifier.size(28.dp), Color.White)
        }
        Column {
            Text("Username", style = MaterialTheme.typography.labelSmall, color = RememberMeColors.Muted)
            Text("Remember Me user", style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
private fun SettingRow(title: String, subtitle: String, checked: Boolean, icon: Int? = null, onCheckedChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        icon?.let { HugeIcon(it, title, Modifier.size(20.dp), RememberMeColors.Moss); Spacer(Modifier.width(8.dp)) }
        Column(Modifier.weight(1f)) { Text(title, style = MaterialTheme.typography.bodyMedium); Text(subtitle, color = RememberMeColors.Muted, style = MaterialTheme.typography.bodySmall) }
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun ActionRow(title: String, subtitle: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { onClick() }.padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) { Text(title, style = MaterialTheme.typography.bodyLarge); Text(subtitle, color = RememberMeColors.Muted, style = MaterialTheme.typography.bodySmall) }
        Text(">", color = RememberMeColors.Moss, style = MaterialTheme.typography.titleLarge)
    }
}

@Composable
fun SimpleSectionScreen(title: String, subtitle: String, back: () -> Unit) {
    RmPage {
        TextButton(back) { Text("Back") }
        Text(title, style = MaterialTheme.typography.headlineLarge)
        Text(subtitle, color = RememberMeColors.Muted)
        RmDivider()
        Text("This section is ready for the corresponding agent data.", style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
fun GraphDashboardScreen(go: (String) -> Unit) {
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
      Column(
        Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
      ) {
        SectionTopNav("Search graphs", go)
        BrandHeader("Memory relationships")
        Text("关系图是设计示意，尚未由你的真实录音生成。", color = RememberMeColors.Muted)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GraphMetricCard("Event flow", "timeline", Modifier.weight(1f))
            GraphMetricCard("Mood trends", "emotions", Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GraphMetricCard("Decision + values", "patterns", Modifier.weight(1f))
            GraphMetricCard("Expression style", "voice", Modifier.weight(1f))
        }
        RmDivider()
        Text("How do these combine?", style = MaterialTheme.typography.titleLarge)
        Text("Events become memories. Memories reveal moods, values and expression patterns. The graph keeps each connection traceable to its evidence.", color = RememberMeColors.Muted, style = MaterialTheme.typography.bodyMedium)
        RelationshipImageGraph()
      }
      BottomTabs(Routes.Graph, go)
    }
}

@Composable
fun MemoryDashboardScreen(memoryRepository: MemoryRepository, go: (String) -> Unit) {
    val state by memoryRepository.memories().collectAsState(initial = Loadable.Loading)
    val memories = (state as? Loadable.Content)?.value.orEmpty()
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
      Column(
        Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
      ) {
        SectionTopNav("Search memories", go)
        BrandHeader("Memories show who you are")
        Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).border(1.dp, RememberMeColors.Line, MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    HugeIcon(R.drawable.hg_clock, "Memory history", Modifier.size(20.dp), RememberMeColors.Moss)
                    Text("Memory", style = MaterialTheme.typography.titleLarge)
                }
                TextButton({ }) {
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                        HugeIcon(R.drawable.hg_reload_horizontal, "Refresh", Modifier.size(16.dp), RememberMeColors.Moss)
                        Text("Refresh history board", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            Text("Here you can see when a memory changed and what it changed into.", color = RememberMeColors.Muted, style = MaterialTheme.typography.bodyMedium)
            MemoryChangeBoard(memories)
        }
        RmDivider()
        Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).border(1.dp, RememberMeColors.Line, MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface).padding(horizontal = 16.dp, vertical = 12.dp)) {
            Text("Memory control board", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(4.dp))
            MemoryControlRow("Memory change", "Review and compare versions") { }
            MemoryControlRow("Memory delete", "Remove it from the portrait") { }
            MemoryControlRow("Add memory", "Write a memory manually") { }
        }
      }
      BottomTabs(Routes.Memories, go)
    }
}

@Composable
private fun MemoryChangeBoard(memories: List<Memory>) {
    Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.small).background(RememberMeColors.SageTint.copy(alpha = .55f)).padding(14.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (memories.isEmpty()) {
            Text("No memory changes yet", color = RememberMeColors.Muted)
            Text("New recordings and confirmed memories will appear here.", style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
        } else {
            memories.take(5).forEachIndexed { index, memory ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.width(64.dp)) {
                        Text(memory.date, style = MaterialTheme.typography.labelMedium, color = RememberMeColors.Clay)
                        Text("v${index + 1}", style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
                    }
                    Box(Modifier.size(10.dp).clip(androidx.compose.foundation.shape.CircleShape).background(RememberMeColors.Moss))
                    Spacer(Modifier.width(12.dp))
                    Text(memory.story, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                }
                if (index < memories.take(5).lastIndex) HorizontalDivider(color = RememberMeColors.Line)
            }
        }
    }
}

@Composable
private fun MemoryControlRow(title: String, subtitle: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { onClick() }.padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        val icon = when (title) {
            "Memory change" -> R.drawable.hg_edit
            "Memory delete" -> R.drawable.hg_delete
            else -> R.drawable.hg_book
        }
        val tint = if (title == "Memory delete") RememberMeColors.Clay else RememberMeColors.Moss
        HugeIcon(icon, title, Modifier.size(19.dp), tint)
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
        }
        HugeIcon(R.drawable.hg_more, "Open $title", Modifier.size(18.dp), RememberMeColors.Muted)
    }
    RmDivider()
}

@Composable
private fun GraphMetricCard(title: String, subtitle: String, modifier: Modifier) {
    val accent = when (title) {
        "Event flow" -> RememberMeColors.SageTint
        "Mood trends" -> RememberMeColors.ClayTint
        "Decision + values" -> RememberMeColors.LilacTint
        else -> RememberMeColors.SkyTint
    }
    Column(modifier.clip(MaterialTheme.shapes.medium).background(accent).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium, maxLines = 1)
        Text(subtitle, style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
        Box(Modifier.fillMaxWidth().height(30.dp), contentAlignment = Alignment.BottomStart) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.Bottom) {
                listOf(0.35f, 0.7f, 0.48f, 0.86f, 0.62f).forEach { value ->
                    Box(Modifier.width(9.dp).height((26 * value).dp).background(RememberMeColors.Moss.copy(alpha = .7f)))
                }
            }
        }
    }
}

@Composable
private fun RelationshipImageGraph() {
    Column(
        Modifier.fillMaxWidth()
            .clip(MaterialTheme.shapes.medium)
            .background(RememberMeColors.Surface)
            .border(1.dp, RememberMeColors.Line, MaterialTheme.shapes.medium)
            .padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text("Memory relationship graph", style = MaterialTheme.typography.titleMedium)
        Image(
            painter = painterResource(R.drawable.relationship_graph),
            contentDescription = "Memory relationship graph",
            modifier = Modifier.fillMaxWidth().aspectRatio(2983f / 2929f),
            contentScale = ContentScale.Fit
        )
        Text("Each relationship remains linked to its memory and recording.", style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
    }
}

@Composable
private fun RelationshipVectorGraph() {
    Box(Modifier.fillMaxWidth().height(330.dp).clip(MaterialTheme.shapes.medium).background(RememberMeColors.Surface), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Memory relationship graph", style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
                GraphNode("values", RememberMeColors.Clay)
                Text("—", color = RememberMeColors.Line)
                GraphNode("decisions", RememberMeColors.Moss)
                Text("—", color = RememberMeColors.Line)
                GraphNode("events", RememberMeColors.Clay)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp), verticalAlignment = Alignment.CenterVertically) {
                GraphNode("mood", RememberMeColors.Moss)
                Text("—  subject  —", color = RememberMeColors.Muted)
                GraphNode("expression", RememberMeColors.Moss)
            }
            Text("Each edge points back to a memory and its recording.", style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
        }
    }
}

@Composable
private fun GraphNode(label: String, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Box(Modifier.size(18.dp).clip(androidx.compose.foundation.shape.CircleShape).background(color))
        Text(label, style = MaterialTheme.typography.labelMedium)
    }
}

@Composable fun CreatorHomeScreen(go:(String)->Unit)=RmPage{
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Column{Text("晚上好",color=RememberMeColors.Muted);Text("陈屿",style=MaterialTheme.typography.headlineLarge)};if(BuildConfig.DEBUG) Text("•••",Modifier.clickable{go(Routes.Debug)}.padding(12.dp))}
    Spacer(Modifier.height(12.dp));Text("今天想留下些什么？",style=MaterialTheme.typography.headlineMedium);Box(Modifier.fillMaxWidth(),contentAlignment=Alignment.Center){RmCaptureOrb{go(Routes.Recording)}}
    RmDivider();RmSectionHeader("我又多了解了你一点");Text("你提到小时候和外婆一起整理老照片。那段时间让你觉得，记住一个人也包括记住当时的心情。",style=MaterialTheme.typography.bodyLarge)
    RmDivider();RmSectionHeader("还有一些我不了解");Text("你很少谈到高中以前的朋友。",color=RememberMeColors.Muted);RmSecondaryButton("聊聊这个"){}
    RmDivider();RmSectionHeader("最近的记忆","查看全部");Text("2019 · 广州\n第一次真正承认自己想做影像。",Modifier.clickable{go(Routes.Memories)}.padding(vertical=8.dp),style=MaterialTheme.typography.bodyLarge)
    NavigationRow(go)
}
@Composable private fun NavigationRow(go:(String)->Unit){Row(Modifier.fillMaxWidth().padding(top=12.dp),horizontalArrangement=Arrangement.SpaceAround){listOf("Home" to Routes.Home,"Memories" to Routes.Memories,"Capture" to Routes.Recording,"Twin" to Routes.Twin).forEach{(label,r)->Text(label,Modifier.clickable{go(r)}.padding(10.dp),style=MaterialTheme.typography.labelMedium)}}}

@Composable fun MemoriesScreen(memoryRepository:MemoryRepository,back:()->Unit){val state by memoryRepository.memories().collectAsState(initial=Loadable.Loading);RmPage{TextButton(back){Text("← 返回")};Text("Memory Archive",style=MaterialTheme.typography.headlineLarge);Text("不是一份清单，是你留下的人生切片。",color=RememberMeColors.Muted);when(val s=state){is Loadable.Content->s.value.forEach{m->MemoryItem(m)};Loadable.Loading->CircularProgressIndicator();Loadable.Empty->Text("还没有记忆");is Loadable.Error->Text(s.message)}}}
@Composable private fun MemoryItem(m:Memory){Column(Modifier.padding(vertical=12.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){Text("${m.date} · ${m.place}",color=RememberMeColors.Muted);Text("“${m.story}”",style=MaterialTheme.typography.titleLarge);Text((m.people+m.tags).joinToString("   "),style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted);RmVoicePlayer(m.duration);RmDivider()}}

@Composable
@OptIn(ExperimentalFoundationApi::class)
private fun TwinLegacyScreen(back: () -> Unit, go: (String) -> Unit) {
    var query by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var asked by remember { mutableStateOf(false) }
    var history by remember { mutableStateOf(listOf("What matters lately?" to "Today, 09:42", "Grandma's radio" to "Yesterday", "A decision worth remembering" to "Sep 24", "How I want to grow" to "Sep 21")) }
    var selected by remember { mutableStateOf<Int?>(null) }
    var renameOpen by remember { mutableStateOf(false) }
    var renameIndex by remember { mutableIntStateOf(-1) }
    var renameText by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
      Row(Modifier.weight(1f).fillMaxWidth()) {
        Column(Modifier.width(172.dp).fillMaxHeight().padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth(), singleLine = true, leadingIcon = { HugeIcon(R.drawable.hg_search, "Search", Modifier.size(16.dp)) }, placeholder = { Text("Search", style = MaterialTheme.typography.labelSmall) })
            TextButton(back, Modifier.fillMaxWidth()) { Text("Back") }
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
                HugeIcon(R.drawable.hg_clock, "Chat history", Modifier.size(16.dp), RememberMeColors.Muted)
                Text("Chat history", style = MaterialTheme.typography.labelMedium, color = RememberMeColors.Muted)
            }
            Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
              history.mapIndexedNotNull { index, item -> if (query.isBlank() || item.first.contains(query, ignoreCase = true)) index to item else null }.forEach { (index, item) ->
                Box {
                  Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.small).background(MaterialTheme.colorScheme.surface).combinedClickable(onClick = { }, onLongClick = { selected = index }).padding(9.dp)) {
                    Text(item.first, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                    Text(item.second, style = MaterialTheme.typography.labelSmall, color = RememberMeColors.Muted)
                  }
                  DropdownMenu(expanded = selected == index, onDismissRequest = { selected = null }) {
                    DropdownMenuItem(text = { Text("Rename") }, onClick = { renameText = item.first; renameIndex = index; renameOpen = true; selected = null })
                    DropdownMenuItem(text = { Text("Top") }, onClick = { history = listOf(item) + history.filterIndexed { i, _ -> i != index }; selected = null })
                    DropdownMenuItem(text = { Text("Delete") }, onClick = { history = history.filterIndexed { i, _ -> i != index }; selected = null })
                  }
                }
              }
            }
            RmDivider()
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(32.dp).clip(androidx.compose.foundation.shape.CircleShape).background(RememberMeColors.Clay), contentAlignment = Alignment.Center) { Text("你", color = Color.White) }
                Spacer(Modifier.width(8.dp)); HugeIcon(R.drawable.hg_user, "Profile", Modifier.size(16.dp)); Spacer(Modifier.width(4.dp)); Text("My profile", style = MaterialTheme.typography.labelMedium)
            }
        }
        Column(Modifier.weight(1f).fillMaxHeight().verticalScroll(rememberScrollState()).padding(horizontal = 22.dp, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("REMEMBER ME", style = MaterialTheme.typography.labelLarge, color = RememberMeColors.Moss)
            Text("A quiet conversation", style = MaterialTheme.typography.headlineMedium)
            Text("Your words stay distinct from Twin's simulation.", color = RememberMeColors.Muted)
            RmDivider()
            if (asked) {
                Text("You", style = MaterialTheme.typography.labelMedium, color = RememberMeColors.Clay)
                Text(message.ifBlank { "What should I remember from today?" }, style = MaterialTheme.typography.bodyLarge)
                Text("Remember Me", style = MaterialTheme.typography.labelMedium, color = RememberMeColors.Moss)
                Text("I will keep the parts that remain useful, and show you the source before anything becomes part of your portrait.", style = MaterialTheme.typography.bodyLarge)
            } else {
                Text("Start a conversation", style = MaterialTheme.typography.titleLarge)
                Text("Ask about a memory, a feeling, or a decision. Twin will label what is original and what is simulation.", color = RememberMeColors.Muted)
            }
            Spacer(Modifier.weight(1f))
            OutlinedTextField(message, { message = it }, Modifier.fillMaxWidth(), minLines = 2, placeholder = { Text("Write to Remember Me") })
            RmPrimaryButton("Send", { asked = true }, Modifier.fillMaxWidth())
        }
      }
      BottomTabs(Routes.Twin, go)
    }
    if (renameOpen) {
        AlertDialog(onDismissRequest = { renameOpen = false }, title = { Text("Rename chat") }, text = { OutlinedTextField(renameText, { renameText = it }, singleLine = true) }, confirmButton = { TextButton({ history = history.mapIndexed { i, item -> if (i == renameIndex) renameText to item.second else item }; renameOpen = false }) { Text("Rename") } }, dismissButton = { TextButton({ renameOpen = false }) { Text("Cancel") } })
    }
}

@Composable fun CalibrationScreen(back:()->Unit){var step by remember{mutableIntStateOf(0)};RmPage{TextButton(back){Text("← 返回")};Text("看看我是不是真的了解你。",style=MaterialTheme.typography.headlineLarge);Text("如果你有一份稳定但没有兴趣的工作，和一个风险很高但非常想做的项目，你会怎么选？",style=MaterialTheme.typography.titleLarge);Text("Twin Answer · LOCKED",color=RememberMeColors.Muted);Text("我会给想做的项目设一个六个月期限。如果基本生活不受影响，我愿意承担风险。",style=MaterialTheme.typography.bodyLarge);if(step==0)RmPrimaryButton("写下你的答案",{step=1},Modifier.fillMaxWidth()) else {OutlinedTextField("我可能会先存够半年的钱，再试一次。",{},Modifier.fillMaxWidth());RmSectionHeader("Compare");listOf("Decision  接近","Reasoning  有差异","Values  接近","Emotion  尚不确定","Expression  有差异").forEach{Text(it)} }}}

@Composable fun HandoverScreen(back:()->Unit)=RmPage{TextButton(back){Text("← 返回")};Text("数字托付",style=MaterialTheme.typography.headlineLarge);Text("如果未来你无法继续使用 Remember Me，你希望谁可以收到什么？",style=MaterialTheme.typography.titleLarge);listOf("妈妈" to "Memories · Original Voice","伴侣" to "Memories · Messages · Twin Chat","孩子" to "For You messages","朋友" to "Selected memories").forEach{(p,s)->Column(Modifier.padding(vertical=10.dp)){Text(p,fontWeight=FontWeight.Medium);Text(s,color=RememberMeColors.Muted);RmDivider()}};Text("每个人的访问范围都可以不同，也可以随时撤回。",color=RememberMeColors.Muted)}

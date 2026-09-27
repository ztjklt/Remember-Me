package me.remember.app.feature

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import me.remember.app.R
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.navigation.Routes
import me.remember.app.ui.components.HugeIcon

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ChatHistoryScreen(back: () -> Unit, go: (String) -> Unit) {
    var query by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var asked by remember { mutableStateOf(false) }
    var history by remember { mutableStateOf(listOf("What matters lately?" to "Today, 09:42", "Grandma's radio" to "Yesterday", "A decision worth remembering" to "Sep 24", "How I want to grow" to "Sep 21")) }
    var selected by remember { mutableStateOf<Int?>(null) }
    var renameOpen by remember { mutableStateOf(false) }
    var renameIndex by remember { mutableIntStateOf(-1) }
    var renameText by remember { mutableStateOf("") }

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Column(Modifier.weight(1f).fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(query, { query = it }, Modifier.weight(1f), singleLine = true, leadingIcon = { HugeIcon(R.drawable.hg_search, "Search chat history", Modifier.size(18.dp)) }, placeholder = { Text("Search chat history") })
                IconButton(back, Modifier.size(48.dp)) { HugeIcon(R.drawable.hg_arrow_left, "Back", Modifier.size(22.dp)) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                HugeIcon(R.drawable.hg_clock, "Chat history", Modifier.size(18.dp), RememberMeColors.Muted)
                Text("Chat history", style = MaterialTheme.typography.titleMedium, color = RememberMeColors.Muted)
            }
            Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                history.mapIndexedNotNull { index, item -> if (query.isBlank() || item.first.contains(query, ignoreCase = true)) index to item else null }.forEach { (index, item) ->
                    Box(Modifier.fillMaxWidth()) {
                        Column(Modifier.fillMaxWidth().heightIn(min = 76.dp).clip(MaterialTheme.shapes.medium).border(1.dp, RememberMeColors.Line, MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surface).combinedClickable(onClick = { }, onLongClick = { selected = index }).padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(item.first, style = MaterialTheme.typography.bodyLarge, maxLines = 2)
                            Text(item.second, style = MaterialTheme.typography.bodySmall, color = RememberMeColors.Muted)
                        }
                        DropdownMenu(expanded = selected == index, onDismissRequest = { selected = null }) {
                            DropdownMenuItem(text = { Text("Rename") }, leadingIcon = { HugeIcon(R.drawable.hg_edit, "Rename", Modifier.size(18.dp)) }, onClick = { renameText = item.first; renameIndex = index; renameOpen = true; selected = null })
                            DropdownMenuItem(text = { Text("Top") }, leadingIcon = { HugeIcon(R.drawable.hg_more, "Top", Modifier.size(18.dp)) }, onClick = { history = listOf(item) + history.filterIndexed { i, _ -> i != index }; selected = null })
                            DropdownMenuItem(text = { Text("Delete") }, leadingIcon = { HugeIcon(R.drawable.hg_delete, "Delete", Modifier.size(18.dp)) }, onClick = { history = history.filterIndexed { i, _ -> i != index }; selected = null })
                        }
                    }
                }
                if (asked) {
                    Text("You", style = MaterialTheme.typography.labelMedium, color = RememberMeColors.Clay)
                    Text(message.ifBlank { "What should I remember from today?" }, style = MaterialTheme.typography.bodyLarge)
                    Text("Remember Me", style = MaterialTheme.typography.labelMedium, color = RememberMeColors.Moss)
                    Text("I will keep the useful parts and show you the source before anything becomes part of your portrait.", style = MaterialTheme.typography.bodyLarge)
                }
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(message, { message = it }, Modifier.weight(1f), minLines = 1, maxLines = 3, placeholder = { Text("Write to Remember Me") })
                IconButton(onClick = { asked = true }, modifier = Modifier.size(52.dp)) { HugeIcon(R.drawable.hg_chat, "Send message", Modifier.size(24.dp), RememberMeColors.Moss) }
            }
        }
        ChatBottomTabs(go)
    }
    if (renameOpen) {
        AlertDialog(onDismissRequest = { renameOpen = false }, title = { Text("Rename chat") }, text = { OutlinedTextField(renameText, { renameText = it }, singleLine = true) }, confirmButton = { TextButton({ history = history.mapIndexed { i, item -> if (i == renameIndex) renameText to item.second else item }; renameOpen = false }) { Text("Rename") } }, dismissButton = { TextButton({ renameOpen = false }) { Text("Cancel") } })
    }
}

@Composable
private fun ChatBottomTabs(go: (String) -> Unit) {
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
            TextButton(onClick = { go(route) }, modifier = Modifier.weight(1f), contentPadding = PaddingValues(horizontal = 1.dp, vertical = 6.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    HugeIcon(icon, label, Modifier.size(16.dp), RememberMeColors.Muted)
                    Text(label, style = MaterialTheme.typography.labelSmall, maxLines = 1, softWrap = false)
                }
            }
        }
    }
}

package me.remember.app.integration

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

internal fun accountLabel(state: NativeState): String = when(state.demoRole) {
    "owner" -> "陈守义 · 本人"
    "relative" -> "女儿 · 亲友"
    else -> "${state.actorName} · ${if(state.owner) "本人" else "亲友"}"
}

@Composable
internal fun DemoAccountPanel(current: String, enabled: Boolean, switch: (String) -> Unit) {
    Text("选择一个身份体验", style = MaterialTheme.typography.titleLarge)
    listOf(Triple("owner", "陈守义 · 本人", "录下故事，决定与谁分享"),
        Triple("relative", "女儿 · 亲友", "聊聊往事，读留给自己的信")).forEach { (role, title, detail) ->
        Surface(onClick = { if(current != role) switch(role) }, enabled = enabled,
            shape = RoundedCornerShape(24.dp), color = if(current == role) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth().testTag("demo-account-$role")) {
            Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Icon(if(role == "owner") Icons.Outlined.MicNone else Icons.Outlined.ChatBubbleOutline, null)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(title, style = MaterialTheme.typography.titleMedium)
                    Text(detail, style = MaterialTheme.typography.bodyMedium)
                }
                if(current == role) Icon(Icons.Outlined.CheckCircle, "当前账号")
                else Icon(Icons.Outlined.ChevronRight, "切换账号")
            }
        }
    }
    Text("虚构人物演示 · 两个身份各有可见范围", style = MaterialTheme.typography.bodyMedium)
}

@Composable
internal fun DemoEntryPanel(state: NativeState, model: NativeWorkbenchModel) {
    Column(Modifier.fillMaxWidth().padding(top = 48.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
        Text(if(state.busy) "正在进入演示" else "走进陈守义的故事", style = MaterialTheme.typography.headlineMedium)
        if(state.busy) Text("正在加载账号与记忆", style = MaterialTheme.typography.bodyLarge)
        else DemoAccountPanel("", true, model::enterDemo)
    }
}

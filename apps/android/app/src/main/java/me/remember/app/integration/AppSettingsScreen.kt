package me.remember.app.integration

import android.Manifest
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import me.remember.app.BuildConfig
import me.remember.app.core.designsystem.RememberMeBrand

@Composable
fun AppSettingsScreen(state: NativeState, model: NativeWorkbenchModel, appearance: AppearanceChoice,
    updateAppearance: (AppearanceChoice) -> Unit, openPeople: () -> Unit, openPending: () -> Unit,
    resetScroll: () -> Unit,
    confirm: (String, () -> Unit) -> Unit) {
    var section by rememberSaveable(state.actor, state.subject) { mutableStateOf("home") }
    LaunchedEffect(section) { resetScroll() }
    val enabled = !state.busy && !state.recording
    BackHandler(section != "home") { section = "home" }
    if(section != "home") TextButton(onClick = { section = "home" }) { Icon(Icons.Outlined.ArrowBack, null); Spacer(Modifier.width(8.dp)); Text("返回我的") }
    when(section) {
        "home" -> {
            Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                RememberMeBrand(size = 56.dp)
                Column { Text(state.actorName, style = MaterialTheme.typography.headlineMedium)
                    Text(if(state.owner) "留下故事的人" else "被邀请的亲友", style = MaterialTheme.typography.bodyMedium) }
            }
            SettingsEntry("账号与空间", "当前身份、换号与退出", Icons.Outlined.AccountCircle) { section = "account" }
            SettingsEntry("外观与阅读", "${appearance.theme.title} · ${appearance.scene.title}", Icons.Outlined.Palette) { section = "appearance" }
            SettingsEntry("设备权限与提醒", "麦克风、通知与系统设置", Icons.Outlined.Security) { section = "permissions" }
            SettingsEntry("亲友与分享", "邀请、完整分享范围与撤销", Icons.Outlined.PeopleOutline) { section = "sharing" }
            if(state.owner) SettingsEntry("我的用词", "补充人名和方言含义", Icons.Outlined.EditNote) { section = "vocabulary" }
            SettingsEntry("待处理与核对", "录音、亲友问题、人物理解", Icons.Outlined.FactCheck) { section = "pending" }
            SettingsEntry("数据与帮助", "来源、缓存和版本", Icons.Outlined.Info) { section = "help" }
            Text("声音、文字和分享范围，都由你决定。", style = MaterialTheme.typography.bodySmall)
        }
        "account" -> {
            Text("账号与空间", style = MaterialTheme.typography.headlineMedium)
            Text("当前登录：${state.actorName}", style = MaterialTheme.typography.titleMedium)
            Text("角色由服务端根据空间所有权和授权确定，换外观不会改变角色。")
            state.spaces.forEach { space ->
                OutlinedButton(onClick = { model.selectSpace(space); section = "home" }, enabled = enabled,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                    Text("${space.text("display_name")} · ${if(space.text("role") == "owner") "记录者" else "亲友"}${if(space.text("subject_id") == state.subject) " · 当前" else ""}")
                }
            }
            Text("内测账号由管理员准备；需要修改密码时请联系管理员。新设密码可用 8 位，现有密码仍有效。", style = MaterialTheme.typography.bodySmall)
            Button(onClick = { confirm("退出将停止播放并清除本机访问内容，保留按账号隔离的本机原音。再次登录需输入账号密码。") { model.logout() } },
                enabled = !state.busy, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text("退出登录 / 换个账号") }
        }
        "appearance" -> {
            Text("外观与阅读", style = MaterialTheme.typography.headlineMedium)
            Text("明暗", style = MaterialTheme.typography.titleMedium)
            ThemeChoice.entries.forEach { value -> ChoiceRow(value.title, appearance.theme == value) { updateAppearance(appearance.copy(theme = value)) } }
            Text("自然背景", style = MaterialTheme.typography.titleMedium)
            SceneChoice.entries.forEach { value -> ChoiceRow(value.title, appearance.scene == value) { updateAppearance(appearance.copy(scene = value)) } }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { Text("简化花田动效"); Text("减少花朵与阅读页的过渡。", style = MaterialTheme.typography.bodySmall) }
                Switch(appearance.reduceMotion, { updateAppearance(appearance.copy(reduceMotion = it)) })
            }
            Text("文字大小跟随手机系统设置。外观选择只保存在这台设备上。", style = MaterialTheme.typography.bodySmall)
        }
        "permissions" -> DevicePermissions(state, model)
        "sharing" -> { ClaimInvitationPanel(state, model); SharingPanel(state, model, confirm) }
        "vocabulary" -> if(state.owner) {
            var text by remember(state.subject, state.vocabulary) { mutableStateOf(state.vocabulary) }
            Text("我的用词", style = MaterialTheme.typography.headlineMedium)
            Text("写下人名、方言与意思。只有核对时明确带入故事，才用于理解和分享。")
            OutlinedTextField(text, { if(it.length <= 3000) text = it }, label = { Text("人名与方言解释") }, minLines = 4, modifier = Modifier.fillMaxWidth())
            Button(onClick = { model.saveVocabulary(text) }, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text("保存我的用词") }
        }
        "pending" -> {
            Text("待处理与核对", style = MaterialTheme.typography.headlineMedium)
            SettingsEntry("录音核对与失败原因", "查看已保存的原音和对应阶段", Icons.Outlined.Mic) { openPending() }
            SettingsEntry("故事与人物内容", "八个记忆侧面、四个视图与待审核故事", Icons.Outlined.LocalFlorist) { openPeople() }
            ManageTab(state, model, confirm)
        }
        "help" -> {
            Text("数据与帮助", style = MaterialTheme.typography.headlineMedium)
            Text("原音是录制的声音；机器稿是识别结果；核对稿是本人修正的文字；“再补充一点”是另外写下的信息。它们分开保留。")
            Text("允许麦克风不代表同意上传、云端分析或分享；每个环节仍需要主动确认。撤权限制后续访问，不能收回他人已经保存的文件。")
            OutlinedButton(onClick = { confirm("仅清理可重新下载的来源音频，并停止当前原音播放；不删除本机录音、登录或云端记忆。") { model.clearSourceCache() } }, enabled = enabled) { Text("清理下载缓存") }
            OutlinedButton(onClick = model::refresh, enabled = enabled) { Text("刷新云端资料") }
            OutlinedButton(onClick = model::checkConnection, enabled = enabled) { Text("检查服务连接") }
            Text(state.connectionCheck.message, style = MaterialTheme.typography.bodySmall)
            Text("应用版本：${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodySmall)
            Text("接口版本：${state.serviceInfo.apiVersion.ifBlank { "暂未取得" }}", style = MaterialTheme.typography.bodySmall)
            Text("注册：${if(state.serviceInfo.registrationAllowed) "服务端允许" else "本次内测关闭"}", style = MaterialTheme.typography.bodySmall)
            Text("模型凭据在服务端，不需要在手机填写。没有材料时，系统会说明不知道。", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable private fun SettingsEntry(title: String, subtitle: String, icon: ImageVector, open: () -> Unit) {
    Surface(onClick = open, shape = RoundedCornerShape(20.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = .88f),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = .35f))) {
        Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
            Column(Modifier.weight(1f)) { Text(title, style = MaterialTheme.typography.titleMedium); Text(subtitle, style = MaterialTheme.typography.bodySmall) }
            Icon(Icons.Outlined.ChevronRight, null)
        }
    }
}

@Composable private fun ChoiceRow(title: String, selected: Boolean, choose: () -> Unit) {
    Surface(onClick = choose, shape = RoundedCornerShape(16.dp), color = if(selected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface.copy(alpha = .8f)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp).heightIn(min = 52.dp), verticalAlignment = Alignment.CenterVertically) {
            RadioButton(selected, choose); Text(title, Modifier.weight(1f))
        }
    }
}

@Composable private fun DevicePermissions(state: NativeState, model: NativeWorkbenchModel) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    var revision by remember { mutableIntStateOf(0) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if(event == Lifecycle.Event.ON_RESUME) revision++ }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    val mic = remember(revision) { context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED }
    val notifications = remember(revision) { context.getSystemService(NotificationManager::class.java).areNotificationsEnabled() &&
        (Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) }
    val requestNotification = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        revision++; if(granted) model.setDailyReminder(true) else model.report("通知未获准，每日提醒保持关闭。")
    }
    LaunchedEffect(notifications, state.dailyReminder) { if(!notifications && state.dailyReminder) model.setDailyReminder(false) }
    Text("设备权限与提醒", style = MaterialTheme.typography.headlineMedium)
    Text("麦克风：${if(mic) "已允许" else "未允许"}", style = MaterialTheme.typography.titleMedium)
    Text("只有主动录音时才使用麦克风；拒绝后仍可浏览已授权故事。", style = MaterialTheme.typography.bodySmall)
    OutlinedButton(onClick = {
        runCatching { context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))) }
            .onFailure { model.report("系统设置暂时无法打开，请在手机设置中管理应用权限。") }
    }) { Text("打开系统权限设置") }
    Text("通知：${if(notifications) "已允许" else "未允许或系统已关闭"}", style = MaterialTheme.typography.titleMedium)
    if(state.owner) Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) { Text("每日提醒"); Text("上午 9 点左右的通用本机通知，不含私密内容，不调用模型。", style = MaterialTheme.typography.bodySmall) }
        Switch(state.dailyReminder, { enabled ->
            if(!enabled) model.setDailyReminder(false)
            else if(Build.VERSION.SDK_INT >= 33 && !notifications) requestNotification.launch(Manifest.permission.POST_NOTIFICATIONS)
            else model.setDailyReminder(true)
        }, enabled = !state.busy && !state.recording)
    }
    Text("提醒默认关闭；退出、换号或切换空间会取消。系统电池策略可能延迟通知。", style = MaterialTheme.typography.bodySmall)
    Text("亲友能看哪些内容，请到“亲友与分享”管理；这与手机系统权限不同。", style = MaterialTheme.typography.bodySmall)
}

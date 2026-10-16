package me.remember.app.integration

import android.Manifest
import android.bluetooth.BluetoothManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import me.remember.app.BuildConfig
import me.remember.app.hardware.*
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun Work3200Screen(model: NativeWorkbenchModel, compact: Boolean = false, onManage: () -> Unit = {}, condensed: Boolean = false) = Work3200Panel(model.recorder(), compact, onManage, condensed)

@Composable
internal fun Work3200Panel(controller: Work3200Controller, compact: Boolean = false, onManage: () -> Unit = {}, condensed: Boolean = false) {
    val context = LocalContext.current
    val state by controller.ui.collectAsState()
    val view = LocalView.current
    var filesExpanded by remember { mutableStateOf(false) }
    var downloadsExpanded by remember { mutableStateOf(false) }
    var diagnostics by remember { mutableStateOf(false) }
    DisposableEffect(state.busy, view) {
        val previous = view.keepScreenOn
        if (state.busy in setOf("download", "verify")) view.keepScreenOn = true
        onDispose { view.keepScreenOn = previous }
    }
    val permissionNames = remember { if (Build.VERSION.SDK_INT >= 31)
        arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION) }
    val enableBluetooth = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        controller.notice("蓝牙已处理。请点击准备连接继续。")
    }
    fun prepare() {
        val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
        when {
            adapter == null -> controller.notice("这台设备没有可用的蓝牙适配器。")
            !adapter.isEnabled -> enableBluetooth.launch(Intent(android.bluetooth.BluetoothAdapter.ACTION_REQUEST_ENABLE))
            else -> { controller.keepConnectedInBackground(); controller.authorize() }
        }
    }
    val permissions = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        if (permissionNames.all { context.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }) prepare() else controller.notice("需要允许“附近的设备”权限才能扫描连接。可在系统设置 → 应用 → 勿忘我 → 权限中开启。")
    }
    val requestFile = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let { controller.export(it, request = true) } }
    val importFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { controller.importGrant(it) } }
    val reportFile = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let { controller.export(it) } }
    var exporting by remember { mutableStateOf<HardwareDownloadReceipt?>(null) }
    val exportFile = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        val receipt = exporting; exporting = null
        if (uri != null && receipt != null) controller.export(uri, receipt)
    }
    val idle = state.busy.isEmpty()
    if(compact) {
        RecorderCaptureSummary(state, controller, onManage, condensed)
        return
    }
    val active=state.recordPhase in setOf(DeviceRecordPhase.RECORDING,DeviceRecordPhase.PAUSED)
    val scanning = state.busy == "scan"
    val selecting = !state.connected && state.busy != "connect" && state.nearby.isNotEmpty()
    val connectionFlow = !state.connected && (state.busy in setOf("auth", "scan", "connect") || selecting)
    RecorderProductHero(searching = scanning, compact = selecting)
    if(!state.connected) {
        Text(if(state.busy == "connect") "正在连接" else if(selecting) "选择录音豆" else if(scanning) "正在搜索设备" else "soundcore Work", style=MaterialTheme.typography.headlineSmall)
        if(scanning && !selecting) Text("请将录音豆靠近手机", style=MaterialTheme.typography.bodyLarge)
    }
    if(state.connected) RecorderDeviceStatusRow(state)
    if(active) Text("${if(state.recordPhase==DeviceRecordPhase.PAUSED) "已暂停" else "正在录音"} · ${clock(state.elapsedMs)}",style=MaterialTheme.typography.titleMedium)
    if (!BuildConfig.SOUNDCORE_ENABLED) Text("当前安装包未包含录音豆 SDK，请安装设备联调版。", color = MaterialTheme.colorScheme.error)
    val routineMessage=listOf("录音豆正在采集声音", "录音豆已暂停", "设备正在录音", "已连接录音豆。", "设备已确认绑定", "设备已就绪", "录音已保存到手机", "已保存，正在转文字", "播放结束", "正在播放原音", "蓝牙已恢复").any {state.message.startsWith(it)}
    val connectionPrompt = state.message.startsWith("开启手机蓝牙") || state.message.startsWith("录音豆授权成功") || state.message.startsWith("扫描结束，请选择")
    if(!scanning && state.busy != "connect" && !connectionPrompt && (!idle || !state.connected || !state.bound || !routineMessage)) Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(when(state.busy) { "download" -> "正在同步录音"; "verify","decode" -> "正在准备转文字"; "list" -> "正在读取设备录音"; else -> state.message })
            if (!idle) key(state.busy, state.recordingFileId) { RecorderProgress(state.percent) }
        }
    }
    if (!state.authorized) Button(onClick = {
        if (permissionNames.any { context.checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }) permissions.launch(permissionNames)
        else prepare()
    }, enabled = idle && BuildConfig.SOUNDCORE_ENABLED, modifier = Modifier.fillMaxWidth()) { Text("准备连接") }
    if (state.authorized && !state.connected && !state.reconnecting) {
        if(idle) Button(onClick = controller::scan, modifier = Modifier.fillMaxWidth()) { Text(if(selecting) "重新搜索" else "搜索录音豆") }
        (if(state.busy == "connect") emptyList() else state.nearby).forEach { device ->
            NearbyRecorderCard(device, enabled = idle || scanning) { controller.connect(device) }
        }
        if (scanning) TextButton(onClick = controller::stopScan) { Text("停止搜索") }
    }
    if (state.connected) {
        if (!state.bound) OutlinedButton(onClick = controller::bind, enabled = idle, modifier = Modifier.fillMaxWidth()) { Text("首次使用：绑定这颗录音豆") }
        RecorderMenuRow(if(state.listComplete) "设备录音 ${state.files.size}" else "设备录音", Icons.Outlined.GraphicEq, filesExpanded) {
            filesExpanded=!filesExpanded; if(filesExpanded && !active && idle) controller.listFiles()
        }
        if(filesExpanded) OutlinedButton(onClick=controller::listFiles,enabled=idle && !active) {Text("刷新列表")}
        if (state.recordPhase == DeviceRecordPhase.ENDED && idle && state.downloads.none { it.fileId==state.recordingFileId }) OutlinedButton(onClick = controller::retrySync) { Text("重试同步") }
    }
    if (state.needsGrant) {
        Text("授权服务尚未就绪时", style = MaterialTheme.typography.titleMedium)
        Text("导出本机申请给开发人员，再导入对应的短期授权文件。无需填写密钥或开启 USB 调试。")
        OutlinedButton(onClick = { requestFile.launch("remember-device-request.json") }, enabled = idle) { Text("导出本机授权申请") }
        OutlinedButton(onClick = { importFile.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }, enabled = idle) { Text("导入授权文件") }
    }
    (if (filesExpanded) state.files else emptyList()).forEach { file ->
        Surface(shape = MaterialTheme.shapes.medium, tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(12.dp)) {
                Text(recordingTime(file.fileId), style = MaterialTheme.typography.titleMedium)
                Text("${file.durationMs / 1000} 秒 · 设备文件 ${recorderMegabytes(file.sizeBytes.toLong())}")
                Button(onClick = { controller.download(file) }, enabled = idle && !active && state.listComplete && file.code == 0 && file.sizeBytes > 0) { Text("下载到手机") }
                RecorderFileActions(controller,state,file)
                if (file.code != 0) Text("设备暂不允许下载此文件（${file.code}）。")
            }
        }
    }
    if(!connectionFlow && (state.connected || state.downloads.isNotEmpty())) RecorderMenuRow("手机原音 ${state.downloads.size}", Icons.Outlined.PhoneAndroid, downloadsExpanded) {downloadsExpanded=!downloadsExpanded}
    (if (downloadsExpanded) state.downloads else emptyList()).forEach { receipt ->
        Surface(shape = MaterialTheme.shapes.medium, tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(recordingTime(receipt.fileId), style = MaterialTheme.typography.titleMedium)
                Text(recorderMegabytes(receipt.bytes))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { controller.play(receipt) }, enabled = idle && !state.playing) { Text("手机试听") }
                    OutlinedButton(onClick = { exporting = receipt; exportFile.launch("recording-${receipt.fileId}.raw") }, enabled = idle) { Text("导出原文件") }
                }
                state.savedMarks[receipt.importId].orEmpty().forEach { mark ->
                    TextButton(onClick = { controller.play(receipt, mark.offsetMs) }, enabled = idle) {
                        Text("重点 ${clock(mark.offsetMs)} · ${if (mark.origin == "device") "设备标记" else "手机添加"} · 从这里听")
                    }
                }
            }
        }
    }
    if (state.playing) OutlinedButton(onClick = controller::stopPlayback) { Text("停止播放") }
    if(state.connected) RecorderMaintenancePanel(controller,state)
    if(!connectionFlow) RecorderMenuRow("连接帮助", Icons.Outlined.HelpOutline, diagnostics) {diagnostics=!diagnostics}
    if(diagnostics) TextButton(onClick = { reportFile.launch("remember-device-diagnostics.json") }, enabled = idle) { Text("导出连接与下载记录") }
    if (state.connected || (!idle && !scanning)) TextButton(onClick = { controller.disconnect() },enabled=state.maintenanceAction!=RecorderCommand.OTA) { Text(if(idle) "断开连接" else "取消当前操作") }
}

@Composable private fun RecorderCaptureSummary(state: RecorderUi, controller: Work3200Controller, manage: () -> Unit, condensed: Boolean) {
    val active=state.recordPhase in setOf(DeviceRecordPhase.RECORDING,DeviceRecordPhase.PAUSED)
    val saved=state.downloads.any { it.fileId==state.recordingFileId }
    val syncFailed=state.recordPhase==DeviceRecordPhase.ENDED && !saved && state.busy.isEmpty() &&
        listOf("未完成","失败","无法","重试","未收到","超时").any { state.message.contains(it) }
    val awaitingFile=state.recordPhase==DeviceRecordPhase.ENDED && !saved && !syncFailed
    if(condensed && !active && !syncFailed && state.busy.isEmpty()) {
        Surface(shape=MaterialTheme.shapes.large,color=MaterialTheme.colorScheme.surface.copy(alpha=.94f)) {
            Row(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=4.dp),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=androidx.compose.ui.Alignment.CenterVertically) {
                Text(if(state.connected && state.bound) "录音豆 · 已连接" else "录音豆",style=MaterialTheme.typography.titleMedium)
                TextButton(onClick=manage) { Text(if(state.connected) "设备" else "连接") }
            }
        }
        return
    }
    Surface(shape=MaterialTheme.shapes.extraLarge,color=MaterialTheme.colorScheme.surface.copy(alpha=.94f)) {
        Column(Modifier.fillMaxWidth().padding(24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=androidx.compose.ui.Alignment.CenterVertically) {
                Text(if(state.connected && state.bound) "录音豆 · 已连接" else if(state.reconnecting) "正在重连" else "录音豆",style=MaterialTheme.typography.titleMedium)
                TextButton(onClick=manage) { Text("设备") }
            }
            Text(when {
                state.recordPhase==DeviceRecordPhase.RECORDING -> "正在录音"
                state.recordPhase==DeviceRecordPhase.PAUSED -> "录音已暂停"
                state.busy=="download" -> "收到录音，正在同步"
                state.busy in setOf("verify","decode") -> "已收到，正在准备转文字"
                awaitingFile -> "正在接收录音"
                state.recordPhase==DeviceRecordPhase.UNKNOWN -> "连接恢复后确认录音状态"
                !state.connected || !state.bound -> "连接后，就可以开始了"
                saved -> "录音已保存"
                else -> "按下录音豆，开始记录"
            },style=MaterialTheme.typography.headlineSmall)
            if(active) Text(clock(state.elapsedMs),style=MaterialTheme.typography.displayMedium)
            if(state.busy in setOf("download","verify","decode","list") || awaitingFile) {
                key(state.busy, state.recordingFileId) { RecorderProgress(state.percent) }
            } else if(!active && !saved && state.connected && state.bound && !syncFailed) Text("录完自动转文字",style=MaterialTheme.typography.bodyLarge)
            if(active) Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) { DeviceMarkerStatus(state) }
                TextButton(onClick={controller.runCommand(if(state.recordPhase==DeviceRecordPhase.RECORDING) RecorderCommand.PAUSE else RecorderCommand.RESUME)},enabled=state.busy.isEmpty()) {
                    Text(if(state.recordPhase==DeviceRecordPhase.RECORDING) "暂停" else "继续")
                }
            }
            if(!state.connected || !state.bound) Button(onClick=manage,modifier=Modifier.fillMaxWidth()) { Text(if(state.connected) "完成绑定" else "连接录音豆") }
            if(syncFailed) {
                Text("本段同步未完成，原音仍在录音豆。",color=MaterialTheme.colorScheme.error)
                OutlinedButton(onClick=controller::retrySync,enabled=state.connected) { Text("重试同步") }
            }
        }
    }
}

@Composable internal fun RecorderDeviceStatusRow(state: RecorderUi) {
    Row(Modifier.fillMaxWidth().testTag("recorder-status-row"),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        Text(if(state.connected) "已连接" else "未连接",style=MaterialTheme.typography.labelLarge)
        Text("电量 ${state.batteryPercent?.let {"$it%"} ?: "—"}",style=MaterialTheme.typography.labelLarge)
        val free=state.storageFreeFraction
        if(free!=null) {
            LinearProgressIndicator(progress={free},modifier=Modifier.weight(1f).height(6.dp))
            Text("余 ${String.format(java.util.Locale.ROOT,"%.1f",free*100)}%",style=MaterialTheme.typography.labelLarge)
        } else Text("空间 —",style=MaterialTheme.typography.labelLarge)
    }
}

@Composable private fun DeviceMarkerStatus(state: RecorderUi) {
    val count=state.recordMarks.count {it.origin=="device"}
    Text(when {count>0 -> "设备重点 $count 处";state.realtimeMarked -> "已收到重点标记";else -> "双敲机身标重点"},style=MaterialTheme.typography.bodyLarge)
}

private fun recordingTime(id: Int): String = runCatching {
    DateTimeFormatter.ofPattern("MM-dd HH:mm:ss").withZone(ZoneId.systemDefault()).format(Instant.ofEpochSecond(id.toLong()))
}.getOrDefault("录音 $id")

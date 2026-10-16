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
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
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
    var manage by remember { mutableStateOf(!compact) }
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
    Text(if (compact) "录音豆录音" else "连接录音豆", style = MaterialTheme.typography.headlineMedium)
    if (!state.connected) Text("连接后按录音豆上的按钮开始和结束，声音由录音豆采集。")
    if (state.connected || state.recordPhase != DeviceRecordPhase.IDLE) {
        val label = when(state.recordPhase) {
            DeviceRecordPhase.RECORDING -> "录音豆正在录音"
            DeviceRecordPhase.PAUSED -> "录音豆已暂停"
            DeviceRecordPhase.ENDED -> "录音已结束"
            DeviceRecordPhase.UNKNOWN -> "设备录音状态待确认"
            DeviceRecordPhase.IDLE -> "录音豆待命"
        }
        Text(label, style = MaterialTheme.typography.titleLarge)
        if (state.recordPhase in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED, DeviceRecordPhase.ENDED))
            Text(clock(state.elapsedMs), style = MaterialTheme.typography.displaySmall)
        if (state.recordPhase in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED)) {
            Text("连接期间持续计时，结束后按设备文件校准时长。", style = MaterialTheme.typography.bodySmall)
            Text("按录音豆按钮结束后，本段会自动同步到手机。")
            OutlinedButton(onClick = controller::addMark) { Text("标记重点 · ${state.recordMarks.size}") }
            OutlinedButton(onClick = { controller.runCommand(if(state.recordPhase==DeviceRecordPhase.RECORDING) RecorderCommand.PAUSE else RecorderCommand.RESUME) }, enabled=state.busy.isEmpty()) {
                Text(if(state.recordPhase==DeviceRecordPhase.RECORDING) "暂停录音豆" else "恢复录音豆录音")
            }
            Text("手机添加的重点保存在本 App；设备重点在回传后显示。", style = MaterialTheme.typography.bodySmall)
        }
        if (state.realtimeMarked) Text("已收到设备重点标记，准确时间将在文件同步后显示。")
    }
    if (!BuildConfig.SOUNDCORE_ENABLED) Text("当前安装包未包含录音豆 SDK，请安装设备联调版。", color = MaterialTheme.colorScheme.error)
    Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(state.message)
            if (!idle) state.percent?.let { LinearProgressIndicator(progress = { it / 100f }, modifier = Modifier.fillMaxWidth()) }
                ?: LinearProgressIndicator(Modifier.fillMaxWidth())
            if (state.progress.isNotEmpty()) Text(state.progress)
        }
    }
    if (!state.authorized) Button(onClick = {
        if (permissionNames.any { context.checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }) permissions.launch(permissionNames)
        else prepare()
    }, enabled = idle && BuildConfig.SOUNDCORE_ENABLED, modifier = Modifier.fillMaxWidth()) { Text("准备连接") }
    if (state.authorized && !state.connected && !state.reconnecting) {
        Button(onClick = controller::scan, enabled = idle, modifier = Modifier.fillMaxWidth()) { Text("扫描附近录音豆") }
        if (state.busy == "scan") OutlinedButton(onClick = controller::stopScan) { Text("停止扫描") }
        state.nearby.forEach { device ->
            OutlinedButton(onClick = { controller.connect(device) }, enabled = idle || state.busy == "scan", modifier = Modifier.fillMaxWidth()) {
                Text("${device.name} · ${device.product}\n${device.mac.takeLast(5)} · 连接")
            }
        }
    }
    if (state.connected) {
        Text("已连接：${state.device?.name}", style = MaterialTheme.typography.titleMedium)
        Text(state.deviceInfo.ifBlank { "正在等待设备返回电量和固件信息…" })
        if (!state.bound) OutlinedButton(onClick = controller::bind, enabled = idle, modifier = Modifier.fillMaxWidth()) { Text("首次使用：绑定这颗录音豆") }
        if (compact) TextButton(onClick = { manage = !manage }) { Text(if (manage) "收起设备录音" else "设备录音与连接管理") }
        if (manage) Button(onClick = controller::listFiles, enabled = idle, modifier = Modifier.fillMaxWidth()) { Text("读取 / 刷新设备录音") }
        if (manage) RecorderMaintenancePanel(controller,state)
        if (state.recordPhase == DeviceRecordPhase.ENDED && idle && state.downloads.none { it.fileId==state.recordingFileId }) OutlinedButton(onClick = controller::retrySync) { Text("重试同步") }
    }
    if ((manage || !state.connected) && (state.connected || !idle || state.authorized)) TextButton(onClick = { controller.disconnect() },enabled=state.maintenanceAction!=RecorderCommand.OTA) { Text("断开 / 取消当前操作") }
    if (state.needsGrant) {
        Text("授权服务尚未就绪时", style = MaterialTheme.typography.titleMedium)
        Text("导出本机申请给开发人员，再导入对应的短期授权文件。无需填写密钥或开启 USB 调试。")
        OutlinedButton(onClick = { requestFile.launch("remember-device-request.json") }, enabled = idle) { Text("导出本机授权申请") }
        OutlinedButton(onClick = { importFile.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }, enabled = idle) { Text("导入授权文件") }
    }
    if (manage && state.files.isNotEmpty()) Text("设备上的录音", style = MaterialTheme.typography.titleLarge)
    (if (manage) state.files else emptyList()).forEach { file ->
        Surface(shape = MaterialTheme.shapes.medium, tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(12.dp)) {
                Text(recordingTime(file.fileId), style = MaterialTheme.typography.titleMedium)
                Text("${file.durationMs / 1000} 秒 · 设备文件 ${recorderMegabytes(file.sizeBytes.toLong())}")
                Button(onClick = { controller.download(file) }, enabled = idle && state.listComplete && file.code == 0 && file.sizeBytes > 0) { Text("下载到手机") }
                RecorderFileActions(controller,state,file)
                if (file.code != 0) Text("设备暂不允许下载此文件（${file.code}）。")
            }
        }
    }
    Text("手机已保存：${state.downloads.size} 段", style = MaterialTheme.typography.titleLarge)
    (if (compact && !manage) state.downloads.take(1) else state.downloads).forEach { receipt ->
        Surface(shape = MaterialTheme.shapes.medium, tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(recordingTime(receipt.fileId), style = MaterialTheme.typography.titleMedium)
                Text("来源：录音豆 · 已保存到本机")
                if (!compact) Text("实际 ${recorderMegabytes(receipt.bytes)} · 校验 ${receipt.sha256.take(16)}…")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { controller.play(receipt) }, enabled = idle && !state.playing) { Text("手机试听") }
                    OutlinedButton(onClick = { exporting = receipt; exportFile.launch("recording-${receipt.fileId}.raw") }, enabled = idle) { Text("导出原文件") }
                }
                state.savedMarks[receipt.importId].orEmpty().forEach { mark ->
                    TextButton(onClick = { controller.play(receipt, mark.offsetMs) }, enabled = idle) {
                        Text("重点 ${clock(mark.offsetMs)} · ${if (mark.origin == "device") "设备标记" else "手机添加"} · 从这里听")
                    }
                }
                if (compact) Text("下方可确认上传并转成文字；也可在“档案 → 我的录音”中继续。", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
    if (state.playing) OutlinedButton(onClick = controller::stopPlayback) { Text("停止播放") }
    Text("新录音同步后自动转文字，设备原文件保留。", style = MaterialTheme.typography.bodySmall)
    TextButton(onClick = { reportFile.launch("remember-device-diagnostics.json") }, enabled = idle) { Text("导出连接与下载记录") }
}

@Composable private fun RecorderCaptureSummary(state: RecorderUi, controller: Work3200Controller, manage: () -> Unit, condensed: Boolean) {
    val active=state.recordPhase in setOf(DeviceRecordPhase.RECORDING,DeviceRecordPhase.PAUSED)
    val saved=state.downloads.any { it.fileId==state.recordingFileId }
    val syncFailed=state.recordPhase==DeviceRecordPhase.ENDED && !saved && state.busy.isEmpty() &&
        listOf("未完成","失败","无法","重试","未收到","超时").any { state.message.contains(it) }
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
                state.recordPhase==DeviceRecordPhase.RECORDING -> "正在记录这一刻"
                state.recordPhase==DeviceRecordPhase.PAUSED -> "录音已暂停"
                state.busy=="download" -> "收到录音，正在同步"
                state.busy=="verify" -> "正在准备录音"
                state.recordPhase==DeviceRecordPhase.UNKNOWN -> "连接恢复后确认录音状态"
                !state.connected || !state.bound -> "连接后，就可以开始了"
                else -> "按录音豆，留下一段声音"
            },style=MaterialTheme.typography.headlineSmall)
            if(active) Text(clock(state.elapsedMs),style=MaterialTheme.typography.displayMedium)
            if(state.busy in setOf("download","verify","list")) {
                state.percent?.let { LinearProgressIndicator(progress={it/100f},modifier=Modifier.fillMaxWidth()) }
                    ?: LinearProgressIndicator(Modifier.fillMaxWidth())
                if(state.progress.isNotBlank()) Text(state.progress,style=MaterialTheme.typography.bodyMedium)
            } else if(!active && state.connected && state.bound) Text("录完自动转文字",style=MaterialTheme.typography.bodyLarge)
            if(active) Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick=controller::addMark) { Text("标记重点${if(state.recordMarks.isNotEmpty()) " · ${state.recordMarks.size}" else ""}") }
                TextButton(onClick={controller.runCommand(if(state.recordPhase==DeviceRecordPhase.RECORDING) RecorderCommand.PAUSE else RecorderCommand.RESUME)},enabled=state.busy.isEmpty()) {
                    Text(if(state.recordPhase==DeviceRecordPhase.RECORDING) "暂停" else "继续")
                }
            }
            if(active && state.realtimeMarked) Text("已收到重点标记",color=MaterialTheme.colorScheme.primary)
            if(!state.connected || !state.bound) Button(onClick=manage,modifier=Modifier.fillMaxWidth()) { Text(if(state.connected) "完成绑定" else "连接录音豆") }
            if(syncFailed) {
                Text("本段同步未完成，原音仍在录音豆。",color=MaterialTheme.colorScheme.error)
                OutlinedButton(onClick=controller::retrySync,enabled=state.connected) { Text("重试同步") }
            }
        }
    }
}

private fun recordingTime(id: Int): String = runCatching {
    DateTimeFormatter.ofPattern("MM-dd HH:mm:ss").withZone(ZoneId.systemDefault()).format(Instant.ofEpochSecond(id.toLong()))
}.getOrDefault("录音 $id")

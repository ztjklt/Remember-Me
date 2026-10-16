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
fun Work3200Screen(model: NativeWorkbenchModel) {
    val context = LocalContext.current
    val identity = model.hardwareScope()
    val controller = remember(identity) { Work3200Controller(context, identity, model::hardwareGrant) }
    val state by controller.ui.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val view = LocalView.current
    DisposableEffect(controller, lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { controller.stopPlayback(); controller.disconnect("已离开前台，连接已关闭。返回后可重新连接，已保存文件保留在手机。") }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); controller.close() }
    }
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
            else -> controller.authorize()
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
    Text("连接录音豆", style = MaterialTheme.typography.headlineMedium)
    Text("连接设备 → 绑定确认 → 下载录音 → 手机试听", style = MaterialTheme.typography.bodyMedium)
    Text("首次联调建议用设备按键录制约 30 秒并结束，再来这里下载。请保持此页面打开。")
    if (!BuildConfig.SOUNDCORE_ENABLED) Text("当前安装包未包含录音豆 SDK，请安装设备联调版。", color = MaterialTheme.colorScheme.error)
    Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(state.message)
            if (!idle) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (state.progress.isNotEmpty()) Text(state.progress)
        }
    }
    if (!state.authorized) Button(onClick = {
        if (permissionNames.any { context.checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }) permissions.launch(permissionNames)
        else prepare()
    }, enabled = idle && BuildConfig.SOUNDCORE_ENABLED, modifier = Modifier.fillMaxWidth()) { Text("准备连接") }
    if (state.authorized && !state.connected) {
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
        OutlinedButton(onClick = controller::bind, enabled = idle, modifier = Modifier.fillMaxWidth()) { Text("首次使用：绑定这颗录音豆") }
        Button(onClick = controller::listFiles, enabled = idle, modifier = Modifier.fillMaxWidth()) { Text("读取 / 刷新设备录音") }
    }
    if (state.connected || !idle || state.authorized) TextButton(onClick = { controller.disconnect() }) { Text("断开 / 取消当前操作") }
    if (state.needsGrant) {
        Text("授权服务尚未就绪时", style = MaterialTheme.typography.titleMedium)
        Text("导出本机申请给开发人员，再导入对应的短期授权文件。无需填写密钥或开启 USB 调试。")
        OutlinedButton(onClick = { requestFile.launch("remember-device-request.json") }, enabled = idle) { Text("导出本机授权申请") }
        OutlinedButton(onClick = { importFile.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }, enabled = idle) { Text("导入授权文件") }
    }
    if (state.files.isNotEmpty()) Text("设备上的录音", style = MaterialTheme.typography.titleLarge)
    state.files.forEach { file ->
        Surface(shape = MaterialTheme.shapes.medium, tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(12.dp)) {
                Text(recordingTime(file.fileId), style = MaterialTheme.typography.titleMedium)
                Text("${file.durationMs / 1000} 秒 · 设备标记 ${file.sizeBytes} 字节")
                Button(onClick = { controller.download(file) }, enabled = idle && state.listComplete && file.code == 0 && file.sizeBytes > 0) { Text("下载到手机") }
                if (file.code != 0) Text("设备暂不允许下载此文件（${file.code}）。")
            }
        }
    }
    Text("手机已保存：${state.downloads.size} 段", style = MaterialTheme.typography.titleLarge)
    state.downloads.forEach { receipt ->
        Surface(shape = MaterialTheme.shapes.medium, tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(recordingTime(receipt.fileId), style = MaterialTheme.typography.titleMedium)
                Text("实际 ${receipt.bytes} 字节 · 校验 ${receipt.sha256.take(16)}…")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { controller.play(receipt) }, enabled = idle && !state.playing) { Text("手机试听") }
                    OutlinedButton(onClick = { exporting = receipt; exportFile.launch("recording-${receipt.fileId}.raw") }, enabled = idle) { Text("导出原文件") }
                }
            }
        }
    }
    if (state.playing) OutlinedButton(onClick = controller::stopPlayback) { Text("停止播放") }
    Text("下载后先试听核对。此页不会自动上传，也不会删除录音豆里的文件。", style = MaterialTheme.typography.bodySmall)
    TextButton(onClick = { reportFile.launch("remember-device-diagnostics.json") }, enabled = idle) { Text("导出连接与下载记录") }
}

private fun recordingTime(id: Int): String = runCatching {
    DateTimeFormatter.ofPattern("MM-dd HH:mm:ss").withZone(ZoneId.systemDefault()).format(Instant.ofEpochSecond(id.toLong()))
}.getOrDefault("录音 $id")

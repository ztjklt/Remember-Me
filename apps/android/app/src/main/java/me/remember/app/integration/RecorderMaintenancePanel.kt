package me.remember.app.integration

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import me.remember.app.hardware.*

@Composable internal fun RecorderFileActions(controller: Work3200Controller,state: RecorderUi,file: DeviceRecording) {
    val context=LocalContext.current
    var deleting by remember(state.device?.key,file.fileId) { mutableStateOf(false) }
    val permissions=if(Build.VERSION.SDK_INT>=33) arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION,Manifest.permission.NEARBY_WIFI_DEVICES) else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION)
    val request=rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        if(permissions.all { context.checkSelfPermission(it)==PackageManager.PERMISSION_GRANTED }) controller.download(file,true)
        else controller.notice("Wi-Fi 下载需要允许附近 Wi-Fi 和位置权限；仍可选择蓝牙下载。")
    }
    val idle=state.busy.isEmpty() && state.recordPhase !in setOf(DeviceRecordPhase.RECORDING,DeviceRecordPhase.PAUSED)
    OutlinedButton(onClick={
        if(permissions.all { context.checkSelfPermission(it)==PackageManager.PERMISSION_GRANTED }) controller.download(file,true) else request.launch(permissions)
    },enabled=idle && state.listComplete && file.code==0 && file.sizeBytes>0) { Text("通过 Wi-Fi 下载") }
    TextButton(onClick={deleting=true},enabled=idle) { Text("删除设备上的此段录音") }
    if(deleting) AlertDialog(onDismissRequest={deleting=false},title={Text("删除录音豆上的原文件？")},
        text={Text("将删除设备文件 ${file.fileId}（${file.durationMs/1000} 秒）。请先确认手机已有可播放的副本。设备删除无法撤销。")},
        confirmButton={TextButton(onClick={deleting=false;controller.runCommand(RecorderCommand.DELETE_RECORDING,file.fileId)}) { Text("确认删除设备原文件") }},
        dismissButton={TextButton(onClick={deleting=false}) { Text("保留") }})
}

@Composable internal fun RecorderMaintenancePanel(controller: Work3200Controller,state: RecorderUi) {
    var expanded by remember { mutableStateOf(false) }
    var confirmation by remember(state.device?.key) { mutableStateOf<Pair<String,()->Unit>?>(null) }
    val firmware=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(controller::importFirmware) }
    val logs=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri -> uri?.let(controller::exportDeviceLogs) }
    RecorderMenuRow("设备设置", Icons.Outlined.Settings, expanded) {expanded=!expanded}
    if(expanded) {
        Text(state.deviceInfo.ifBlank {"固件未返回"})
        Text("传输：${state.maintenance.channel}")
        if(state.maintenance.livePackets>0) Text("实时音频 ${recorderMegabytes(state.maintenance.liveBytes)}")
        val d=state.maintenance.details
        Text("SDK：${state.maintenance.sdk.ifBlank { "尚未返回" }}",style=MaterialTheme.typography.bodySmall)
        Text("序列号：${d.serial.ifBlank { "未返回" }}\nWi-Fi 固件：${d.wifiFirmware.ifBlank { "未返回" }}\n充电盒固件：${d.boxFirmware.ifBlank { "未返回" }}")
        Text("充电盒电量：${d.boxBattery?.toString() ?: "未返回"}（设备原始值）\n录音豆充电：${d.charging?.let { if(it) "是" else "否" } ?: "未知"}")
        if(state.maintenance.result.isNotBlank()) Text(state.maintenance.result)
        val idle=state.busy.isEmpty() && state.recordPhase !in setOf(DeviceRecordPhase.RECORDING,DeviceRecordPhase.PAUSED)
        fun confirm(text:String,command:RecorderCommand,id:Int=0) { confirmation=text to {controller.runCommand(command,id)} }
        OutlinedButton(onClick={controller.runCommand(RecorderCommand.SYNC_TIME)},enabled=idle) { Text("同步设备时间") }
        OutlinedButton(onClick={confirm("开启设备 Find My 功能？此开关不等于在本 App 显示设备地图。",RecorderCommand.FIND_MY_ON)},enabled=idle) { Text("开启 Find My") }
        OutlinedButton(onClick={confirm("关闭设备 Find My 功能？",RecorderCommand.FIND_MY_OFF)},enabled=idle) { Text("关闭 Find My") }
        OutlinedButton(onClick={controller.runCommand(RecorderCommand.LOG_LIST)},enabled=idle) { Text("读取设备日志列表") }
        Text("日志采集：${state.maintenance.collecting?.let { if(it) "开启" else "关闭" } ?: "尚未读取"}")
        OutlinedButton(onClick={confirm("开启设备诊断日志采集？需要排障时使用，录音内容不会因此自动上传。",RecorderCommand.LOG_ENABLE)},enabled=idle) { Text("开启日志采集") }
        OutlinedButton(onClick={controller.runCommand(RecorderCommand.LOG_DISABLE)},enabled=idle) { Text("关闭日志采集") }
        state.maintenance.logs.forEach { log ->
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                TextButton(onClick={controller.runCommand(RecorderCommand.LOG_DOWNLOAD,log.id)},enabled=idle) { Text("下载日志 ${log.id}") }
                TextButton(onClick={confirm("删除设备日志 ${log.id}？",RecorderCommand.LOG_DELETE,log.id)},enabled=idle) { Text("删除") }
            }
        }
        if(state.maintenanceAction==RecorderCommand.LOG_DOWNLOAD) TextButton(onClick=controller::stopLogTransfer) { Text("停止日志下载") }
        OutlinedButton(onClick={logs.launch("remember-recorder-logs.zip")},enabled=idle) { Text("导出已下载设备日志") }
        Text("固件升级需官方 D3200 固件、目标版本及校验资料。请先整理为应用要求的 ZIP 包；不会自动查找或刷入未知固件。",style=MaterialTheme.typography.bodySmall)
        OutlinedButton(onClick={firmware.launch(arrayOf("application/zip","application/octet-stream"))},enabled=idle) { Text("导入官方固件资料包") }
        state.maintenance.firmware?.let { f ->
            Text("待升级：蓝牙 ${f.btVersion ?: "无"} / Wi-Fi ${f.wifiVersion ?: "无"}")
            OutlinedButton(onClick={confirm("确认这些固件来自官方且匹配当前录音豆，保持设备电量充足并在升级完成前不退出 App？",RecorderCommand.OTA)},enabled=idle) { Text("确认并升级固件") }
        }
        TextButton(onClick={confirm("解除这颗录音豆的绑定？需要再次绑定才能继续使用。手机上已保存的录音保留。",RecorderCommand.UNBIND)},enabled=idle) { Text("解除设备绑定") }
        TextButton(onClick={confirm("重置这颗录音豆？此操作可能清除设备数据及设置，无法撤销，请先备份设备录音。",RecorderCommand.RESET)},enabled=idle) { Text("重置设备") }
    }
    if(state.wifiTransfer) TextButton(onClick=controller::closeWifi) { Text("关闭 Wi-Fi 传输") }
    confirmation?.let { (message,action) -> AlertDialog(onDismissRequest={confirmation=null},title={Text("确认设备操作")},text={Text(message)},
        confirmButton={TextButton(onClick={confirmation=null;action()}) {Text("确认")}},
        dismissButton={TextButton(onClick={confirmation=null}) {Text("取消")}}) }
}

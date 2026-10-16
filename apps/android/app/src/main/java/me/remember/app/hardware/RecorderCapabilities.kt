package me.remember.app.hardware

import java.io.File

enum class RecorderCommand {
    SYNC_TIME, PAUSE, RESUME, FIND_MY_ON, FIND_MY_OFF, UNBIND, RESET,
    DELETE_RECORDING, LOG_LIST, LOG_ENABLE, LOG_DISABLE, LOG_DOWNLOAD, LOG_STOP, LOG_DELETE, OTA
}
data class RecorderFirmware(val btVersion: String?, val wifiVersion: String?, val btFile: File?, val wifiFile: File?)
data class RecorderLog(val id: Int, val end: Int)
data class RecorderDetails(val serial: String = "", val wifiFirmware: String = "", val boxFirmware: String = "",
    val boxBattery: Int? = null, val charging: Boolean? = null, val boxCharging: Boolean? = null)
data class RecorderMaintenance(val logs: List<RecorderLog> = emptyList(), val collecting: Boolean? = null,
    val result: String = "", val channel: String = "蓝牙", val details: RecorderDetails = RecorderDetails(),
    val firmware: RecorderFirmware? = null, val liveBytes: Long = 0, val livePackets: Long = 0, val sdk: String = "")

fun recorderCommandAllowed(command: RecorderCommand, phase: DeviceRecordPhase, busy: Boolean, transferring: Boolean): Boolean {
    if (busy) return command == RecorderCommand.LOG_STOP
    return when (command) {
        RecorderCommand.PAUSE -> phase == DeviceRecordPhase.RECORDING
        RecorderCommand.RESUME -> phase == DeviceRecordPhase.PAUSED
        else -> phase in setOf(DeviceRecordPhase.IDLE, DeviceRecordPhase.ENDED) && !transferring
    }
}

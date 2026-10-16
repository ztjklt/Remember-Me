package me.remember.app.hardware

import java.io.File

interface HardwareEvents {
    fun diagnostic(message: String) { }
    fun fileError(fileId: Int, operation: String, code: Int) { error(operation, code) }
    fun commandResult(command: RecorderCommand, success: Boolean, detail: String) { }
    fun maintenanceProgress(command: RecorderCommand, percent: Int?, detail: String, complete: Boolean) { }
    fun deviceDetails(details: RecorderDetails) { }
    fun batteryChanged(device: Int, box: Int) { }
    fun chargingChanged(device: Boolean, box: Boolean) { }
    fun deviceLogs(logs: List<RecorderLog>, collecting: Boolean) { }
    fun channel(name: String) { }
    fun sdkInfo(version: String, product: String) { }
    fun realtimeSwitch(fileId: Int) { }
    fun linkRecovering() { }
    fun audioFragment(fileId: Int, audio: ByteArray, append: Boolean, sequence: Int, marked: Boolean) { }
    fun supplement(fileId: Int, current: Int, total: Int) { }
    fun transferIdle(idle: Boolean) { }
    fun transferRejected(fileId: Int) { }
    fun recording(status: Int, durationMs: Int, fileId: Int) { }
    fun recordingDuration(durationMs: Long) { }
    fun recordingSnapshot(recording: Int?, startedAt: Int) { }
    fun bindingAdvertisement(mac: String, uuid: String, bound: Boolean) { }
    fun realtimeMarker(fileId: Int, sequence: Int) { }
    fun auth(result: HardwareAuthResult)
    fun found(productCode: String?, name: String?, mac: String?, uuid: String?)
    fun connected()
    fun disconnected(systemCode: Int?)
    fun info(battery: Int?, firmware: String?, freeKb: Int?, totalKb: Int?)
    fun binding(confirmed: Boolean)
    fun files(files: List<DeviceRecording>, complete: Boolean)
    fun transfer(fileId: Int, sdkStatus: Int)
    fun progress(fileId: Int, receivedBytes: Int, totalBytes: Int, sequenceNumber: Int, marked: Boolean)
    fun receivedSdkFile(fileId: Int, rawFile: File)
    fun markers(fileId: Int, offsetsMs: IntArray)
    fun error(operation: String, code: Int)
}

interface HardwareTransport : AutoCloseable {
    fun command(command: RecorderCommand, fileId: Int = 0, firmware: RecorderFirmware? = null) { throw UnsupportedOperationException("SDK capability unavailable") }
    fun transferWifi(recording: DeviceRecording, directory: File) { throw UnsupportedOperationException("Wi-Fi unavailable") }
    fun closeWifi() { }
    fun isTransferring(): Boolean = false
    fun logDirectory(): File? = null
    fun configureLogDirectory(directory: File) { }
    fun refreshInfo() { }
    fun realtime(directory: File) { }
    fun initialize(application: Any, credentials: Work3200Credentials)
    fun scan()
    fun stopScan()
    fun connect(address: String, id: String)
    fun bind()
    fun listFiles()
    fun transfer(recording: DeviceRecording, privateDownloadDirectory: File)
}

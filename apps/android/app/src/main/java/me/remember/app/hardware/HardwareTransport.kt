package me.remember.app.hardware

import java.io.File

interface HardwareEvents {
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

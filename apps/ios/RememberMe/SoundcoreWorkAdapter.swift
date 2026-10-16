import Foundation
#if canImport(module_spplinkKit)
@preconcurrency import module_spplinkKit
import UIKit

// The SDK calls back from its own queues. Transfer only value snapshots onto
// MainActor; never send mutable Kotlin objects across executors.
final class SoundcoreCallbacks: NSObject, SoundcoreBusinessCallback, OnReceiveScanResult, SoundcoreConnectionCallback, OnAuthResultListener, LogInterface, @unchecked Sendable {
    let event: @Sendable (SoundcoreEvent) -> Void
    private let selectionLock = NSLock()
    private var selectedMAC: String?
    private var selectedUUID: String?
    private var scanning = false
    private var markerOffsets: [Int32: Set<Int>] = [:]
    private var finalizedMarkers: Set<Int32> = []
    private var invalidMarkerFiles: Set<Int32> = []
    func select(_ device: RecordingBeanDevice?) { selectionLock.withLock {
        selectedMAC = device?.mac; selectedUUID = device?.id
        markerOffsets = [:]; finalizedMarkers = []; invalidMarkerFiles = []
    } }
    private func accepts(_ mac: String, _ uuid: String) -> Bool {
        selectionLock.withLock { selectedMAC == mac && selectedUUID == uuid }
    }
    func setScanning(_ active: Bool) { selectionLock.withLock { scanning = active } }
    init(event: @escaping @Sendable (SoundcoreEvent) -> Void) { self.event = event }
    private func publishMarkers(fileID: Int32, offsets: [Int], final: Bool) {
        guard fileID >= 0 else { return }
        let snapshot: ([Int], Bool)? = selectionLock.withLock {
            let previous = markerOffsets[fileID] ?? []
            let previouslyInvalid = invalidMarkerFiles.contains(fileID)
            if offsets.contains(where: { $0 < 0 }) { invalidMarkerFiles.insert(fileID) }
            let valid = !invalidMarkerFiles.contains(fileID)
            // Preserve malformed raw values for the consumer's conservative
            // timeline validation; silently dropping them could hide a lost
            // toggle and invert every later priority interval.
            let merged = previous.union(offsets)
            guard merged != previous || (final && !finalizedMarkers.contains(fileID)) ||
                previouslyInvalid != !valid else { return nil }
            markerOffsets[fileID] = merged
            if final { finalizedMarkers.insert(fileID) }
            return (merged.sorted(), final && valid)
        }
        if let snapshot { event(.markers(fileID: fileID, offsetsMilliseconds: snapshot.0, final: snapshot.1)) }
    }
    func onAuthResult(result: AuthResult) { event(.authenticated(result.success && result.licenseValid && !result.tokenExpired)) }
    func onScanError(result: Int32) { guard selectionLock.withLock({ scanning }) else { return }; event(.error("暂未找到录音豆，请确认设备已开机、蓝牙已允许后重试。")) }
    func onScanSuccess(device: BlueDeviceModel) {
        guard let id = device.uuid, !id.isEmpty, let mac = device.macAddress, !mac.isEmpty,
              device.productCode == "D3200" else { return }
        event(.discovered(RecordingBeanDevice(id: id, mac: mac, name: device.deviceName ?? "录音豆", product: "D3200")))
    }
    func onConnected(macAddress: String?, deviceName: String?) { guard selectionLock.withLock({ selectedMAC != nil && selectedMAC == macAddress }) else { return }; event(.connected(macAddress)) }
    func onDisconnected(macAddress: String?, systemCode: KotlinInt?, systemMsg: String?) { guard selectionLock.withLock({ selectedMAC != nil && selectedMAC == macAddress }) else { return }; event(.disconnected) }
    func onError(macAddress: String?, exception: SdkException) { guard selectionLock.withLock({ selectedMAC != nil && selectedMAC == macAddress }) else { return }; event(.error("录音豆连接未完成，请靠近设备重试。")) }
    // SDK debug logs may contain device/session data; keep them out of app logs.
    func d(tag: String?, message: String?) {}
    func e(tag: String?, message: String?) {}
    func i(tag: String?, message: String?) {}
    func v(tag: String?, message: String?) {}
    func w(tag: String?, message: String?) {}

    func onAudioRecordDuration(macAddress: String, uuid: String, durationMs: Int64) { guard accepts(macAddress, uuid) else { return }; event(.duration(Int(max(0, durationMs) / 1000))) }
    func onAudioRecordStatusChanged(macAddress: String, uuid: String, status: Int32, recordingDuration: Int32, fileID: Int32) { guard accepts(macAddress, uuid) else { return }; event(.recording(status: status, seconds: Int(max(0, recordingDuration) / 1000), fileID: fileID)) }
    func onBatteryInfoChanged(macAddress: String, uuid: String, deviceBattery: Int32, chargingBoxBattery: Int32) { guard accepts(macAddress, uuid) else { return }; event(.battery(Int(deviceBattery))) }
    func onBindingDeviceError(macAddress: String, uuid: String, errorCode: Int32) { guard accepts(macAddress, uuid) else { return }; event(.error("设备绑定未完成，请将录音器放入充电盒，闪灯时按充电盒按钮确认。")) }
    func onCloseSyncFileByWIFI(macAddress: String, uuid: String) {}
    func onConnectSPPLinkStatusChanged(macAddress: String, uuid: String, isConnect: Bool) {}
    func onConnectWIFIError(macAddress: String, uuid: String, errorCode: Int32) {}
    func onConnectWIFIStatusChanged(macAddress: String, uuid: String, status: WifiState) {}
    func onDecodeFileCompleted(macAddress: String, uuid: String, fileID: Int32, filePath: String) { guard accepts(macAddress, uuid) else { return }; event(.download(fileID: fileID, path: filePath)) }
    func onDecodeFileMarkers(macAddress: String, uuid: String, fileID: Int32, markerTimes: KotlinIntArray) {
        guard accepts(macAddress, uuid) else { return }
        publishMarkers(fileID: fileID, offsets: (0..<markerTimes.size).map { Int(markerTimes.get(index: $0)) }, final: true)
    }
    func onDeleteFileResult(macAddress: String, uuid: String, fileID: Int32, isSuccess: Bool) {}
    func onDeviceBindConfirm(macAddress: String, uuid: String) { guard accepts(macAddress, uuid) else { return }; event(.bound) }
    func onDeviceChargingStatusChanged(macAddress: String, uuid: String, deviceChargingStatus: Int32, chargingBoxChargingStatus: Int32) {}
    func onDeviceLogDeleteResult(macAddress: String, uuid: String, success: Bool) {}
    func onDeviceLogDumping(macAddress: String, uuid: String, success: Bool, packetSequence: Int32, fileTimestamp: Int32, transferStatus: Int32, progress: Int32, fragmentData: KotlinByteArray) {}
    func onDeviceLogEnableCollectionResult(macAddress: String, uuid: String, success: Bool) {}
    func onDeviceLogRequestListResult(macAddress: String, uuid: String, success: Bool, fileCount: Int32, fileList: [DeviceLogFileInfo], logCollectionStatus: Bool) {}
    func onDeviceLogTransferResult(macAddress: String, uuid: String, success: Bool, code: Int32) {}
    func onDeviceTransferStateChanged(macAddress: String, uuid: String, state: DeviceTransferState) {}
    func onFindMyEnableResult(macAddress: String, uuid: String, success: Bool) {}
    func onGetDeviceInfo(macAddress: String, uuid: String, info: DeviceInfo) { guard accepts(macAddress, uuid) else { return }; event(.info(battery: Int(info.deviceBattery), recording: info.recording?.intValue == 1)) }
    func onGetDeviceInfoError(macAddress: String, uuid: String, errorCode: Int32) {}
    func onOtaError(macAddress: String, uuid: String, errorCode: Int32) {}
    func onRealtimeTransferSwitch(macAddress: String, uuid: String, fileID: Int32, filePath: String?) {}
    func onReceiveAudioFragment(macAddress: String, uuid: String, fileID: Int32, audioData: KotlinByteArray, isAppendPreAudio: Bool, sequenceNumber: Int32, isMark: Bool) {
        guard accepts(macAddress, uuid), fileID >= 0, sequenceNumber >= 0 else { return }
        if isMark { publishMarkers(fileID: fileID, offsets: [Int(sequenceNumber) * 20], final: false) }
        let bytes = (0..<audioData.size).map { UInt8(bitPattern: audioData.get(index: $0)) }
        event(.realtimeFragment(fileID: fileID, sequence: Int(sequenceNumber), isAppendPreAudio: isAppendPreAudio, data: Data(bytes), isMarked: isMark))
    }
    func onReceiveOfflineFile(macAddress: String, uuid: String, offlineFileData: OfflineFileData, isAllAudioFiles: Bool) { guard accepts(macAddress, uuid) else { return }; event(.files(offlineFileData.fileInfoList.map { RecordingBeanFile(id: $0.time, size: $0.size, duration: $0.duration, endTime: $0.endTime, code: $0.code) })) }
    func onReceiveOfflineFileError(macAddress: String, uuid: String, errorCode: Int32) { guard accepts(macAddress, uuid) else { return }; event(.error("录音列表暂未读出，可重试同步。")) }
    func onReceiveWaitingDeviceOpenWIFI(macAddress: String, uuid: String) {}
    func onResetDeviceResult(macAddress: String, uuid: String, result: Bool) {}
    func onSendBindingDeviceCMDSuccess(macAddress: String, uuid: String) { guard accepts(macAddress, uuid) else { return }; event(.bindingPending) }
    func onSendUnbindingDeviceCMDSuccess(macAddress: String, uuid: String) {}
    func onSyncTimeResult(macAddress: String, uuid: String, result: Bool) {}
    func onTransferFileError(macAddress: String, uuid: String, fileID: Int32, errorType: FileTransferError) { guard accepts(macAddress, uuid) else { return }; event(.error("录音同步未完成，设备原文件保留，可重试。")) }
    func onTransferFileProgress(macAddress: String, uuid: String, fileID: Int32, total: Int32, current: Int32, sequenceNumber: Int32, isMark: Bool) {
        guard accepts(macAddress, uuid) else { return }
        if isMark && sequenceNumber >= 0 { publishMarkers(fileID: fileID, offsets: [Int(sequenceNumber) * 20], final: false) }
        if total > 0 { event(.progress(Int(Double(current) * 100 / Double(total)))) }
    }
    func onTransferFileStatusChanged(macAddress: String, uuid: String, fileID: Int32, status: Int32, markTimeStampList: NSMutableArray) {
        guard accepts(macAddress, uuid) else { return }
        // Only the decode callback confirms that the complete marker timeline
        // has been read; intermediate transfer snapshots may still be partial.
        publishMarkers(fileID: fileID, offsets: markTimeStampList.compactMap { ($0 as? NSNumber)?.intValue }, final: false)
    }
    func onTransferFileSupplementProgress(macAddress: String, uuid: String, fileID: Int32, total: Int32, current: Int32) {}
    func onTransferFileTransmitting(macAddress: String, uuid: String, fileID: Int32) {}
    func onWifiScanned(macAddress: String, uuid: String) {}
}

@MainActor
final class SoundcoreWorkAdapter {
    static let available = true
    private let sdk = SoundcoreSDK.companion.proxy
    private let callbacks: SoundcoreCallbacks
    let root: URL
    private(set) var selected: RecordingBeanDevice?
    init(root: URL, event: @escaping @Sendable (SoundcoreEvent) -> Void) {
        self.root = root; callbacks = SoundcoreCallbacks(event: event)
    }
    func initialize(_ receipt: RecordingDeviceSession) throws {
        guard receipt.sdk_version == sdk.getVersion(), receipt.product_code == sdk.getProductCode() else { throw APIError.invalidResponse }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        let config = SDKInitConfig(context: UIApplication.shared, userId: receipt.user_id,
            deviceId: receipt.device_id, token: receipt.token, licenseJson: receipt.license_json,
            license_signature: receipt.license_signature, environment: .development, isDebug: KotlinBoolean(bool: false),
            firmwareLogFilePath: nil, commandTimeOut: 8, fileTransferInterval: 300,
            isSPPSingleThread: false, androidUDPPingTimeIntval: 100, androidWIFIReceiveThreadSwitch: false)
        sdk.registerBusinessCallback(callback: callbacks)
        sdk.doInitSDK(logInterface: callbacks, config: config, authResultListener: callbacks)
    }
    func scan() {
        callbacks.setScanning(true)
        // SDK filters are device UUIDs, not product codes. Check D3200 in the callback.
        sdk.startScan(bleScan: true, sppScan: false, filters: NSMutableArray(), onReceiveScanResult: callbacks)
    }
    func connect(_ device: RecordingBeanDevice) {
        if let old = selected { sdk.disconnect(macAddress: old.mac, uuid: old.id) }
        callbacks.setScanning(false); sdk.stopScan(); selected = device; callbacks.select(device)
        sdk.connect(macAddress: device.mac, uuid: device.id, listener: callbacks)
    }
    func refresh(_ device: RecordingBeanDevice) { sdk.getDeviceInfo(macAddress: device.mac, uuid: device.id) }
    func bind(_ device: RecordingBeanDevice) { sdk.bindingDevice(macAddress: device.mac, uuid: device.id, binding: true) }
    func list(_ device: RecordingBeanDevice) { sdk.getAllAudioRecordFiles(macAddress: device.mac, uuid: device.id) }
    /// Subscribes to an already recording device. This is not a start command.
    func beginRealtime(_ device: RecordingBeanDevice) {
        guard selected == device else { return }
        sdk.acquireRealtimeAudioData(macAddress: device.mac, uuid: device.id, savaPath: root.path)
    }
    func setPaused(_ paused: Bool, device: RecordingBeanDevice) {
        if paused { sdk.pauseRecord(macAddress: device.mac, uuid: device.id) }
        else { sdk.resumeRecord(macAddress: device.mac, uuid: device.id) }
    }
    func download(_ file: RecordingBeanFile, from device: RecordingBeanDevice) throws {
        let info = FileInfoModel(time: file.id, endTime: file.endTime, size: file.size, duration: file.duration, code: file.code)
        try sdk.startSyncAudioFile(macAddress: device.mac, uuid: device.id,
            fileList: NSMutableArray(array: [info]), savaPath: root.path, openBTTime: 60)
    }
    func close() {
        callbacks.setScanning(false); sdk.stopScan()
        if let selected { sdk.disconnect(macAddress: selected.mac, uuid: selected.id) }
        selected = nil; callbacks.select(nil); sdk.close()
    }
}
#else
@MainActor
final class SoundcoreWorkAdapter {
    static let available = false
    let root: URL
    var selected: RecordingBeanDevice? { nil }
    init(root: URL, event: @escaping @Sendable (SoundcoreEvent) -> Void) { self.root = root }
    func initialize(_ receipt: RecordingDeviceSession) throws { throw APIError.invalidResponse }
    func scan() {}
    func connect(_ device: RecordingBeanDevice) {}
    func refresh(_ device: RecordingBeanDevice) {}
    func bind(_ device: RecordingBeanDevice) {}
    func list(_ device: RecordingBeanDevice) {}
    func beginRealtime(_ device: RecordingBeanDevice) {}
    func setPaused(_ paused: Bool, device: RecordingBeanDevice) {}
    func download(_ file: RecordingBeanFile, from device: RecordingBeanDevice) throws { throw APIError.invalidResponse }
    func close() {}
}
#endif

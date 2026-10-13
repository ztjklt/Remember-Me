package me.remember.hardware.example;

/** SDK-specific callback defaults. Compiled against the vendor jar, never copied into its source. */
abstract class SoundcoreCallbacks implements com.oceanwing.soundcore.spplink.listener.SoundcoreBusinessCallback {
    @Override public void onAudioRecordStatusChanged(java.lang.String p0, java.lang.String p1, int p2, int p3, int p4) { }
    @Override public void onReceiveOfflineFile(java.lang.String p0, java.lang.String p1, com.oceanwing.soundcore.spplink.service.audio.model.OfflineFileData p2, boolean p3) { }
    @Override public void onReceiveOfflineFileError(java.lang.String p0, java.lang.String p1, int p2) { }
    @Override public void onAudioRecordDuration(java.lang.String p0, java.lang.String p1, long p2) { }
    @Override public void onTransferFileStatusChanged(java.lang.String p0, java.lang.String p1, int p2, int p3, java.util.ArrayList<java.lang.Integer> p4) { }
    @Override public void onDecodeFileCompleted(java.lang.String p0, java.lang.String p1, int p2, java.lang.String p3) { }
    @Override public void onDecodeFileMarkers(java.lang.String p0, java.lang.String p1, int p2, int[] p3) { }
    @Override public void onTransferFileError(java.lang.String p0, java.lang.String p1, int p2, com.oceanwing.soundcore.spplink.listener.FileTransferError p3) { }
    @Override public void onDeviceTransferStateChanged(java.lang.String p0, java.lang.String p1, com.oceanwing.soundcore.spplink.listener.DeviceTransferState p2) { }
    @Override public void onOtaError(java.lang.String p0, java.lang.String p1, int p2) { }
    @Override public void onTransferFileSupplementProgress(java.lang.String p0, java.lang.String p1, int p2, int p3, int p4) { }
    @Override public void onTransferFileProgress(java.lang.String p0, java.lang.String p1, int p2, int p3, int p4, int p5, boolean p6) { }
    @Override public void onReceiveAudioFragment(java.lang.String p0, java.lang.String p1, int p2, byte[] p3, boolean p4, int p5, boolean p6) { }
    @Override public void onGetDeviceInfo(java.lang.String p0, java.lang.String p1, com.oceanwing.soundcore.spplink.service.deviceinfo.DeviceInfo p2) { }
    @Override public void onGetDeviceInfoError(java.lang.String p0, java.lang.String p1, int p2) { }
    @Override public void onDeleteFileResult(java.lang.String p0, java.lang.String p1, int p2, boolean p3) { }
    @Override public void onSendBindingDeviceCMDSuccess(java.lang.String p0, java.lang.String p1) { }
    @Override public void onSendUnbindingDeviceCMDSuccess(java.lang.String p0, java.lang.String p1) { }
    @Override public void onDeviceBindConfirm(java.lang.String p0, java.lang.String p1) { }
    @Override public void onDeviceLogEnableCollectionResult(java.lang.String p0, java.lang.String p1, boolean p2) { }
    @Override public void onDeviceLogRequestListResult(java.lang.String p0, java.lang.String p1, boolean p2, int p3, java.util.List<com.oceanwing.soundcore.spplink.service.devicelog.DeviceLogFileInfo> p4, boolean p5) { }
    @Override public void onDeviceLogTransferResult(java.lang.String p0, java.lang.String p1, boolean p2, int p3) { }
    @Override public void onDeviceLogDeleteResult(java.lang.String p0, java.lang.String p1, boolean p2) { }
    @Override public void onDeviceLogDumping(java.lang.String p0, java.lang.String p1, boolean p2, int p3, int p4, int p5, int p6, byte[] p7) { }
    @Override public void onBindingDeviceError(java.lang.String p0, java.lang.String p1, int p2) { }
    @Override public void onSyncTimeResult(java.lang.String p0, java.lang.String p1, boolean p2) { }
    @Override public void onDeviceChargingStatusChanged(java.lang.String p0, java.lang.String p1, int p2, int p3) { }
    @Override public void onBatteryInfoChanged(java.lang.String p0, java.lang.String p1, int p2, int p3) { }
    @Override public void onResetDeviceResult(java.lang.String p0, java.lang.String p1, boolean p2) { }
    @Override public void onFindMyEnableResult(java.lang.String p0, java.lang.String p1, boolean p2) { }
    @Override public void onReceiveWaitingDeviceOpenWIFI(java.lang.String p0, java.lang.String p1) { }
    @Override public void onWifiScanned(java.lang.String p0, java.lang.String p1) { }
    @Override public void onConnectWIFIError(java.lang.String p0, java.lang.String p1, int p2) { }
    @Override public void onConnectWIFIStatusChanged(java.lang.String p0, java.lang.String p1, com.oceanwing.soundcore.spplink.service.wifi.WifiState p2) { }
    @Override public void onCloseSyncFileByWIFI(java.lang.String p0, java.lang.String p1) { }
    @Override public void onRealtimeTransferSwitch(java.lang.String p0, java.lang.String p1, int p2, java.lang.String p3) { }
    @Override public void onTransferFileTransmitting(java.lang.String p0, java.lang.String p1, int p2) { }
    @Override public void onConnectSPPLinkStatusChanged(java.lang.String p0, java.lang.String p1, boolean p2) { }
}

package me.remember.app.hardware;

import com.oceanwing.soundcore.spplink.SoundcoreSDK;
import com.oceanwing.soundcore.spplink.log.LogInterface;
import com.oceanwing.soundcore.spplink.model.SDKInitConfig;
import com.oceanwing.soundcore.spplink.model.BlueDeviceModel;
import com.oceanwing.soundcore.spplink.model.SdkException;
import com.oceanwing.soundcore.spplink.listener.SoundcoreConnectionCallback;
import com.oceanwing.soundcore.spplink.listener.FileTransferError;
import com.oceanwing.soundcore.spplink.service.auth.SDKEnvironment;
import com.oceanwing.soundcore.spplink.service.audio.model.FileInfoModel;
import com.oceanwing.soundcore.spplink.service.audio.model.OfflineFileData;
import com.oceanwing.soundcore.spplink.service.search.OnReceiveScanResult;
import me.remember.app.hardware.*;
import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** Runtime adapter for the privately supplied Soundcore 1.3.02 archive. */
public final class Soundcore1302Bridge implements HardwareTransport {
    private static final LogInterface NO_LOG = new LogInterface() {
        public void v(String t, String m) { } public void d(String t, String m) { }
        public void i(String t, String m) { } public void w(String t, String m) { }
        public void e(String t, String m) { }
    };
    private final SoundcoreSDK sdk;
    private final HardwareEvents events;
    private volatile long generation;
    private volatile long connectionGeneration;
    private HardwareAuthResult auth;
    private volatile String mac;
    private volatile String uuid;
    private volatile File downloadRoot;
    private volatile Integer downloadFileId;
    private final java.util.Set<File> realtimeRoots = java.util.concurrent.ConcurrentHashMap.newKeySet();
    private volatile boolean connected;
    private File logRoot;
    private RecorderCommand pendingCommand;
    private boolean wifiActive, wifiBleLost;

    public Soundcore1302Bridge(SoundcoreSDK sdk, HardwareEvents events) { this.sdk = sdk; this.events = events; }

    /** Caller supplies short-lived server-issued values; app_key is neither accepted nor stored here. */
    public synchronized void initialize(Object application, Work3200Credentials credentials) {
        final long epoch = ++generation;
        auth = null; mac = null; uuid = null; downloadRoot = null; connected = false; ++connectionGeneration;
        downloadFileId = null; realtimeRoots.clear();
        wifiActive=false; wifiBleLost=false;
        if(logRoot == null) logRoot = new File(((android.content.Context) application).getFilesDir(), "recorder-logs/" + java.util.UUID.randomUUID());
        if (!logRoot.isDirectory() && !logRoot.mkdirs()) throw new IllegalStateException("Log directory unavailable");
        events.sdkInfo(sdk.getVersion(), sdk.getProductCode());
        sdk.registerBusinessCallback(new SoundcoreCallbacks() {
            private boolean current(String address, String id) {
                return epoch == generation && address.equals(mac) && id.equals(uuid);
            }
            @Override public void onGetDeviceInfo(String address, String id, com.oceanwing.soundcore.spplink.service.deviceinfo.DeviceInfo info) {
                if (current(address, id)) {
                    events.info(info.getDeviceBattery(), info.getFirmwareVersion(), info.getFreeMemoryKB(), info.getTotalMemoryKB());
                    events.recordingSnapshot(info.getRecording(), info.getRecodingOriginalTime());
                    com.oceanwing.soundcore.spplink.service.deviceinfo.ChargingBoxInfo box = info.getChargingBoxInfo();
                    events.deviceDetails(new RecorderDetails(orEmpty(info.getSerialNumber()), orEmpty(info.getWifiFirmwareVersion()),
                        box == null ? "" : orEmpty(box.getVersion()), box == null ? null : box.getBattery(),
                        info.getDeviceChargingStatus() == null ? null : info.getDeviceChargingStatus() == 1,
                        box == null ? null : box.isCharging()));
                }
            }
            @Override public void onAudioRecordStatusChanged(String address, String id, int status, int duration, int fileId) {
                if (current(address, id)) events.recording(status, duration, fileId);
                if (current(address, id) && status == 0 && (pendingCommand == RecorderCommand.PAUSE || pendingCommand == RecorderCommand.RESUME)) pendingCommand = null;
                if (current(address, id) && ((status == 2 && pendingCommand == RecorderCommand.PAUSE) ||
                        (status == 1 && pendingCommand == RecorderCommand.RESUME))) {
                    events.commandResult(pendingCommand, true, "设备已确认录音状态"); pendingCommand = null;
                }
            }
            @Override public void onAudioRecordDuration(String address, String id, long duration) {
                if (current(address, id)) events.recordingDuration(duration);
            }
            @Override public void onReceiveAudioFragment(String address, String id, int fileId, byte[] audio, boolean append, int sequence, boolean marked) {
                if (current(address, id)) {
                    events.audioFragment(fileId, audio.clone(), append, sequence, marked);
                    if (marked) events.realtimeMarker(fileId, sequence);
                }
            }
            @Override public void onGetDeviceInfoError(String address, String id, int code) {
                if (current(address, id)) events.error("device_info", code);
            }
            @Override public void onSendBindingDeviceCMDSuccess(String address, String id) {
                if (current(address, id)) events.binding(false);
            }
            @Override public void onDeviceBindConfirm(String address, String id) {
                if (current(address, id)) { events.binding(true); sdk.getDeviceInfo(address, id); }
            }
            @Override public void onBindingDeviceError(String address, String id, int code) {
                if (current(address, id)) events.error("binding", code);
            }
            @Override public void onReceiveOfflineFile(String address, String id, OfflineFileData data, boolean complete) {
                if (!current(address, id)) return;
                List<DeviceRecording> files = new ArrayList<>();
                for (FileInfoModel f : data.getFileInfoList()) files.add(new DeviceRecording(f.getTime(), f.getEndTime(), f.getSize(), f.getDuration(), f.getCode()));
                events.files(files, complete);
            }
            @Override public void onReceiveOfflineFileError(String address, String id, int code) {
                if (current(address, id)) events.error("file_list", code);
            }
            @Override public void onTransferFileStatusChanged(String address, String id, int fileId, int status, ArrayList<Integer> markers) {
                if (current(address, id)) {
                    events.transfer(fileId, status);
                    // The supplied guide specifies offsets in milliseconds for
                    // this callback too. Preserve them even if decode markers arrive later.
                    if (markers != null && !markers.isEmpty()) events.markers(fileId, markers.stream().mapToInt(Integer::intValue).toArray());
                }
            }
            @Override public void onDeviceTransferStateChanged(String address, String id, com.oceanwing.soundcore.spplink.listener.DeviceTransferState state) {
                if (current(address, id)) events.transferIdle(state == com.oceanwing.soundcore.spplink.listener.DeviceTransferState.IDLE);
            }
            @Override public void onTransferFileTransmitting(String address, String id, int fileId) {
                if (current(address, id)) events.transferRejected(fileId);
            }
            @Override public void onTransferFileProgress(String address, String id, int fileId, int total, int received, int sequence, boolean marked) {
                if (current(address, id)) events.progress(fileId, received, total, sequence, marked);
            }
            @Override public void onDecodeFileCompleted(String address, String id, int fileId, String path) {
                if (!current(address, id)) return;
                try {
                    File file = new File(path).getCanonicalFile();
                    // Live and offline callbacks share this API. A delayed live callback
                    // must not fail the offline download of the same recording.
                    for (File liveRoot : realtimeRoots) if (file.toPath().startsWith(liveRoot.toPath())) {
                        events.diagnostic("live file callback file=" + fileId + " ignored by offline receiver"); return;
                    }
                    File expectedRoot = downloadRoot;
                    if (expectedRoot == null || !Integer.valueOf(fileId).equals(downloadFileId)) return;
                    boolean within = file.toPath().startsWith(expectedRoot.toPath());
                    events.diagnostic("sdk file file=" + fileId + " within=" + within + " exists=" + file.isFile() + " bytes=" + file.length());
                    if (!within || !file.isFile() || file.length() == 0) throw new IllegalArgumentException();
                    events.receivedSdkFile(fileId, file); // Still SDK raw Opus; never an upload-ready WAV claim.
                } catch (Exception error) { events.fileError(fileId, "received_file_path", -1); }
            }
            @Override public void onDecodeFileMarkers(String address, String id, int fileId, int[] offsets) {
                if (current(address, id)) events.markers(fileId, offsets.clone());
            }
            @Override public void onTransferFileError(String address, String id, int fileId, FileTransferError error) {
                if (current(address, id)) events.fileError(fileId, "file_transfer", error.getCode());
            }
            @Override public void onTransferFileSupplementProgress(String a, String u, int file, int total, int received) {
                if (current(a,u)) events.supplement(file, received, total);
            }
            @Override public void onSyncTimeResult(String a,String u,boolean ok) { if(current(a,u)) events.commandResult(RecorderCommand.SYNC_TIME,ok,"设备时间同步"); }
            @Override public void onFindMyEnableResult(String a,String u,boolean ok) {
                if(current(a,u)) events.commandResult(pendingCommand == RecorderCommand.FIND_MY_OFF ? RecorderCommand.FIND_MY_OFF : RecorderCommand.FIND_MY_ON,ok,"Find My 设置");
            }
            @Override public void onResetDeviceResult(String a,String u,boolean ok) { if(current(a,u)) events.commandResult(RecorderCommand.RESET,ok,"设备重置"); }
            @Override public void onSendUnbindingDeviceCMDSuccess(String a,String u) { if(current(a,u)) events.commandResult(RecorderCommand.UNBIND,true,"解除绑定指令已发送，设备可能断开"); }
            @Override public void onDeleteFileResult(String a,String u,int file,boolean ok) { if(current(a,u)) events.commandResult(RecorderCommand.DELETE_RECORDING,ok,"设备文件 " + file); }
            @Override public void onDeviceChargingStatusChanged(String a,String u,int device,int box) { if(current(a,u)) events.chargingChanged(device==1,box==1); }
            @Override public void onBatteryInfoChanged(String a,String u,int device,int box) { if(current(a,u)) events.batteryChanged(device,box); }
            @Override public void onDeviceLogEnableCollectionResult(String a,String u,boolean ok) {
                if(current(a,u)) events.commandResult(pendingCommand == RecorderCommand.LOG_DISABLE ? RecorderCommand.LOG_DISABLE : RecorderCommand.LOG_ENABLE,ok,"设备日志采集设置");
            }
            @Override public void onDeviceLogRequestListResult(String a,String u,boolean ok,int count,List<com.oceanwing.soundcore.spplink.service.devicelog.DeviceLogFileInfo> files,boolean collecting) {
                if(!current(a,u)) return;
                List<RecorderLog> result = new ArrayList<>();
                if(ok) for(com.oceanwing.soundcore.spplink.service.devicelog.DeviceLogFileInfo f: files) result.add(new RecorderLog(f.getFileTimestamp(),f.getFileEndTimestamp()));
                if(ok) events.deviceLogs(result,collecting);
                events.commandResult(RecorderCommand.LOG_LIST,ok,"读取设备日志列表");
            }
            @Override public void onDeviceLogTransferResult(String a,String u,boolean ok,int code) {
                if(!current(a,u)) return;
                RecorderCommand command = pendingCommand == RecorderCommand.LOG_STOP ? RecorderCommand.LOG_STOP : RecorderCommand.LOG_DOWNLOAD;
                if(!ok || command == RecorderCommand.LOG_STOP) events.commandResult(command,ok,"日志传输指令 " + code);
                else events.maintenanceProgress(command,null,"设备已接受日志下载",false);
            }
            @Override public void onDeviceLogDeleteResult(String a,String u,boolean ok) { if(current(a,u)) events.commandResult(RecorderCommand.LOG_DELETE,ok,"删除设备日志"); }
            @Override public void onDeviceLogDumping(String a,String u,boolean ok,int sequence,int file,int status,int progress,byte[] fragment) {
                if(!current(a,u)) return;
                if(!ok) events.commandResult(RecorderCommand.LOG_DOWNLOAD,false,"设备日志传输失败");
                else events.maintenanceProgress(RecorderCommand.LOG_DOWNLOAD,Math.max(0,Math.min(100,progress)),"日志 " + file,status==2);
            }
            @Override public void onReceiveWaitingDeviceOpenWIFI(String a,String u) { if(current(a,u)) events.channel("Wi-Fi：等待设备热点"); }
            @Override public void onWifiScanned(String a,String u) { if(current(a,u)) events.channel("Wi-Fi：已发现设备热点"); }
            @Override public void onConnectWIFIStatusChanged(String a,String u,com.oceanwing.soundcore.spplink.service.wifi.WifiState state) {
                if(current(a,u)) events.channel("Wi-Fi " + state.name());
            }
            @Override public void onConnectWIFIError(String a,String u,int code) { if(current(a,u)) events.error("wifi",code); }
            @Override public void onCloseSyncFileByWIFI(String a,String u) {
                if(!current(a,u)) return;
                wifiActive=false; events.channel("Wi-Fi 已关闭");
                if(wifiBleLost) {
                    wifiBleLost=false; events.linkRecovering();
                    final long connection=connectionGeneration;
                    new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(() -> {
                        if(epoch==generation && connection==connectionGeneration) {
                            try { connect(a,u); } catch(RuntimeException e) { events.error("connect",-1); }
                        }
                    },1000);
                }
            }
            @Override public void onRealtimeTransferSwitch(String a,String u,int fileId,String path) { if(current(a,u)) events.realtimeSwitch(fileId); }
            @Override public void onConnectSPPLinkStatusChanged(String a,String u,boolean value) { if(current(a,u)) events.channel(value?"蓝牙 SPP":"蓝牙 BLE"); }
            @Override public void onOtaError(String a,String u,int code) { if(current(a,u)) events.commandResult(RecorderCommand.OTA,false,"固件升级错误 " + code); }
        });
        SDKEnvironment environment = credentials.getEnvironment() == HardwareEnvironment.PRODUCTION ? SDKEnvironment.PRODUCTION : SDKEnvironment.DEVELOPMENT;
        SDKInitConfig config = new SDKInitConfig(application, credentials.getUserId(), credentials.getDeviceId(), credentials.getToken(),
                credentials.getLicenseJson(), credentials.getLicenseSignature(), environment, false, logRoot.getPath(), 3L, 200L, false, 100L, true);
        sdk.initSDK(NO_LOG, config, result -> {
            synchronized (Soundcore1302Bridge.this) {
                if (epoch != generation) return;
                auth = new HardwareAuthResult(result.getSuccess(), result.isOnline(), result.getLicenseValid(), result.getLicenseExpireTime(),
                        result.getTokenExpired(), result.getError() == null ? null : new HardwareAuthError(result.getError().getCode(), null));
                events.auth(auth); // Can arrive twice; consumer must preserve offline and online observations.
            }
        });
    }

    private void requireAuthorized() {
        if (auth == null || !auth.getSuccess() || auth.getTokenExpired() || (!auth.isOnline() && (!auth.getLicenseValid() || auth.getLicenseExpireTime() <= System.currentTimeMillis() / 1000)))
            throw new IllegalStateException("SDK authorization is not ready");
    }
    private static String orEmpty(String value) { return value == null ? "" : value; }
    public synchronized void scan() {
        requireAuthorized(); final long epoch = generation;
        sdk.startScan(true, true, new ArrayList<>(), new OnReceiveScanResult() {
            public void onScanSuccess(BlueDeviceModel device) {
                if (epoch == generation) {
                    events.found(device.getProductCode(), device.getDeviceName(), device.getMacAddress(), device.getUuid());
                    events.bindingAdvertisement(device.getMacAddress(), device.getUuid(), "1".equals(device.getBindingStatus()));
                }
            }
            public void onScanError(int code) {
                // The SDK reports normal scan timeout/user stop as 1/2. A queued stop
                // callback must not tear down the connection selected from that scan.
                if (epoch == generation && code != 1 && code != 2) events.error("scan", code);
            }
        });
    }
    public synchronized void stopScan() { sdk.stopScan(); }
    public synchronized void connect(String address, String id) {
        requireAuthorized(); final long epoch = generation; final long connection = ++connectionGeneration;
        if (address == null || address.isBlank() || id == null || id.isBlank()) throw new IllegalArgumentException("Device transport identity is incomplete");
        mac = address; uuid = id; connected = false;
        sdk.connect(address, id, new SoundcoreConnectionCallback() {
            private boolean current() { return epoch == generation && connection == connectionGeneration; }
            public void onConnected(String ignored, String name) {
                if (!current()) return;
                connected = true;
                // Kotlin UInt is JVM-mangled; the method name is verified against this exact 1.3.02 jar.
                syncTime();
                events.connected(); sdk.getDeviceInfo(address, id);
            }
            public void onDisconnected(String ignored, Integer systemCode, String message) {
                if (current()) {
                    connected=false;
                    if(wifiActive) { wifiBleLost=true; events.channel("Wi-Fi 传输中，蓝牙暂时断开"); }
                    else { mac=null; uuid=null; events.disconnected(systemCode); }
                }
            }
            public void onError(String ignored, SdkException error) { if (current()) { connected = false; events.error("connect", error.getCode()); } }
        });
    }
    public synchronized void bind() { requireConnected(); sdk.bindingDevice(mac, uuid, true); }
    public synchronized void refreshInfo() { requireConnected(); sdk.getDeviceInfo(mac, uuid); }
    public synchronized void realtime(File directory) {
        requireConnected();
        String folder = SoundcoreSavePath.directoryArgument(directory);
        realtimeRoots.add(new File(folder));
        sdk.acquireRealtimeAudioData(mac, uuid, folder);
    }
    public synchronized void listFiles() { requireConnected(); sdk.getAllAudioRecordFiles(mac, uuid); }
    public synchronized void transfer(DeviceRecording recording, File privateDownloadDirectory) {
        requireConnected();
        try { downloadRoot = privateDownloadDirectory.getCanonicalFile(); }
        catch (java.io.IOException error) { throw new IllegalArgumentException("Download folder unavailable"); }
        if (!downloadRoot.isDirectory()) throw new IllegalArgumentException("Create the app-private download directory first");
        downloadFileId = recording.getFileId();
        ArrayList<FileInfoModel> files = new ArrayList<>();
        files.add(new FileInfoModel(recording.getFileId(), recording.getEndTime(), recording.getSizeBytes(), recording.getDurationMs(), recording.getCode()));
        sdk.startSyncAudioFile(mac, uuid, files, SoundcoreSavePath.directoryArgument(downloadRoot), 15000);
    }
    private void requireConnected() { requireAuthorized(); if ((!connected && !wifiActive) || mac == null || uuid == null) throw new IllegalStateException("Device is not connected"); }
    public synchronized void pauseExistingRecording() { requireConnected(); sdk.pauseRecord(mac, uuid); }
    public synchronized void resumeExistingRecording() { requireConnected(); sdk.resumeRecord(mac, uuid); }
    private void syncTime() {
        try { sdk.getClass().getMethod("syncTime-jXDDuk8", String.class, String.class, int.class)
                .invoke(sdk, mac, uuid, (int)(System.currentTimeMillis()/1000)); }
        catch (ReflectiveOperationException e) { events.error("sync_time_binding",-1); }
    }
    @Override public synchronized boolean isTransferring() { requireConnected(); return sdk.isDataTransferring(mac,uuid); }
    @Override public synchronized File logDirectory() { return logRoot; }
    @Override public synchronized void configureLogDirectory(File directory) { if(connected) throw new IllegalStateException("Disconnect first"); logRoot=directory; }
    @Override public synchronized void closeWifi() { requireConnected(); sdk.closeWIFITransport(mac,uuid); }
    @Override public synchronized void transferWifi(DeviceRecording recording, File directory) {
        requireConnected();
        try { downloadRoot=directory.getCanonicalFile(); } catch(java.io.IOException e) { throw new IllegalArgumentException(e); }
        if(!downloadRoot.isDirectory()) throw new IllegalArgumentException("Download folder unavailable");
        downloadFileId = recording.getFileId();
        ArrayList<FileInfoModel> files=new ArrayList<>();
        files.add(new FileInfoModel(recording.getFileId(),recording.getEndTime(),recording.getSizeBytes(),recording.getDurationMs(),recording.getCode()));
        wifiActive=true; wifiBleLost=false;
        sdk.startSyncAudioFileByWIFI(mac,uuid,files,SoundcoreSavePath.directoryArgument(downloadRoot),1000L);
    }
    @Override public synchronized void command(RecorderCommand command,int fileId,RecorderFirmware firmware) {
        requireConnected(); pendingCommand=command;
        switch(command) {
            case SYNC_TIME: syncTime(); break;
            case PAUSE: sdk.pauseRecord(mac,uuid); break;
            case RESUME: sdk.resumeRecord(mac,uuid); break;
            case FIND_MY_ON: case FIND_MY_OFF: sdk.setFindMyEnable(mac,uuid,command==RecorderCommand.FIND_MY_ON); break;
            case UNBIND: sdk.bindingDevice(mac,uuid,false); break;
            case RESET: sdk.resetDevice(mac,uuid); break;
            case DELETE_RECORDING: sdk.deleteFiles(mac,uuid,new ArrayList<>(java.util.Collections.singletonList(fileId))); break;
            case LOG_LIST: sdk.requestDeviceLogList(mac,uuid); break;
            case LOG_ENABLE: case LOG_DISABLE: sdk.setDeviceLogEnableCollection(mac,uuid,command==RecorderCommand.LOG_ENABLE,false,0,111); break;
            case LOG_DOWNLOAD: case LOG_STOP: sdk.setDeviceLogTransfer(mac,uuid,command==RecorderCommand.LOG_DOWNLOAD,new int[]{fileId}); break;
            case LOG_DELETE: sdk.deleteDeviceLogFile(mac,uuid,fileId); break;
            case OTA:
                if(firmware==null) throw new IllegalArgumentException("Official firmware is required");
                final long epoch=generation, connection=connectionGeneration;
                sdk.startCombinedOta(mac,uuid,new com.oceanwing.soundcore.spplink.service.ota.FirmwarePackage(
                    firmware.getBtVersion(),firmware.getWifiVersion(),firmware.getBtFile()==null?null:firmware.getBtFile().getPath(),firmware.getWifiFile()==null?null:firmware.getWifiFile().getPath()),
                    new com.oceanwing.soundcore.spplink.service.ota.OTAProgressCallback() {
                        private boolean current(){return epoch==generation && connection==connectionGeneration;}
                        public void onStateChanged(com.oceanwing.soundcore.spplink.service.ota.OTAState state,com.oceanwing.soundcore.spplink.service.ota.Phase phase) {
                            if(current()) events.maintenanceProgress(RecorderCommand.OTA,null,"固件 " + phase.name() + " · " + state.name(),false);
                        }
                        public void onProgress(int percent) { if(current()) events.maintenanceProgress(RecorderCommand.OTA,percent,"固件升级",false); }
                        public void onError(com.oceanwing.soundcore.spplink.service.ota.OTAError error) { if(current()) events.commandResult(RecorderCommand.OTA,false,error.name()); }
                        public void onCompleted() { if(current()) events.commandResult(RecorderCommand.OTA,true,"固件升级完成，等待设备重启"); }
                    }); break;
        }
    }
    @Override public synchronized void close() {
        ++generation; ++connectionGeneration;
        try { sdk.stopScan(); if (mac != null && uuid != null) sdk.disconnect(mac, uuid); } catch (RuntimeException ignored) { }
        auth = null; mac = null; uuid = null; downloadRoot = null; connected = false; wifiActive=false; wifiBleLost=false; sdk.close();
        downloadFileId = null; realtimeRoots.clear(); pendingCommand = null;
    }
}

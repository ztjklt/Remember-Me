package me.remember.hardware.example;

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

/** Compile-only example, deliberately outside app source sets. No constructor starts network or Bluetooth. */
public final class Soundcore1302Bridge implements AutoCloseable {
    public interface Events {
        void auth(HardwareAuthResult result);
        void found(String productCode, String name, String mac, String uuid);
        void connected();
        void disconnected(Integer systemCode);
        void files(List<DeviceRecording> files, boolean complete);
        void transfer(int fileId, int sdkStatus);
        void progress(int fileId, int receivedBytes, int totalBytes, int sequenceNumber, boolean marked);
        void receivedSdkFile(int fileId, File rawFile);
        void markers(int fileId, int[] offsetsMs);
        void error(String operation, int code);
    }

    private static final LogInterface NO_LOG = new LogInterface() {
        public void v(String t, String m) { } public void d(String t, String m) { }
        public void i(String t, String m) { } public void w(String t, String m) { }
        public void e(String t, String m) { }
    };
    private final SoundcoreSDK sdk;
    private final Events events;
    private volatile long generation;
    private volatile long connectionGeneration;
    private HardwareAuthResult auth;
    private volatile String mac;
    private volatile String uuid;
    private volatile File downloadRoot;
    private volatile boolean connected;

    public Soundcore1302Bridge(SoundcoreSDK sdk, Events events) { this.sdk = sdk; this.events = events; }

    /** Caller supplies short-lived server-issued values; app_key is neither accepted nor stored here. */
    public synchronized void initialize(Object application, Work3200Credentials credentials) {
        final long epoch = ++generation;
        auth = null; mac = null; uuid = null; downloadRoot = null; connected = false; ++connectionGeneration;
        sdk.registerBusinessCallback(new SoundcoreCallbacks() {
            private boolean current(String address, String id) {
                return epoch == generation && address.equals(mac) && id.equals(uuid);
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
                if (current(address, id)) events.transfer(fileId, status);
            }
            @Override public void onTransferFileProgress(String address, String id, int fileId, int total, int received, int sequence, boolean marked) {
                if (current(address, id)) events.progress(fileId, received, total, sequence, marked);
            }
            @Override public void onDecodeFileCompleted(String address, String id, int fileId, String path) {
                if (!current(address, id) || downloadRoot == null) return;
                try {
                    File file = new File(path).getCanonicalFile();
                    if (!file.toPath().startsWith(downloadRoot.toPath()) || !file.isFile() || file.length() == 0) throw new IllegalArgumentException();
                    events.receivedSdkFile(fileId, file); // Still SDK raw Opus; never an upload-ready WAV claim.
                } catch (Exception error) { events.error("received_file_path", -1); }
            }
            @Override public void onDecodeFileMarkers(String address, String id, int fileId, int[] offsets) {
                if (current(address, id)) events.markers(fileId, offsets.clone());
            }
            @Override public void onTransferFileError(String address, String id, int fileId, FileTransferError error) {
                if (current(address, id)) events.error("file_transfer", error.getCode());
            }
        });
        SDKEnvironment environment = credentials.getEnvironment() == HardwareEnvironment.PRODUCTION ? SDKEnvironment.PRODUCTION : SDKEnvironment.DEVELOPMENT;
        SDKInitConfig config = new SDKInitConfig(application, credentials.getUserId(), credentials.getDeviceId(), credentials.getToken(),
                credentials.getLicenseJson(), credentials.getLicenseSignature(), environment, false, null, 3L, 200L, false, 100L, true);
        sdk.initSDK(NO_LOG, config, result -> {
            synchronized (Soundcore1302Bridge.this) {
                if (epoch != generation) return;
                auth = new HardwareAuthResult(result.getSuccess(), result.isOnline(), result.getLicenseValid(), result.getLicenseExpireTime(),
                        result.getTokenExpired(), result.getError() == null ? null : new HardwareAuthError(result.getError().getCode(), result.getError().getMessage()));
                events.auth(auth); // Can arrive twice; consumer must preserve offline and online observations.
            }
        });
    }

    private void requireAuthorized() {
        if (auth == null || !auth.getSuccess() || auth.getTokenExpired() || (!auth.isOnline() && (!auth.getLicenseValid() || auth.getLicenseExpireTime() <= System.currentTimeMillis() / 1000)))
            throw new IllegalStateException("SDK authorization is not ready");
    }
    public synchronized void scan() {
        requireAuthorized(); final long epoch = generation;
        sdk.startScan(true, true, new ArrayList<>(), new OnReceiveScanResult() {
            public void onScanSuccess(BlueDeviceModel device) {
                if (epoch == generation) events.found(device.getProductCode(), device.getDeviceName(), device.getMacAddress(), device.getUuid());
            }
            public void onScanError(int code) { if (epoch == generation) events.error("scan", code); }
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
                try { sdk.getClass().getMethod("syncTime-jXDDuk8", String.class, String.class, int.class)
                        .invoke(sdk, address, id, (int) (System.currentTimeMillis() / 1000)); }
                catch (ReflectiveOperationException error) { events.error("sync_time_binding", -1); }
                sdk.getDeviceInfo(address, id); events.connected();
            }
            public void onDisconnected(String ignored, Integer systemCode, String message) {
                if (current()) { connected = false; mac = null; uuid = null; events.disconnected(systemCode); }
            }
            public void onError(String ignored, SdkException error) { if (current()) { connected = false; events.error("connect", error.getCode()); } }
        });
    }
    public synchronized void listFiles() { requireConnected(); sdk.getAllAudioRecordFiles(mac, uuid); }
    public synchronized void transfer(DeviceRecording recording, File privateDownloadDirectory) throws java.io.IOException {
        requireConnected(); downloadRoot = privateDownloadDirectory.getCanonicalFile();
        if (!downloadRoot.isDirectory()) throw new IllegalArgumentException("Create the app-private download directory first");
        ArrayList<FileInfoModel> files = new ArrayList<>();
        files.add(new FileInfoModel(recording.getFileId(), recording.getEndTime(), recording.getSizeBytes(), recording.getDurationMs(), recording.getCode()));
        sdk.startSyncAudioFile(mac, uuid, files, downloadRoot.getPath(), 300000);
    }
    private void requireConnected() { requireAuthorized(); if (!connected || mac == null || uuid == null) throw new IllegalStateException("Device is not connected"); }
    public synchronized void pauseExistingRecording() { requireConnected(); sdk.pauseRecord(mac, uuid); }
    public synchronized void resumeExistingRecording() { requireConnected(); sdk.resumeRecord(mac, uuid); }
    @Override public synchronized void close() {
        ++generation; ++connectionGeneration; auth = null; mac = null; uuid = null; downloadRoot = null; connected = false; sdk.close();
    }
}

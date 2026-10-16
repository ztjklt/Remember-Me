import AVFoundation
import CryptoKit
import Combine
import Foundation
import SwiftUI

struct RecordingBeanDevice: Identifiable, Equatable, Sendable {
    let id: String
    let mac: String
    let name: String
    let product: String
}
struct RecordingBeanFile: Identifiable, Equatable, Sendable {
    let id: Int32
    let size: Int32
    let duration: Int32
    let endTime: Int32
    let code: Int32
}
struct RecordingDeviceSession: Decodable, Sendable {
    let user_id: String
    let device_id: String
    let token: String
    let license_json: String
    let license_signature: String
    let token_expires_at: Int64
    let environment: String
    let sdk_version: String
    let product_code: String
}
struct BeanDownloadedFile: Sendable {
    let device: RecordingBeanDevice
    let fileID: Int32
    let url: URL
    let root: URL
    var priorityTimeline: WearablePriorityTimeline? = nil
    var sourceOffsetMS: Int = 0
    var sourceDurationMS: Int? = nil
}
enum SoundcoreEvent: Sendable {
    case bound, bindingPending
    case authenticated(Bool), discovered(RecordingBeanDevice), connected(String?), disconnected
    case info(battery: Int, recording: Bool), recording(status: Int32, seconds: Int, fileID: Int32)
    case duration(Int), battery(Int)
    case files([RecordingBeanFile]), download(fileID: Int32, path: String), progress(Int), error(String)
    case markers(fileID: Int32, offsetsMilliseconds: [Int], final: Bool)
    case realtimeFragment(fileID: Int32, sequence: Int, isAppendPreAudio: Bool, data: Data, isMarked: Bool)
}
extension APIClient {
    func recordingDeviceSession(subject: String, installation: String) async throws -> RecordingDeviceSession {
        let body = try JSONSerialization.data(withJSONObject: ["installation_id": installation])
        return try JSONDecoder().decode(RecordingDeviceSession.self, from: await request(
            "/api/v1/subjects/\(subject)/recording-device/session", method: "POST", body: body,
            contentType: "application/json", timeout: 25))
    }
}

@MainActor
final class DeviceConnectionsModel: ObservableObject {
    @Published private(set) var headphonesName: String?
    @Published private(set) var beanState = "未连接"
    @Published private(set) var devices: [RecordingBeanDevice] = []
    @Published private(set) var connected: RecordingBeanDevice?
    @Published private(set) var battery: Int?
    @Published private(set) var recording = false
    @Published private(set) var paused = false
    @Published private(set) var busy = false
    @Published private(set) var progress: Int?
    @Published private(set) var files: [RecordingBeanFile] = []
    @Published private(set) var receivingLiveAudio = false
    @Published private(set) var priorityActive = false
    @Published var message: String?
    var onDownload: ((BeanDownloadedFile, RecordingOwner, [String: String]) async -> Bool)?
    var onAuthorization: ((RecordingOwner, [String: String]) -> Void)?
    @Published var automaticSync = UserDefaults.standard.object(forKey: "device-auto-sync") == nil || UserDefaults.standard.bool(forKey: "device-auto-sync") {
        didSet {
            UserDefaults.standard.set(automaticSync, forKey: "device-auto-sync")
            if automaticSync { beginRealtimeIfNeeded(); processNextImport(); drain() }
            else { receivingLiveAudio = false; realtimeRequested = false; finishLiveCapture() }
        }
    }
    private var authorization: [String: String] = [:]
    private var transferred: Set<String> = []
    private var batchPaused = false
    private var transferLedgerKey: String?
    private var scope: RecordingOwner?
    private var generation = UUID()
    private var audioObserver: AnyCancellable?
    private var sourceActivity = RecordingActivityController()
    private var elapsedSeconds = 0
    private var activeFileID: Int32?
    private var importingFileID: Int32?
    private var adapter: SoundcoreWorkAdapter?
    private var timelines: [Int32: WearablePriorityTimeline] = [:]
    private var liveCapture: SoundcoreLiveCapture?
    private var realtimeRequested = false
    private var fileListReceived = false
    private var pendingImports: [(file: BeanDownloadedFile, signature: String?, purposes: [String: String])] = []
    private var manualMarkers: [Int32: [Int]] = [:]
    private var liveOffsetMS = 0
    private var tailFlushTask: Task<Void, Never>?
    var transferRoot: URL { FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("DeviceTransfers", isDirectory: true) }
    var sdkAvailable: Bool { SoundcoreWorkAdapter.available }
    init() {
        refreshHeadphones()
        audioObserver = NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification).sink { [weak self] _ in
            Task { @MainActor in self?.refreshHeadphones() }
        }
    }
    func refreshHeadphones() {
        let audio = AVAudioSession.sharedInstance()
        let ports = audio.currentRoute.inputs + audio.currentRoute.outputs
        let external: Set<AVAudioSession.Port> = [.bluetoothHFP, .bluetoothA2DP, .bluetoothLE, .headphones, .headsetMic, .usbAudio]
        headphonesName = ports.first { external.contains($0.portType) }?.portName
    }
    func reconcile(owner: RecordingOwner?) {
        if scope != nil && scope != owner { disconnect() }
        refreshHeadphones()
        if let device = connected { adapter?.refresh(device) }
    }
    func scan(pairing: Pairing?, client: APIClient?) async {
        guard !busy, let pairing, let client else { message = "先登录你的记忆空间，再连接录音豆。"; return }
        guard sdkAvailable else { message = "此版本暂不支持录音豆连接，仍可用手机录音。"; return }
        disconnect()
        let owner = RecordingOwner(pairing), request = UUID()
        generation = request; scope = owner; busy = true; beanState = "正在认证"
        let key = "recording-device-installation"
        let installation = UserDefaults.standard.string(forKey: key) ?? UUID().uuidString
        UserDefaults.standard.set(installation, forKey: key)
        do {
            let caps = try await client.capabilities()
            guard request == generation, scope == owner else { return }
            let grants = try await client.consents(subjectID: pairing.subjectID)
            guard request == generation, scope == owner else { return }
            let recording: String
            if let prior = grants.last(where: { $0.scope == "RECORDING" && $0.status == "granted" }) { recording = prior.id }
            else { recording = try await client.grantConsent(subjectID: pairing.subjectID, scope: "RECORDING", evidenceRef: "ios-connect-recording-bean").id }
            guard request == generation, scope == owner else { return }
            let speaker: String
            if let prior = grants.last(where: { $0.scope == "SPEAKER_IDENTIFICATION" && $0.status == "granted" }) { speaker = prior.id }
            else { speaker = try await client.grantConsent(subjectID: pairing.subjectID, scope: "SPEAKER_IDENTIFICATION", evidenceRef: "ios-connect-recording-bean").id }
            guard request == generation, scope == owner else { return }
            authorization = ["device_recording_consent_id": recording, "device_speaker_consent_id": speaker]
            if caps.stt_processing == "cloud" {
                guard let policy = caps.cloud_asr_policy, !policy.isEmpty else { throw APIError.invalidResponse }
                authorization["cloud_asr_policy"] = policy
            }
            let session = try await client.recordingDeviceSession(subject: pairing.subjectID, installation: installation)
            guard request == generation, scope == owner else { return }
            let namespace = owner.storageNamespace
            let adapter = SoundcoreWorkAdapter(root: transferRoot.appendingPathComponent(namespace)) { [weak self] event in
                Task { @MainActor in
                    guard let self, self.generation == request, self.scope == owner else { return }
                    self.receive(event, owner: owner)
                }
            }
            self.adapter = adapter
            try adapter.initialize(session)
        } catch {
            guard generation == request else { return }
            busy = false; beanState = "未连接"; message = "录音豆连接暂未完成，可重试。\n\(error.localizedDescription)"
        }
    }
    func connect(_ device: RecordingBeanDevice) {
        guard !busy, devices.contains(device) else { return }
        busy = true; beanState = "正在连接"; message = nil
        adapter?.connect(device)
    }
    func disconnect() {
        finishLiveCapture()
        generation = UUID(); scope = nil
        adapter?.close(); adapter = nil
        sourceActivity.finish()
        connected = nil; battery = nil; recording = false; paused = false
        authorization = [:]; transferred = []; transferLedgerKey = nil; batchPaused = false
        busy = false; devices = []; files = []; progress = nil; activeFileID = nil; importingFileID = nil; beanState = "未连接"
        liveCapture = nil; timelines = [:]; manualMarkers = [:]; pendingImports = []
        tailFlushTask?.cancel(); tailFlushTask = nil
        receivingLiveAudio = false; priorityActive = false; realtimeRequested = false; fileListReceived = false; liveOffsetMS = 0
    }
    func bind() {
        guard let connected, !busy else { return }
        message = "请将录音器放入充电盒，闪灯时按充电盒按钮确认绑定。"
        adapter?.bind(connected)
    }
    func syncFiles() {
        guard let connected, !busy else { return }
        batchPaused = false; message = nil; adapter?.refresh(connected)
        processNextImport()
        if recording { beginRealtimeIfNeeded() }
        else { adapter?.list(connected) }
    }
    func setPaused() {
        guard let connected, recording else { return }
        adapter?.setPaused(!paused, device: connected)
    }
    func togglePriority() {
        guard recording, !paused, receivingLiveAudio, let fileID = activeFileID else { return }
        let offset = liveOffsetMS
        guard !(timelines[fileID]?.markersMS.contains(offset) ?? false) else {
            message = "请等下一段音频传回，再切换重点；当前重点状态保持。"; return
        }
        manualMarkers[fileID, default: []].append(offset)
        var timeline = timelines[fileID] ?? WearablePriorityTimeline()
        timeline.observe([offset], final: false); timelines[fileID] = timeline
        priorityActive = timeline.markersMS.filter { $0 <= offset }.count % 2 == 1
        message = priorityActive ? "重点已开始，这之后的对话完整保留。" : "重点已结束，后续记忆可整理精简；原音继续保留。"
    }
    func download(_ file: RecordingBeanFile) {
        guard let connected, !busy, !recording else { return }
        guard !transferred.contains(signature(file)) else { message = "这段录音已同步到手机，无需重复取回。"; return }
        busy = true; progress = 0
        do { try adapter?.download(file, from: connected) }
        catch { busy = false; progress = nil; message = "录音暂未传回，设备原文件保留，可重试。" }
    }
    private func receive(_ event: SoundcoreEvent, owner: RecordingOwner) {
        switch event {
        case .authenticated(let valid):
            busy = false
            if valid { beanState = "正在查找录音豆"; onAuthorization?(owner, authorization); adapter?.scan() }
            else { beanState = "认证未完成"; message = "设备认证暂未通过，请重试连接。" }
        case .discovered(let device):
            if !devices.contains(where: { $0.id == device.id }) { devices.append(device) }
        case .connected(let mac):
            guard let chosen = adapter?.selected, chosen.mac == mac else { return }
            connected = chosen; busy = false; beanState = "已连接"
            let identity = owner.storageNamespace + chosen.id
            let key = "bean-transfer-" + SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
            transferLedgerKey = key; transferred = Set(UserDefaults.standard.stringArray(forKey: key) ?? [])
            adapter?.refresh(chosen); adapter?.list(chosen)
        case .disconnected:
            finishLiveCapture()
            sourceActivity.finish(); connected = nil; recording = false; busy = false; paused = false
            receivingLiveAudio = false; realtimeRequested = false; fileListReceived = false
            beanState = "连接已断开"; message = "录音豆连接已断开，设备上的录音不会删除。"
        case .info(let level, let active):
            let wasRecording = recording
            battery = (0...100).contains(level) ? level : nil
            recording = active
            if !active { finishLiveCapture(); sourceActivity.finish(); realtimeRequested = false; receivingLiveAudio = false }
            else if !wasRecording { elapsedSeconds = 0; sourceActivity.start(id: "bean-session-" + UUID().uuidString, source: "录音豆 · 已连接后计时") }
            if active { beginRealtimeIfNeeded() }
        case .recording(let status, _, let fileID):
            // Official states: 0 stop, 1 recording, 2 paused (see adapter constants).
            guard let connected else { return }
            recording = status != 0; paused = status == 2
            if status == 0 {
                finishLiveCapture(); sourceActivity.finish(); realtimeRequested = false; receivingLiveAudio = false
                priorityActive = false; activeFileID = nil; adapter?.list(connected)
            } else {
                if status == 1 && fileID >= 0 && activeFileID != fileID {
                    finishLiveCapture(); activeFileID = fileID; elapsedSeconds = 0; liveOffsetMS = 0
                    sourceActivity.start(id: "bean-\(fileID)", source: "录音豆")
                }
                if paused { finishLiveCapture(); realtimeRequested = false; receivingLiveAudio = false }
                else { beginRealtimeIfNeeded() }
                sourceActivity.update(paused: paused, seconds: elapsedSeconds, source: "录音豆")
            }
        case .duration(let seconds):
            elapsedSeconds = max(0, seconds)
            sourceActivity.update(paused: paused, seconds: elapsedSeconds, source: "录音豆")
        case .battery(let level): battery = (0...100).contains(level) ? level : nil
        case .bound:
            message = "录音豆已配对。"
            if let connected { adapter?.refresh(connected); adapter?.list(connected) }
        case .bindingPending:
            message = "绑定请求已发送。请将录音器放入充电盒，闪灯时按充电盒按钮确认。"
        case .files(let next):
            files = next; fileListReceived = true
            if recording { beginRealtimeIfNeeded() } else { drain() }
        case .markers(let fileID, let offsets, let final):
            var timeline = timelines[fileID] ?? WearablePriorityTimeline()
            timeline.observe(offsets, final: final)
            timeline.observe(manualMarkers[fileID] ?? [], final: false)
            timelines[fileID] = timeline
            if fileID == activeFileID { priorityActive = timeline.markersMS.filter { $0 <= liveOffsetMS }.count % 2 == 1 }
        case .realtimeFragment(let fileID, let sequence, let appended, let data, let marked):
            guard automaticSync, connected != nil, let root = adapter?.root else { return }
            do {
                if recording && !paused { tailFlushTask?.cancel(); tailFlushTask = nil }
                if marked {
                    var timeline = timelines[fileID] ?? WearablePriorityTimeline()
                    timeline.observe([sequence * 20], final: false); timelines[fileID] = timeline
                    priorityActive = timeline.markersMS.count % 2 == 1
                }
                if liveCapture == nil { liveCapture = SoundcoreLiveCapture(root: root) }
                let chunks = try liveCapture!.append(fileID: fileID, sequence: sequence, isAppendPreAudio: appended, data: data)
                activeFileID = fileID; liveOffsetMS = (sequence + 1) * 20
                receivingLiveAudio = recording && !paused
                elapsedSeconds = liveOffsetMS / 1000
                for chunk in chunks { enqueueLiveChunk(chunk) }
                if recording { sourceActivity.update(paused: paused, seconds: elapsedSeconds, source: priorityActive ? "录音豆 · 重点" : "录音豆") }
                if !recording || paused { scheduleTailFlush() }
            } catch { message = "实时音频暂未整理，设备原音保留；结束后可重试同步完整录音。" }
        case .progress(let value): progress = max(0, min(100, value))
        case .download(let fileID, let path):
            guard let connected else { return }
            if liveCapture?.currentFileID == fileID { finishLiveCapture() }
            busy = false; progress = nil
            var download = BeanDownloadedFile(device: connected, fileID: fileID, url: URL(fileURLWithPath: path), root: adapter?.root ?? transferRoot)
            download.priorityTimeline = timelines[fileID]
            // A complete source can validate a previously blocked live replay.
            // It replaces queued partial imports, never already saved originals.
            pendingImports.removeAll { $0.file.fileID == fileID && $0.signature == nil }
            batchPaused = false
            pendingImports.append((download, files.first { $0.id == fileID }.map(signature), authorization))
            processNextImport()
        case .error(let text):
            busy = false; progress = nil; batchPaused = true; message = text
            realtimeRequested = false; receivingLiveAudio = false
        }
    }
    private func beginRealtimeIfNeeded() {
        guard automaticSync, recording, !paused, !realtimeRequested, fileListReceived, let connected else { return }
        tailFlushTask?.cancel(); tailFlushTask = nil
        realtimeRequested = true
        adapter?.beginRealtime(connected)
    }
    private func finishLiveCapture() {
        do { if let chunk = try liveCapture?.finish() { enqueueLiveChunk(chunk) } }
        catch { message = "实时片段暂未归档，设备原音保留，可重新同步。" }
        liveCapture = nil
    }
    private func scheduleTailFlush() {
        tailFlushTask?.cancel()
        let request = generation
        let expectedCapture = liveCapture
        tailFlushTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(500))
            guard !Task.isCancelled, let self, generation == request,
                  (!recording || paused), let expectedCapture, liveCapture === expectedCapture else { return }
            finishLiveCapture()
        }
    }
    private func enqueueLiveChunk(_ chunk: SoundcoreLiveChunk) {
        guard let connected, let root = adapter?.root else { return }
        let observed = timelines[chunk.fileID] ?? WearablePriorityTimeline()
        let timeline = WearablePriorityTimeline(markersMS: observed.markersMS,
            isComplete: chunk.timelineComplete && !observed.hasInvalidMarkers)
        var file = BeanDownloadedFile(device: connected, fileID: chunk.fileID, url: chunk.url, root: root)
        file.priorityTimeline = timeline; file.sourceOffsetMS = chunk.sourceStartMS; file.sourceDurationMS = chunk.sourceEndMS
        pendingImports.append((file, nil, authorization))
        processNextImport()
    }
    private func processNextImport() {
        guard !batchPaused, importingFileID == nil, let next = pendingImports.first,
              let owner = scope, let onDownload else { return }
        importingFileID = next.file.fileID
        let request = generation
        Task {
            let saved = await onDownload(next.file, owner, next.purposes)
            guard generation == request, scope == owner else { return }
            importingFileID = nil
            if saved {
                pendingImports.removeAll { $0.file.url == next.file.url }
                if let signature = next.signature { transferred.insert(signature) }
                if let key = transferLedgerKey { UserDefaults.standard.set(Array(transferred), forKey: key) }
                message = "原音已保存，正在整理记忆；重点内容完整保留。"
                processNextImport(); drain()
            } else if pendingImports.first?.file.url != next.file.url {
                processNextImport()
            } else { batchPaused = true; message = "录音整理暂未完成，原音保留，可重试整理。" }
        }
    }
    private func signature(_ file: RecordingBeanFile) -> String {
        "\(file.id)-\(file.size)-\(file.endTime)-\(file.duration)-\(file.code)"
    }
    private func drain() {
        guard automaticSync, !batchPaused, !busy, !recording, importingFileID == nil, pendingImports.isEmpty, connected != nil else { return }
        let newest = files.map(\.id).max()
        if let next = files.sorted(by: { $0.id < $1.id }).first(where: {
            $0.size > 0 && $0.duration > 0 && !transferred.contains(signature($0)) &&
            (!recording || $0.id != (activeFileID ?? newest))
        }) { download(next) }
    }

}

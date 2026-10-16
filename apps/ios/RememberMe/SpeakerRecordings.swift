import Foundation
import SwiftUI
import AVFoundation
import Combine
import UIKit

struct SpeakerCapabilities: Decodable {
    let available: Bool
    let policy: String
    let notice: String
    let introduction_guide: String
    let identification_scope: String
    var consent_action: String? = nil
    var introduction_optional: Bool? = nil
    var voiceprint_available: Bool? = nil
}
struct SpeakerParticipant: Decodable, Identifiable {
    let speaker_id: String
    let name: String?
    let identity_method: String
    let introduction_segment_ids: [String]
    let consent_segment_ids: [String]
    var voiceprint_status: String? = nil
    var is_subject: Bool? = nil
    var id: String { speaker_id }
}
struct SpeakerSegment: Decodable, Identifiable {
    let segment_id: String
    let start_ms: Int
    let end_ms: Int
    let text: String
    let speaker_id: String?
    let speaker_name: String?
    let attribution: String
    let overlap: Bool
    var timing_estimated: Bool? = nil
    var id: String { segment_id }
    var label: String {
        if overlap { return "声音重叠，未识别" }
        if let name = speaker_name { return name }
        if attribution == "conflicting_introduction" { return "自我介绍有冲突" }
        if let speaker_id, let number = Int(speaker_id.replacingOccurrences(of: "speaker_", with: "")) { return "说话人 \(number + 1)" }
        return "发言（说话人暂未分清）"
    }
}
struct SpeakerReport: Decodable {
    let identification_scope: String
    let protocol_version: String
    let model_version: String
    var identification_status: String? = nil
    let speakers: [SpeakerParticipant]
    let segments: [SpeakerSegment]
}
struct SpeakerRecordingReply: Decodable, Identifiable {
    let recording_id: String
    let status: String
    let recorded_at: String
    let duration_ms: Int
    let consent_id: String
    let policy: String
    let error: String?
    let report: SpeakerReport?
    var id: String { recording_id }
}

extension APIClient {
    func speakerCapabilities(subject: String) async throws -> SpeakerCapabilities {
        try JSONDecoder().decode(SpeakerCapabilities.self, from: await request("/api/v1/subjects/\(subject)/speaker-recordings/capabilities", timeout: 20))
    }
    func speakerRecording(subject: String, id: String) async throws -> SpeakerRecordingReply {
        try JSONDecoder().decode(SpeakerRecordingReply.self, from: await request("/api/v1/subjects/\(subject)/speaker-recordings/\(id)", timeout: 20))
    }
    func identifySpeakers(subject: String, id: String, policy: String) async throws -> SpeakerRecordingReply {
        let body = try JSONSerialization.data(withJSONObject: ["policy": policy, "accept_current_policy": true])
        return try JSONDecoder().decode(SpeakerRecordingReply.self, from: await request("/api/v1/subjects/\(subject)/speaker-recordings/\(id)/process", method: "POST", body: body, contentType: "application/json", timeout: 90))
    }
    func uploadSpeakerRecording(_ local: LocalSpeakerRecording, file: URL, subject: String, consent: String, policy: String) async throws -> SpeakerRecordingReply {
        let boundary = "Speaker-" + UUID().uuidString
        var body = Data()
        func part(_ name: String, _ value: String) {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        part("consent_id", consent); part("policy", policy); part("idempotency_key", local.id)
        part("recorded_at", ISO8601DateFormatter().string(from: local.recordedAt))
        part("duration_ms", String(local.durationMS)); if let count = local.speakerCount { part("speaker_count", String(count)) }; part("participant_consents_confirmed", "true")
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"recording.m4a\"\r\nContent-Type: audio/mp4\r\n\r\n".utf8))
        body.append(try Data(contentsOf: file)); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return try JSONDecoder().decode(SpeakerRecordingReply.self, from: await request("/api/v1/subjects/\(subject)/speaker-recordings", method: "POST", body: body, contentType: "multipart/form-data; boundary=\(boundary)", timeout: 90))
    }
    func deleteSpeakerRecording(subject: String, id: String) async throws {
        let result = try JSONDecoder().decode(SpeakerRecordingReply.self, from: await request("/api/v1/subjects/\(subject)/speaker-recordings/\(id)", method: "DELETE"))
        if let error = result.error { throw APIError.server(503, error) }
    }
}

struct LocalSpeakerRecording: Codable, Identifiable {
    let id: String
    let owner: RecordingOwner
    let recordedAt: Date
    var durationMS: Int
    var speakerCount: Int? = nil
    let participantsConsentedAt: Date
    var consentID: String?
    var policy: String?
    var remoteID: String?
}

@MainActor
final class SpeakerLocalArchive: ObservableObject {
    static let defaultRoot: URL = {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-offline") {
            return FileManager.default.temporaryDirectory.appendingPathComponent("speaker-ui-" + UUID().uuidString)
        }
        #endif
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("GroupRecordings", isDirectory: true)
    }()
    let root: URL
    @Published private(set) var records: [LocalSpeakerRecording] = []
    @Published var error: String?
    init(root: URL? = nil) { self.root = root ?? Self.defaultRoot; reload() }
    func file(_ id: String) -> URL { root.appendingPathComponent(id + ".m4a") }
    func prepare() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        var directory = root, values = URLResourceValues(); values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
    }
    func reload() {
        guard FileManager.default.fileExists(atPath: root.path) else { return }
        do {
            let files = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
            var loaded: [LocalSpeakerRecording] = [], unreadable = 0
            for file in files where file.lastPathComponent.hasSuffix(".group.json") {
                do { loaded.append(try JSONDecoder().decode(LocalSpeakerRecording.self, from: Data(contentsOf: file))) }
                catch { unreadable += 1 }
            }
            records = loaded.sorted { $0.recordedAt > $1.recordedAt }
            error = unreadable == 0 ? nil : "有 \(unreadable) 份多人录音信息暂未读出，其余录音仍可查看，原音没有删除。"
        } catch { self.error = "多人录音档案暂未读出，原音仍然保留。" }
    }
    func save(_ recording: LocalSpeakerRecording, inProgress: Bool = false) throws {
        try prepare()
        let protection: Data.WritingOptions = inProgress ? .completeFileProtectionUntilFirstUserAuthentication : .completeFileProtection
        try JSONEncoder().encode(recording).write(to: root.appendingPathComponent(recording.id + ".group.json"), options: [.atomic, protection])
        try FileManager.default.setAttributes([.protectionKey: inProgress ? FileProtectionType.completeUnlessOpen : FileProtectionType.complete], ofItemAtPath: file(recording.id).path)
        reload()
    }
    func visible(to pairing: Pairing?) -> [LocalSpeakerRecording] {
        guard let pairing else { return [] }
        return records.filter { $0.owner == RecordingOwner(pairing) }
    }
    func remove(_ id: String) throws {
        for url in [file(id), root.appendingPathComponent(id + ".group.json")] where FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
        reload()
    }
}

@MainActor
protocol SpeakerAudioRecording: AnyObject {
    var currentTime: TimeInterval { get }
    func prepare() throws
    func start() -> Bool
    func stop()
}

@MainActor
private final class SystemSpeakerAudioRecording: SpeakerAudioRecording {
    private let audio: AVAudioRecorder
    private let events = RecordingAudioEvents()
    var currentTime: TimeInterval { audio.currentTime }
    init(file: URL, finished: @escaping @MainActor (Bool) -> Void) throws {
        audio = try AVAudioRecorder(url: file, settings: [AVFormatIDKey: Int(kAudioFormatMPEG4AAC), AVSampleRateKey: 44100,
            AVNumberOfChannelsKey: 1, AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue])
        events.recorder = audio; events.finished = finished; audio.delegate = events
    }
    func prepare() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP])
        try session.setActive(true)
        guard audio.prepareToRecord() else { throw APIError.invalidResponse }
    }
    func start() -> Bool { audio.record() }
    func stop() { audio.delegate = nil; events.recorder = nil; events.finished = nil; audio.stop() }
}

@MainActor
protocol SpeakerAudioPlayback: AnyObject {
    var currentTime: TimeInterval { get set }
    var duration: TimeInterval { get }
    func play() -> Bool
    func stop()
}
extension AVAudioPlayer: SpeakerAudioPlayback { }

@MainActor
final class SpeakerRecordingWorkspace: ObservableObject {
    @Published var local: LocalSpeakerRecording?
    @Published var reply: SpeakerRecordingReply?
    @Published var capabilities: SpeakerCapabilities?
    @Published var error: String?
    @Published var busy = false
    @Published var recording = false
    @Published private(set) var starting = false
    @Published private(set) var archiveSavePending = false
    @Published var seconds = 0
    var captureActive: Bool { starting || recording }
    private var recorder: (any SpeakerAudioRecording)?
    private var player: (any SpeakerAudioPlayback)?
    private var timer: Task<Void, Never>?
    private var recordingID: String?
    private weak var activeArchive: SpeakerLocalArchive?
    private var startGeneration = UUID()
    private var playbackGeneration = UUID()
    private var playTask: Task<Void, Never>?
    private var audioObservations: Set<AnyCancellable> = []
    private let permission: @MainActor () async -> Bool
    private let isApplicationActive: @MainActor () -> Bool
    private let makeRecorder: @MainActor (URL, @escaping @MainActor (Bool) -> Void) throws -> any SpeakerAudioRecording
    private let makePlayer: @MainActor (URL) throws -> any SpeakerAudioPlayback
    init(local: LocalSpeakerRecording? = nil, permission: (@MainActor () async -> Bool)? = nil,
         isApplicationActive: @escaping @MainActor () -> Bool = { UIApplication.shared.applicationState == .active },
         recorderFactory: (@MainActor (URL, @escaping @MainActor (Bool) -> Void) throws -> any SpeakerAudioRecording)? = nil,
         playerFactory: (@MainActor (URL) throws -> any SpeakerAudioPlayback)? = nil) {
        self.local = local
        self.permission = permission ?? { await AVAudioApplication.requestRecordPermission() }
        self.isApplicationActive = isApplicationActive
        self.makeRecorder = recorderFactory ?? { try SystemSpeakerAudioRecording(file: $0, finished: $1) }
        self.makePlayer = playerFactory ?? { try AVAudioPlayer(contentsOf: $0) }
        NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)
            .receive(on: DispatchQueue.main).sink { [weak self] notification in
                let type = (notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? NSNumber)?.uintValue
                MainActor.assumeIsolated {
                    if type == AVAudioSession.InterruptionType.began.rawValue { self?.handleAudioFailure("录音被系统中断，当前原音已保留。") }
                }
            }.store(in: &audioObservations)
        NotificationCenter.default.publisher(for: AVAudioSession.mediaServicesWereResetNotification)
            .receive(on: DispatchQueue.main).sink { [weak self] _ in
                MainActor.assumeIsolated { self?.handleAudioFailure("系统音频服务已重置，当前原音已保留。请重新开始新录音。") }
            }.store(in: &audioObservations)
        NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification)
            .receive(on: DispatchQueue.main).sink { [weak self] notification in
                let reason = (notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? NSNumber)?.uintValue
                MainActor.assumeIsolated {
                    if reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue { self?.handleAudioFailure("麦克风设备已断开，当前原音已保留。") }
                }
            }.store(in: &audioObservations)
    }
    func start(pairing: Pairing, archive: SpeakerLocalArchive, consented: Bool, speakerCount: Int? = nil) async {
        guard !busy, !recording, local == nil, consented else { return }
        let generation = UUID(); startGeneration = generation
        busy = true; starting = true; error = nil
        defer { if generation == startGeneration { busy = false; starting = false } }
        let granted = await permission()
        guard generation == startGeneration, !Task.isCancelled else { return }
        guard granted else { error = "麦克风权限已拒绝，请在系统设置中打开。"; return }
        guard isApplicationActive() else { return }
        stopPlayback()
        var prepared: (any SpeakerAudioRecording)?
        do {
            try archive.prepare()
            let now = Date()
            let row = LocalSpeakerRecording(id: UUID().uuidString, owner: RecordingOwner(pairing), recordedAt: now,
                durationMS: 0, speakerCount: speakerCount, participantsConsentedAt: now, policy: capabilities?.policy)
            let audio = try makeRecorder(archive.file(row.id)) { [weak self] succeeded in
                guard let self, self.recordingID == row.id, self.recording else { return }
                self.finish(archive: archive)
                if !succeeded { self.error = "录音被系统中断，当前原音已保留。" }
            }
            prepared = audio
            try audio.prepare()
            // Journal owner/consent before opening the microphone. A failed
            // journal must never leave a running recorder with no archive row.
            try archive.save(row, inProgress: true)
            local = row; recorder = audio; activeArchive = archive; recordingID = row.id
            recording = true; seconds = 0
            guard audio.start() else { throw APIError.invalidResponse }
            guard recording, recordingID == row.id else { return }
            timer?.cancel()
            timer = Task { [weak self] in
                while !Task.isCancelled {
                    do { try await Task.sleep(for: .milliseconds(500)) } catch { return }
                    guard self?.updateRecordingClock(id: row.id) == true else { return }
                }
            }
        } catch {
            if recording { finish(archive: archive) } else { prepared?.stop() }
            recorder?.stop(); recorder = nil; recordingID = nil; recording = false
            self.error = "录音未能开始，已有原音仍保留：\(error.localizedDescription)"
        }
    }
    func cancelPendingStart() {
        startGeneration = UUID()
        if starting { starting = false; busy = false }
    }
    private func updateRecordingClock(id: String) -> Bool {
        guard recording, recordingID == id, let recorder else { return false }
        seconds = max(0, Int(recorder.currentTime.isFinite ? recorder.currentTime : 0))
        return true
    }
    func handleAudioFailure(_ message: String) {
        cancelPendingStart(); stopPlayback()
        guard recording, let archive = activeArchive else { return }
        finish(archive: archive); error = message
    }
    static func savedDuration(_ url: URL) -> Int? {
        guard let audio = try? AVAudioPlayer(contentsOf: url), audio.duration.isFinite,
              audio.duration > 0, audio.duration < Double(Int.max / 1000) else { return nil }
        return Int(audio.duration * 1000)
    }
    func finish(archive: SpeakerLocalArchive) {
        guard recording, var local else { return }
        let duration = recorder?.currentTime ?? 0
        recording = false; recordingID = nil
        recorder?.stop(); recorder = nil; timer?.cancel(); timer = nil; activeArchive = nil
        let milliseconds = duration.isFinite && duration >= 0 && duration < Double(Int.max / 1000) ? Int(duration * 1000) : 0
        local.durationMS = Self.savedDuration(archive.file(local.id)) ?? milliseconds
        seconds = local.durationMS / 1000; self.local = local
        do { try archive.save(local); archiveSavePending = false }
        catch { archiveSavePending = true; self.error = "原音已保留，档案暂未保存，请重试保存。" }
    }
    func retryArchiveSave(archive: SpeakerLocalArchive) {
        guard !recording, let local else { return }
        do { try archive.save(local); archiveSavePending = false; error = nil }
        catch { archiveSavePending = true; self.error = "原音已保留，档案暂未保存，请重试保存。" }
    }
    func play(archive: SpeakerLocalArchive, segment: SpeakerSegment? = nil) {
        guard !recording, let local else { return }
        stopPlayback()
        do {
            let audio = try makePlayer(archive.file(local.id))
            guard audio.duration.isFinite, audio.duration > 0, audio.duration < Double(Int.max / 1000) else { throw APIError.invalidResponse }
            let start = max(0, Double(segment?.start_ms ?? 0) / 1000)
            let end = min(audio.duration, Double(segment?.end_ms ?? Int(audio.duration * 1000)) / 1000)
            guard start.isFinite, end.isFinite, end > start else { throw APIError.invalidResponse }
            player = audio; let generation = playbackGeneration
            audio.currentTime = start
            guard audio.play() else { stopPlayback(); throw APIError.invalidResponse }
            if segment != nil {
                playTask = Task { [weak self, weak audio] in
                    do { try await Task.sleep(for: .seconds(end - start)) } catch { return }
                    guard let self, let audio, self.playbackGeneration == generation, self.player === audio else { return }
                    self.stopPlayback()
                }
            }
        } catch { self.error = "这段原音暂时不能播放。" }
    }
    func stopPlayback() { playbackGeneration = UUID(); playTask?.cancel(); playTask = nil; player?.stop(); player = nil }
}

#if DEBUG
extension SpeakerRecordingWorkspace {
    func showIsolatedPreview() {
        let owner = RecordingOwner(Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64), token: "fixture", actorID: "fixture", subjectID: "fixture", consentID: "fixture"))
        local = LocalSpeakerRecording(id: UUID().uuidString, owner: owner, recordedAt: Date(), durationMS: 20000, participantsConsentedAt: Date())
        let body = #"{"recording_id":"fixture","status":"ready","recorded_at":"2026-10-15T00:00:00Z","duration_ms":20000,"consent_id":"fixture","policy":"fixture","error":null,"report":{"identification_scope":"recording","protocol_version":"spoken-introductions-v1","model_version":"fictional-ui-only","speakers":[{"speaker_id":"speaker_0","name":"小王","identity_method":"spoken_introduction","introduction_segment_ids":["segment_0"],"consent_segment_ids":["segment_0"]},{"speaker_id":"speaker_1","name":"小李","identity_method":"spoken_introduction","introduction_segment_ids":["segment_1"],"consent_segment_ids":["segment_1"]}],"segments":[{"segment_id":"segment_2","start_ms":9000,"end_ms":13000,"text":"那天我们一起去种树。","speaker_id":"speaker_0","speaker_name":"小王","attribution":"spoken_introduction","overlap":false},{"segment_id":"segment_3","start_ms":14000,"end_ms":18000,"text":"我还记得那棵树。","speaker_id":"speaker_1","speaker_name":"小李","attribution":"spoken_introduction","overlap":false},{"segment_id":"segment_4","start_ms":18000,"end_ms":19000,"text":"未确定归属的发言。","speaker_id":null,"speaker_name":null,"attribution":"overlap","overlap":true}]}}"#
        reply = try! JSONDecoder().decode(SpeakerRecordingReply.self, from: Data(body.utf8))
    }
}
#endif

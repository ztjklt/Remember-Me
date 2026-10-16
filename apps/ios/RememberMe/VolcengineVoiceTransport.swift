import Foundation
import AVFoundation
@preconcurrency import VolcEngineRTC

enum DomesticVoiceConnectionState: Sendable { case recovering, connected }

/// Only transient amplitude is retained; neither meter saves audio or requests capture.
enum VoiceAudioMeter {
    static func normalized(_ level: Double?) -> Double? {
        guard let level, level.isFinite else { return nil }
        return min(1, max(0, level))
    }
    static func decibels(_ value: Double) -> Double {
        guard value.isFinite else { return 0 }
        return min(1, max(0, (value + 60) / 60))
    }
}

struct VoicePCM16AudioMeter {
    private var squareSum = 0.0
    private var sampleCount = 0
    /// The personal stream is little-endian, signed 16-bit mono at 24 kHz.
    /// Publish at most once per 100 ms of pushed audio.
    mutating func append(_ data: Data) -> Double? {
        guard !data.isEmpty, data.count.isMultiple(of: 2) else { return nil }
        data.withUnsafeBytes { bytes in
            for offset in stride(from: 0, to: bytes.count, by: 2) {
                let sample = Double(Int16(littleEndian: bytes.loadUnaligned(fromByteOffset: offset, as: Int16.self))) / 32768
                squareSum += sample * sample
            }
        }
        sampleCount += data.count / 2
        guard sampleCount >= 2400 else { return nil }
        let rms = sqrt(squareSum / Double(sampleCount))
        squareSum = 0; sampleCount = 0
        return rms > 0 ? VoiceAudioMeter.decibels(20 * log10(rms)) : 0
    }
}

@MainActor
protocol DomesticVoiceTransport: AnyObject {
    var failureMessage: String? { get }
    var onConversation: (@MainActor (VolcengineVoiceTransport.Conversation) -> Void)? { get set }
    var onAgentConnected: (@MainActor () -> Void)? { get set }
    var onFailure: (@MainActor () -> Void)? { get set }
    var onCaptured: (@MainActor (String, Data) -> Void)? { get set }
    var onSample: (@MainActor (String, Data) -> Void)? { get set }
    var onSpeechBegan: (@MainActor () -> Void)? { get set }
    var onConnectionChanged: (@MainActor (DomesticVoiceConnectionState) -> Void)? { get set }
    var onAudioLevels: (@MainActor (Double?, Double?) -> Void)? { get set }
    func connect(_ ticket: VoiceCallTicket) async throws
    func microphone(_ enabled: Bool) throws
    func selectSpeaker(_ enabled: Bool) throws
    func volume(_ value: Double)
    func disconnect() async
    func playPersonalAudio(_ bytes: URLSession.AsyncBytes) async throws
    func stopPersonalAudio()
    func diagnostic(_ code: String)
    func captureTurn(_ round: Int)
    func resumeAfterReconnect(microphone enabled: Bool) throws
}

extension DomesticVoiceTransport {
    var failureMessage: String? { nil }
    var onAudioLevels: (@MainActor (Double?, Double?) -> Void)? {
        get { nil }
        set { }
    }
}

/// The SDK owns media only. Backend tickets, validated Twin answers, and controls
/// stay behind our API; no ASR/LLM/TTS key or arbitrary-text control in the client.
@MainActor
final class VolcengineVoiceTransport: NSObject, DomesticVoiceTransport, ByteRTCEngineDelegate, ByteRTCRoomDelegate {
    struct Conversation: Decodable, Sendable {
        struct StageInfo: Decodable, Sendable { let Code: Int }
        struct ErrorDetail: Decodable, Sendable {
            let ErrorCode: Int?
            let Code: Int?
            var numericCode: Int? { ErrorCode ?? Code }
        }
        let TaskId: String
        let RoundID: Int
        let EventTime: Int64
        let Stage: StageInfo
        var ErrorInfo: ErrorDetail? = nil
    }
    var onConversation: (@MainActor (Conversation) -> Void)?
    var onAgentConnected: (@MainActor () -> Void)?
    var onFailure: (@MainActor () -> Void)?
    private(set) var failureMessage: String?
    var onCaptured: (@MainActor (String, Data) -> Void)?
    var onSample: (@MainActor (String, Data) -> Void)?
    var onSpeechBegan: (@MainActor () -> Void)?
    var onConnectionChanged: (@MainActor (DomesticVoiceConnectionState) -> Void)?
    var onAudioLevels: (@MainActor (Double?, Double?) -> Void)?
    private var microphoneAudioLevel: Double?
    private var playbackAudioLevel: Double?
    private var microphoneReportTime: ContinuousClock.Instant?
    private var playbackReportTime: ContinuousClock.Instant?
    private var playbackEnabled = true
    private func reportAudioLevels() {
        guard connected, !closing, !recovering else { onAudioLevels?(nil, nil); return }
        let now = ContinuousClock.now
        let microphoneFresh = microphoneReportTime.map { $0.duration(to: now) < .milliseconds(350) } ?? false
        let playbackFresh = playbackReportTime.map { $0.duration(to: now) < .milliseconds(350) } ?? false
        onAudioLevels?(diagnostics.microphoneEnabled && microphoneFresh ? microphoneAudioLevel : nil,
                       playbackEnabled && playbackFresh ? playbackAudioLevel : nil)
    }
    private func clearAudioLevels() {
        microphoneAudioLevel = nil; playbackAudioLevel = nil
        microphoneReportTime = nil; playbackReportTime = nil
        onAudioLevels?(nil, nil)
    }
    private var personalSpeechReports = 0
    private let microphoneBuffer = DomesticMicrophoneBuffer()
    private var samplePCM = Data()
    private var sampleCount = 0
    private var lastCapturedRound = -1
    // The SDK returns an internal implementation without exporting its public
    // base-class symbol. Retain playback operations without linking its metadata.
    private var personalPlayerStop: (() -> Void)?
    private var personalPlayerVolume: ((Int32) -> Void)?
    private var personalPlaybackID = UUID()
    private var engine: ByteRTCEngine?
    private var room: ByteRTCRoom?
    private var ticket: VoiceCallTicket?
    private var joining: CheckedContinuation<Void, Error>?
    private var leaving: CheckedContinuation<Void, Never>?
    private var joinTimeout: Task<Void, Never>?
    private var leaveTimeout: Task<Void, Never>?
    private var captureStarted = false
    private var connected = false
    private var closing = false
    private var recovering = false
    private var recoveryConnectionAvailable = false
    private var latestEventTime: Int64 = -1
    private var latestRound = -1
    /// Latest call only: no audio, text, identities, room IDs, or credentials.
    private struct Diagnostics: Codable {
        var startedAt = Date()
        var ended = false
        var joined = false
        var agentJoined = false
        var captureStarted = false
        var microphoneEnabled = false
        var publishRequested = false
        var localReports = 0
        var audibleReports = 0
        var maximumVolume = 0
        var maximumSendKbps: Float = 0
        var joinedUsers = 0
        var matchingAgentJoins = 0
        // Separate delivery, decoding, and validation without retaining messages.
        var roomBinaryMessages = 0
        var nonConversationRoomMessages = 0
        var conversationDecodeFailures = 0
        var conversationMessagesDecoded = 0
        var conversationRejectedSender = 0
        var conversationRejectedTask = 0
        var conversationRejectedStaleRound = 0
        var conversationRejectedStaleTime = 0
        var conversationEvents = 0
        var lastStage: Int?
        var roomState: Int?
        var audioState: Int?
        var audioError: Int?
        var engineError: Int?
        var agentErrorCode: Int?
        var connectionState: Int?
        var capturedSegments = 0
        var personalAudioPushes = 0
        var personalAudioRebuffers = 0
        var personalAudioMaximumLatenessMs = 0
        var lastDiagnostic: String?
        var diagnosticEvents: [String] = []
    }
    private var diagnostics = Diagnostics()
    func diagnostic(_ code: String) {
        // Codes are compile-time identifiers, never network messages or payloads.
        diagnostics.lastDiagnostic = code
        diagnostics.diagnosticEvents.append(code)
        diagnostics.diagnosticEvents = Array(diagnostics.diagnosticEvents.suffix(12)); saveDiagnostics()
    }
    func captureTurn(_ round: Int) {
        guard !closing, !recovering, ticket?.capture_enabled == true, round >= 0, round > lastCapturedRound else { return }
        lastCapturedRound = round
        guard let pcm = microphoneBuffer.drain() else { return }
        diagnostics.capturedSegments += 1
        onCaptured?("ve_" + String(round), DomesticMicrophoneBuffer.wave(pcm))
        if sampleCount < 3 {
            samplePCM.append(pcm)
            if samplePCM.count >= 160000 {
                sampleCount += 1
                onSample?("vs_" + String(sampleCount), DomesticMicrophoneBuffer.wave(Data(samplePCM.prefix(480000))))
                samplePCM.removeAll()
            }
        }
        saveDiagnostics()
    }
    private func saveDiagnostics() {
        guard let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return }
        var directory = base.appendingPathComponent("VoiceDiagnostics", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            var values = URLResourceValues(); values.isExcludedFromBackup = true
            try directory.setResourceValues(values)
            let data = try JSONEncoder().encode(diagnostics)
            try data.write(to: directory.appendingPathComponent("latest.json"), options: [.atomic, .completeFileProtection])
        } catch { /* Diagnostics must never prevent calling or contain error strings. */ }
    }

    func connect(_ ticket: VoiceCallTicket) async throws {
        guard engine == nil, let appID = ticket.app_id else { throw APIError.invalidResponse }
        self.ticket = ticket
        let config = ByteRTCEngineConfig()
        config.appID = appID
        config.parameters = ["rtc.fg_config": "aigc_media_360=true"]
        guard let created = ByteRTCEngine.createRTCEngine(config, delegate: self) else { throw APIError.invalidResponse }
        engine = created
        saveDiagnostics()
        let properties = ByteRTCAudioPropertiesConfig()
        properties.interval = 100; properties.enableVad = true
        _ = created.enableAudioPropertiesReport(properties)
        if ticket.capture_enabled == true {
            let format = ByteRTCAudioFormat()
            format.sampleRate = ByteRTCAudioSampleRate(rawValue: 16000)!
            format.channel = ByteRTCAudioChannel(rawValue: 1)!
            guard created.enableAudioFrameCallback(.record, format: format) == 0,
                  created.registerAudioFrameObserver(microphoneBuffer) == 0 else { throw APIError.invalidResponse }
        }
        guard created.setAudioScenario(.aiClient) == 0,
              created.setDefaultAudioRoute(.speakerphone) == 0,
              let joinedRoom = created.createRTCRoom(ticket.room) else { throw APIError.invalidResponse }
        room = joinedRoom; joinedRoom.delegate = self
        let user = ByteRTCUserInfo(); user.userId = ticket.participant_identity
        let roomConfig = ByteRTCRoomConfig()
        roomConfig.isPublishAudio = true; roomConfig.isPublishVideo = false
        roomConfig.isAutoSubscribeAudio = true; roomConfig.isAutoSubscribeVideo = false
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            joining = continuation
            let code = joinedRoom.joinRoom(ticket.token, userInfo: user, userVisibility: true, roomConfig: roomConfig)
            if code != 0 { finishJoin(APIError.invalidResponse); return }
            joinTimeout = Task { [weak self] in
                try? await Task.sleep(for: .seconds(15))
                guard !Task.isCancelled else { return }
                self?.finishJoin(APIError.invalidResponse)
            }
        }
    }
    private func finishJoin(_ error: Error? = nil) {
        joinTimeout?.cancel(); joinTimeout = nil
        let continuation = joining; joining = nil
        if let error { continuation?.resume(throwing: error) }
        else { connected = true; diagnostics.joined = true; saveDiagnostics(); continuation?.resume() }
    }
    func microphone(_ enabled: Bool) throws {
        guard let engine, connected, !closing else { throw APIError.invalidResponse }
        // A call lease must be checked by the model before capture can resume.
        if recovering {
            guard engine.muteAudioCapture(true) == 0 else { throw APIError.invalidResponse }
            microphoneBuffer.setEnabled(false)
            diagnostics.microphoneEnabled = false; saveDiagnostics()
            return
        }
        if enabled, !captureStarted {
            guard engine.startAudioCapture() == 0 else { throw APIError.invalidResponse }
            captureStarted = true
            diagnostics.captureStarted = true
        }
        guard engine.muteAudioCapture(!enabled) == 0 else { throw APIError.invalidResponse }
        if enabled { guard room?.publishStreamAudio(true) == 0 else { throw APIError.invalidResponse } }
        diagnostics.microphoneEnabled = enabled
        microphoneAudioLevel = nil; microphoneReportTime = nil
        reportAudioLevels()
        microphoneBuffer.setEnabled(enabled && ticket?.capture_enabled == true)
        if enabled { diagnostics.publishRequested = true }
        saveDiagnostics()
    }
    func resumeAfterReconnect(microphone enabled: Bool) throws {
        guard recovering, recoveryConnectionAvailable, connected, !closing else { throw APIError.invalidResponse }
        recovering = false; recoveryConnectionAvailable = false
        try microphone(enabled)
    }
    func selectSpeaker(_ enabled: Bool) throws {
        guard let engine, !closing,
              engine.setDefaultAudioRoute(enabled ? .speakerphone : .earpiece) == 0,
              engine.setAudioRoute(enabled ? .speakerphone : .default) == 0 else { throw APIError.invalidResponse }
    }
    func volume(_ value: Double) {
        let level = recovering ? 0 : value
        playbackEnabled = level > 0
        if !playbackEnabled { playbackAudioLevel = nil; playbackReportTime = nil; reportAudioLevels() }
        _ = engine?.setPlaybackVolume(Int(level * 100))
        personalPlayerVolume?(Int32(level * 100))
    }
    func stopPersonalAudio() {
        personalPlaybackID = UUID(); personalPlayerStop?()
        personalPlayerStop = nil; personalPlayerVolume = nil
        playbackAudioLevel = nil; playbackReportTime = nil; reportAudioLevels()
    }
    func playPersonalAudio(_ bytes: URLSession.AsyncBytes) async throws {
        stopPersonalAudio()
        guard !closing, !recovering, let player = engine?.getMediaPlayer(0) else { throw APIError.invalidResponse }
        let playbackID = personalPlaybackID
        personalPlayerStop = { _ = player.stop() }
        personalPlayerVolume = { _ = player.setVolume($0, type: .playout) }
        personalSpeechReports = 0
        playbackEnabled = true
        _ = engine?.setPlaybackVolume(100); _ = player.setVolume(100, type: .playout)
        let source = ByteRTCMediaPlayerCustomSource(); source.mode = .push; source.type = .raw
        let config = ByteRTCMediaPlayerConfig(); config.type = .playout; config.playCount = 1; config.autoPlay = true
        defer { if personalPlaybackID == playbackID { stopPersonalAudio() } }
        guard player.open(with: source, config: config) == 0 else { throw APIError.invalidResponse }
        var meter = VoicePCM16AudioMeter()
        let statistics = try await PersonalVoicePCMPlayback.play(bytes, clock: ContinuousClock()) { data in
            guard !self.closing, !self.recovering, self.personalPlaybackID == playbackID,
                  !Task.isCancelled else { throw CancellationError() }
            let frame = ByteRTCAudioFrame(); frame.buffer = data
            frame.samples = Int32(data.count / 2)
            frame.sampleRate = ByteRTCAudioSampleRate(rawValue: 24000)!
            frame.channel = ByteRTCAudioChannel(rawValue: 1)!
            guard player.pushExternalAudioFrame(frame) == 0 else { throw APIError.invalidResponse }
            if let level = meter.append(data) {
                self.playbackAudioLevel = level; self.playbackReportTime = .now; self.reportAudioLevels()
            }
        }
        guard personalPlaybackID == playbackID else { throw CancellationError() }
        diagnostics.personalAudioPushes += statistics.pushes
        diagnostics.personalAudioRebuffers += statistics.rebufferCount
        let late = statistics.maximumLateness.components
        diagnostics.personalAudioMaximumLatenessMs = max(diagnostics.personalAudioMaximumLatenessMs,
            Int(late.seconds * 1000 + late.attoseconds / 1_000_000_000_000_000))
        saveDiagnostics()
    }
    func disconnect() async {
        guard !closing else { return }
        closing = true; clearAudioLevels(); onAudioLevels = nil
        onConversation = nil; onAgentConnected = nil; onFailure = nil
        onCaptured = nil; onSample = nil; onSpeechBegan = nil; onConnectionChanged = nil
        recovering = false; recoveryConnectionAvailable = false
        microphoneBuffer.setEnabled(false); samplePCM.removeAll(); stopPersonalAudio()
        _ = engine?.registerAudioFrameObserver(nil)
        diagnostics.ended = true; saveDiagnostics()
        _ = engine?.muteAudioCapture(true); _ = engine?.setPlaybackVolume(0); _ = engine?.stopAudioCapture()
        finishJoin(CancellationError())
        if let room, connected {
            await withCheckedContinuation { continuation in
                leaving = continuation
                if room.leave() != 0 { finishLeave(); return }
                leaveTimeout = Task { [weak self] in
                    try? await Task.sleep(for: .seconds(1))
                    guard !Task.isCancelled else { return }
                    self?.finishLeave()
                }
            }
        }
        room?.delegate = nil; room?.destroy(); room = nil
        if engine != nil { ByteRTCEngine.destroyRTCEngine() }
        engine = nil; ticket = nil; connected = false
    }
    private func finishLeave() {
        leaveTimeout?.cancel(); leaveTimeout = nil
        let continuation = leaving; leaving = nil; continuation?.resume()
    }
    nonisolated static func decode(_ data: Data) -> Conversation? {
        guard data.count >= 8, data.count <= 64 * 1024, data.prefix(4) == Data("conv".utf8) else { return nil }
        let bytes = [UInt8](data.prefix(8))
        let length = bytes[4...7].reduce(0) { ($0 << 8) | Int($1) }
        guard length == data.count - 8,
              let value = try? JSONDecoder().decode(Conversation.self, from: data.dropFirst(8)),
              (0...5).contains(value.Stage.Code), value.RoundID >= 0 else { return nil }
        return value
    }
    nonisolated func rtcRoom(_ rtcRoom: ByteRTCRoom, onRoomStateChanged roomId: String,
                            withUid uid: String, state: Int, extraInfo: String) {
        Task { @MainActor [weak self] in
            guard let self, self.room === rtcRoom else { return }
            self.receiveRoomState(state)
        }
    }
    func receiveRoomState(_ state: Int) {
        diagnostics.roomState = state; saveDiagnostics()
        if closing { finishLeave(); return }
        // The bundled SDK documents automatic retry for publish/subscribe
        // warnings (-2002/-2003/-2004), and notification-only -2013.
        // Unknown codes and authorization/departure errors still fail closed.
        if [-2002, -2003, -2004, -2013].contains(state) {
            diagnostic("rtc_room_notification_warning"); return
        }
        if state == 0, !connected { finishJoin() }
        else if state != 0 {
            failureMessage = "国内语音房间连接出错（错误码 \(state)），请重新开始。"
            finishJoin(APIError.invalidResponse); onFailure?()
        }
    }
    nonisolated func rtcRoom(_ rtcRoom: ByteRTCRoom, onRoomBinaryMessageReceived uid: String, message: Data) {
        let value = Self.decode(message)
        let hasConversationTag = message.prefix(4) == Data("conv".utf8)
        Task { @MainActor [weak self] in
            guard let self, !self.closing, self.room === rtcRoom else { return }
            self.diagnostics.roomBinaryMessages += 1
            guard let value else {
                if hasConversationTag { self.diagnostics.conversationDecodeFailures += 1 }
                else { self.diagnostics.nonConversationRoomMessages += 1 }
                self.saveDiagnostics(); return
            }
            self.diagnostics.conversationMessagesDecoded += 1
            guard uid == self.ticket?.bot_identity else {
                self.diagnostics.conversationRejectedSender += 1
                self.saveDiagnostics(); return
            }
            guard value.TaskId == self.ticket?.call_id else {
                self.diagnostics.conversationRejectedTask += 1
                self.saveDiagnostics(); return
            }
            guard value.RoundID >= self.latestRound else {
                self.diagnostics.conversationRejectedStaleRound += 1
                self.saveDiagnostics(); return
            }
            guard value.EventTime > self.latestEventTime else {
                self.diagnostics.conversationRejectedStaleTime += 1
                self.saveDiagnostics(); return
            }
            self.latestEventTime = value.EventTime; self.latestRound = value.RoundID
            self.diagnostics.conversationEvents += 1; self.diagnostics.lastStage = value.Stage.Code
            if value.Stage.Code == 2 { self.captureTurn(value.RoundID) }
            self.saveDiagnostics()
            if value.Stage.Code == 0 {
                let code = value.ErrorInfo?.numericCode
                self.diagnostics.agentErrorCode = code
                self.failureMessage = code.map { "国内语音服务出错（错误码 \($0)），请重新开始。" }
                    ?? "国内语音服务出错，请重新开始。"
                self.diagnostic("agent_task_error")
                self.onFailure?()
            }
            else { self.onConversation?(value) }
        }
    }
    nonisolated func rtcRoom(_ rtcRoom: ByteRTCRoom, onUserJoined userInfo: ByteRTCUserInfo) {
        let uid = userInfo.userId
        Task { @MainActor [weak self] in
            guard let self, !self.closing, self.room === rtcRoom else { return }
            self.diagnostics.joinedUsers += 1
            guard uid == self.ticket?.bot_identity else { self.saveDiagnostics(); return }
            self.diagnostics.matchingAgentJoins += 1
            self.diagnostics.agentJoined = true; self.saveDiagnostics()
            self.onAgentConnected?()
        }
    }
    nonisolated func rtcEngine(_ engine: ByteRTCEngine, onFirstRemoteAudioFrame streamId: String, info: ByteRTCStreamInfo) {
        let uid = info.userId
        Task { @MainActor [weak self] in
            guard let self, !self.closing, self.engine === engine, uid == self.ticket?.bot_identity else { return }
            self.onAgentConnected?()
        }
    }
    nonisolated func rtcEngine(_ engine: ByteRTCEngine, onError errorCode: ByteRTCErrorCode) {
        Task { @MainActor [weak self] in
            guard let self, self.engine === engine, !self.closing else { return }
            self.diagnostics.engineError = Int(errorCode.rawValue); self.saveDiagnostics()
            self.finishJoin(APIError.invalidResponse); self.onFailure?()
        }
    }
    nonisolated func rtcEngine(_ engine: ByteRTCEngine, onLocalAudioPropertiesReport infos: [ByteRTCLocalAudioPropertiesInfo]) {
        let volume = infos.map { $0.audioPropertiesInfo.linearVolume }.max() ?? 0
        let decibels = infos.map { $0.audioPropertiesInfo.nonlinearVolume }.max()
        let speech = infos.contains { $0.audioPropertiesInfo.vad > 0 && $0.audioPropertiesInfo.linearVolume > 25 }
        Task { @MainActor [weak self] in
            guard let self, self.engine === engine, !self.closing else { return }
            self.microphoneAudioLevel = decibels.map { VoiceAudioMeter.decibels(Double($0)) }
            self.microphoneReportTime = .now
            self.reportAudioLevels()
            let firstReport = self.diagnostics.localReports == 0
            let firstAudible = volume > 25 && self.diagnostics.audibleReports == 0
            self.diagnostics.localReports += 1
            if volume > 25 { self.diagnostics.audibleReports += 1 }
            self.diagnostics.maximumVolume = max(self.diagnostics.maximumVolume, volume)
            if self.personalPlayerStop != nil, self.diagnostics.microphoneEnabled {
                self.personalSpeechReports = speech ? self.personalSpeechReports + 1 : 0
                if self.personalSpeechReports == 3 { self.onSpeechBegan?() }
            } else { self.personalSpeechReports = 0 }
            if firstReport || firstAudible { self.saveDiagnostics() }
        }
    }
    nonisolated func rtcEngine(_ engine: ByteRTCEngine, onRemoteAudioPropertiesReport infos: [ByteRTCRemoteAudioPropertiesInfo], totalRemoteVolume: Int) {
        // Match both room and bot; unrelated remote participants never drive the Twin.
        let levels = infos.map { ($0.streamInfo.roomId, $0.streamInfo.userId, $0.audioPropertiesInfo.nonlinearVolume) }
        Task { @MainActor [weak self] in
            guard let self, self.engine === engine, !self.closing, !self.recovering else { return }
            if self.personalPlayerStop != nil { return }
            let decibels = levels.filter { $0.0 == self.ticket?.room && $0.1 == self.ticket?.bot_identity }
                .map(\.2).max()
            self.playbackAudioLevel = decibels.map { VoiceAudioMeter.decibels(Double($0)) }
            self.playbackReportTime = .now
            self.reportAudioLevels()
        }
    }
    nonisolated func rtcRoom(_ rtcRoom: ByteRTCRoom, onLocalStreamStats streamId: String,
                            info: ByteRTCStreamInfo, stats: ByteRTCLocalStreamStats) {
        let bitrate = stats.audioStats.sentKBitrate
        Task { @MainActor [weak self] in
            guard let self, self.room === rtcRoom, !self.closing else { return }
            let firstSent = bitrate > 0 && self.diagnostics.maximumSendKbps == 0
            self.diagnostics.maximumSendKbps = max(self.diagnostics.maximumSendKbps, bitrate)
            if firstSent { self.saveDiagnostics() }
        }
    }
    nonisolated func rtcEngine(_ engine: ByteRTCEngine, onLocalAudioStateChanged source: ByteRTCAudioSource?,
                              state: ByteRTCLocalAudioStreamState, error: ByteRTCLocalAudioStreamError) {
        Task { @MainActor [weak self] in
            guard let self, self.engine === engine, !self.closing else { return }
            self.receiveLocalAudioState(state: state, error: error)
        }
    }
    func receiveLocalAudioState(state: ByteRTCLocalAudioStreamState, error: ByteRTCLocalAudioStreamError) {
        guard !closing else { return }
        diagnostics.audioState = Int(state.rawValue); diagnostics.audioError = Int(error.rawValue)
        saveDiagnostics()
        guard state == .failed else { return }
        // startAudioCapture can succeed synchronously and fail later in this
        // callback. Leaving the model in listening would hide a dead microphone.
        microphoneBuffer.setEnabled(false); samplePCM.removeAll(); stopPersonalAudio(); clearAudioLevels()
        _ = engine?.muteAudioCapture(true); _ = engine?.setPlaybackVolume(0)
        diagnostics.microphoneEnabled = false
        failureMessage = error == .deviceNoPermission ? "麦克风权限已失效，请在 iPhone 设置中允许麦克风后重新开始。"
            : "麦克风未能继续采集（错误码 \(error.rawValue)），请检查音频设备后重新开始。"
        diagnostic("rtc_audio_capture_failed")
        finishJoin(APIError.invalidResponse); onFailure?()
    }
    nonisolated func rtcEngine(_ engine: ByteRTCEngine, onConnectionStateChanged state: ByteRTCConnectionState) {
        let code = Int(state.rawValue)
        Task { @MainActor [weak self] in
            guard let self, self.engine === engine, !self.closing else { return }
            self.diagnostics.connectionState = code; self.saveDiagnostics()
            if state == .failed {
                self.clearAudioLevels()
                self.microphoneBuffer.setEnabled(false); self.samplePCM.removeAll()
                self.stopPersonalAudio()
                _ = engine.muteAudioCapture(true); _ = engine.setPlaybackVolume(0)
                self.diagnostics.microphoneEnabled = false
                self.diagnostic("rtc_connection_failed")
                self.finishJoin(APIError.invalidResponse)
                self.onFailure?()
            } else if self.connected, [.disconnected, .reconnecting, .lost].contains(state) {
                // These SDK states still retry automatically. Suspend immediately,
                // then let the model bound recovery and re-check the server lease.
                self.recovering = true; self.recoveryConnectionAvailable = false
                self.clearAudioLevels()
                self.microphoneBuffer.setEnabled(false); self.samplePCM.removeAll()
                self.stopPersonalAudio()
                _ = engine.muteAudioCapture(true); _ = engine.setPlaybackVolume(0)
                self.diagnostics.microphoneEnabled = false
                self.diagnostic("rtc_recovering")
                self.onConnectionChanged?(.recovering)
            } else if self.recovering, [.connected, .reconnected].contains(state) {
                self.recoveryConnectionAvailable = true
                self.diagnostic("rtc_reconnected_pending_lease")
                self.onConnectionChanged?(.connected)
            }
        }
    }
    nonisolated func onTokenWillExpire(_ rtcRoom: ByteRTCRoom) {
        Task { @MainActor [weak self] in
            guard let self, self.room === rtcRoom, !self.closing else { return }
            self.onFailure?()
        }
    }
}

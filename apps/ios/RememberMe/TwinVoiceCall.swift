import Foundation
import SwiftUI
import AVFoundation
import LiveKit
import UIKit

@MainActor
struct VoiceRoomActions {
    var connect: (Room, VoiceCallTicket) async throws -> Void
    var microphone: (Room, Bool) async throws -> Void
    var interrupt: (Room, String) async throws -> Void
    var selectSpeaker: (Bool) throws -> Void = { _ in }
    var releaseAudioRoute: () -> Void = { }
    var outputPorts: () -> [AVAudioSession.Port] = { [] }
    static var liveKit: VoiceRoomActions {
        let routing = VoiceCallAudioRouting()
        return VoiceRoomActions(
            connect: { room, ticket in
                routing.prepare()
                try await room.connect(url: ticket.livekit_url ?? "", token: ticket.token,
                                       connectOptions: ConnectOptions(reconnectAttempts: 0))
            },
            microphone: { try await $0.localParticipant.setMicrophone(enabled: $1,
                captureOptions: AudioCaptureOptions(echoCancellation: true, autoGainControl: true, noiseSuppression: true)) },
            interrupt: { room, turn in
                let data = try JSONSerialization.data(withJSONObject: ["type": "interrupt", "turn_id": turn])
                try await room.localParticipant.publish(data: data,
                    options: DataPublishOptions(topic: "remember.twin.voice.v1", reliable: true))
            },
            selectSpeaker: { try routing.selectSpeaker($0) },
            releaseAudioRoute: { routing.release() },
            outputPorts: { AVAudioSession.sharedInstance().currentRoute.outputs.map(\.portType) })
    }
}

/// Keep LiveKit's echo-cancelled audio engine in charge of session activation.
/// Apply the speaker override only after capture has established playAndRecord.
@MainActor
private final class VoiceCallAudioRouting {
    private var previousSpeakerPreference: Bool?

    func prepare() {
        let session = AudioManager.shared.audioSession
        if previousSpeakerPreference == nil { previousSpeakerPreference = session.isSpeakerOutputPreferred }
        session.isSpeakerOutputPreferred = true
    }
    func selectSpeaker(_ enabled: Bool) throws {
        AudioManager.shared.audioSession.isSpeakerOutputPreferred = enabled
        // .speaker selects both the built-in microphone and loudspeaker, even with Bluetooth connected.
        try AVAudioSession.sharedInstance().overrideOutputAudioPort(enabled ? .speaker : .none)
    }
    func release() {
        guard let preference = previousSpeakerPreference else { return }
        try? AVAudioSession.sharedInstance().overrideOutputAudioPort(.none)
        AudioManager.shared.audioSession.isSpeakerOutputPreferred = preference
        previousSpeakerPreference = nil
    }
}

/// Room tokens live only in this session. No recording, profile or token is written to chat history.
@MainActor
final class TwinVoiceCallModel: NSObject, ObservableObject, RoomDelegate {
    private static let unknownResponseNotice = "现有资料还不足以回答这个问题。你可以补充相关经历，或换个问题。"
    enum State: String { case idle, connecting, awaitingSpeech, listening, thinking, speaking, reconnecting, ending, failed }
    @Published private(set) var state: State = .idle {
        didSet {
            if state != .speaking { playbackAudioLevel = nil }
            if ![.awaitingSpeech, .listening, .thinking, .speaking].contains(state) { clearAudioLevels() }
        }
    }
    @Published private(set) var muted = false
    /// Measured amplitude only. Nil means there is no current usable media report.
    @Published private(set) var microphoneAudioLevel: Double?
    @Published private(set) var playbackAudioLevel: Double?
    var displayedAudioLevel: Double? {
        switch state {
        case .speaking: playbackAudioLevel
        case .awaitingSpeech, .listening: muted ? nil : microphoneAudioLevel
        default: nil
        }
    }
    @Published private(set) var capabilities: RealtimeVoiceCapabilities?
    @Published private(set) var profile: RealtimeVoiceProfile?
    @Published private(set) var identifiedSpeakerNames: [String] = []
    @Published private(set) var question = ""
    @Published private(set) var answer: TwinAnswerRecord?
    @Published private(set) var notice: String?
    @Published private(set) var isPreparing = false
    @Published private(set) var isChangingMute = false
    @Published private(set) var audioRoute = "手机扬声器（连接后启用）"
    @Published private(set) var audioRouteSymbol = "speaker.wave.2.fill"
    @Published private(set) var speakerEnabled = true
    var canSelectAudioOutput: Bool { microphoneReady && isActive && state != .ending }
    var isActive: Bool { ![.idle, .failed].contains(state) }
    var activeVoiceMode: String? { ticket.map { $0.voice_mode ?? "personal" } }
    var statusText: String {
        switch state {
        case .idle: "准备语音通话"
        case .connecting: domestic != nil && microphoneReady ? "麦克风已连接，请开始说话…" : "正在连接…"
        case .awaitingSpeech: muted ? "麦克风已静音" : "已接通，请开始说话"
        case .listening: muted ? "麦克风已静音" : "我在听，你可以直接说话"
        case .thinking: "正在查找记忆和回答…"
        case .speaking: "孪生正在回答，可以插话打断"
        case .reconnecting: "连接中断，正在重连…"
        case .ending: "正在结束通话…"
        case .failed: "通话未能继续"
        }
    }
    private let recordPermission: @MainActor () async -> Bool
    private let roomActions: VoiceRoomActions
    private let domesticFactory: @MainActor () -> any DomesticVoiceTransport
    private let agentReadyTimeout: Duration
    private let domesticRetryGrace: Duration
    init(recordPermission: @escaping @MainActor () async -> Bool = { await AVAudioApplication.requestRecordPermission() },
         roomActions: VoiceRoomActions = .liveKit,
         domesticFactory: @escaping @MainActor () -> any DomesticVoiceTransport = { VolcengineVoiceTransport() },
         agentReadyTimeout: Duration = .seconds(25), domesticRetryGrace: Duration = .seconds(8)) {
        self.recordPermission = recordPermission
        self.roomActions = roomActions
        self.domesticFactory = domesticFactory
        self.agentReadyTimeout = agentReadyTimeout
        self.domesticRetryGrace = domesticRetryGrace
        super.init()
    }
    private var domestic: (any DomesticVoiceTransport)?
    private var domesticAgentConnected = false
    private var domesticHeartbeat: Task<Void, Never>?
    private var domesticLease: Task<Void, Never>?
    private var domesticLastLeaseSuccess: ContinuousClock.Instant?
    private var domesticRecovering = false
    private var domesticRecoveryAvailable = false
    private var domesticRecoveryEpoch = UUID()
    private var domesticRecoveryTimeout: Task<Void, Never>?
    private var domesticRecoveryValidation: Task<Void, Never>?
    private var domesticUploads: [UUID: Task<Void, Never>] = [:]
    private var personalAudio: Task<Void, Never>?
    private var personalTurn: String?
    private var personalPlayedTurns = Set<String>()
    private var domesticStage: VolcengineVoiceTransport.Conversation?
    private var room: Room?
    private var ticket: VoiceCallTicket?
    private var generation = UUID()
    private var preparationEpoch = UUID()
    private var profileRefreshID: UUID?
    private var speakerTurn: String?
    private var activeTurn: String?
    private var retiredTurns = Set<String>()
    private var client: APIClient?
    private var pairing: Pairing?
    private var expiryTask: Task<Void, Never>?
    private var agentTimeout: Task<Void, Never>?
    private var audioInterruption: NSObjectProtocol?
    private var audioResetObservation: NSObjectProtocol?
    private var routeObservation: NSObjectProtocol?
    private var lockObservation: NSObjectProtocol?
    private var agentReady = false
    private var microphoneReady = false
    private var audioLevelExpiry: Task<Void, Never>?
    private var audioLevelEpoch = UUID()

    private func clearAudioLevels() {
        audioLevelExpiry?.cancel(); audioLevelExpiry = nil; audioLevelEpoch = UUID()
        microphoneAudioLevel = nil; playbackAudioLevel = nil
    }
    private func receiveAudioLevels(microphone: Double?, playback: Double?) {
        guard microphoneReady, !domesticRecovering,
              [.awaitingSpeech, .listening, .thinking, .speaking].contains(state) else {
            clearAudioLevels(); return
        }
        microphoneAudioLevel = muted ? nil : VoiceAudioMeter.normalized(microphone)
        playbackAudioLevel = state == .speaking ? VoiceAudioMeter.normalized(playback) : nil
        audioLevelExpiry?.cancel()
        let epoch = UUID(); audioLevelEpoch = epoch
        let current = generation
        audioLevelExpiry = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(400))
            guard !Task.isCancelled, let self, self.generation == current, self.audioLevelEpoch == epoch else { return }
            self.clearAudioLevels()
        }
    }

    func configure(_ pairing: Pairing, client: APIClient) {
        guard !isActive else { return }
        if self.pairing.map(RecordingOwner.init) != RecordingOwner(pairing) || self.pairing?.token != pairing.token {
            invalidatePreparation()
            capabilities = nil; profile = nil; answer = nil; question = ""; identifiedSpeakerNames = []
            clearAudioLevels()
        }
        self.pairing = pairing; self.client = client
    }
    private func invalidatePreparation() {
        preparationEpoch = UUID()
        profileRefreshID = nil
        isPreparing = false
    }
    private func acceptsPreparation(_ epoch: UUID, owner: RecordingOwner, token: String) -> Bool {
        !Task.isCancelled && !isActive && preparationEpoch == epoch &&
            pairing.map(RecordingOwner.init) == owner && pairing?.token == token
    }
    func prepare() async {
        guard !Task.isCancelled, !isActive, let pairing, let client, !isPreparing else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        let epoch = preparationEpoch
        isPreparing = true
        defer { if preparationEpoch == epoch { isPreparing = false } }
        do {
            let result = try await client.realtimeCapabilities(subjectID: pairing.subjectID)
            guard acceptsPreparation(epoch, owner: owner, token: token) else { return }
            capabilities = result; profile = result.profile
            if state != .failed {
                notice = result.available ? nil : "此服务尚未启用实时声音通话，文字孪生仍可使用。"
            }
        } catch {
            guard acceptsPreparation(epoch, owner: owner, token: token),
                  !(error is CancellationError), (error as? URLError)?.code != .cancelled else { return }
            capabilities = nil; profile = nil
            // Keep the actual hangup reason visible when an automatic refresh also fails.
            if state != .failed || notice == nil { notice = Self.preparationFailureNotice(error) }
        }
    }
    private static func preparationFailureNotice(_ error: Error) -> String {
        if let error = error as? URLError {
            switch error.code {
            case .timedOut: return "检查通话服务超时，请稍后重试。"
            case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed:
                return "无法连接通话服务，请检查网络后重试。"
            default: return "检查通话服务失败，请稍后重试。"
            }
        }
        if let error = error as? APIError {
            switch error {
            case .server(401, _): return "登录已失效，请重新登录后再开始通话。"
            case .server(403, _): return "当前账号无法访问通话服务，请检查账号和空间权限。"
            case .server(404, _): return "当前服务未提供此通话接口，请检查服务版本或空间权限。"
            case .server(let status, _) where status >= 500: return "通话服务暂时异常（\(status)），请稍后重试。"
            case .invalidCertificate: return "通话服务证书验证失败，请检查服务连接设置。"
            case .invalidURL: return "通话服务地址无效，请检查服务连接设置。"
            default: break
            }
        }
        return "检查通话服务失败，请稍后重试。"
    }
    func refreshProfile() async {
        guard !Task.isCancelled, !isActive, let pairing, let client, profileRefreshID == nil else { return }
        let refreshID = UUID(); profileRefreshID = refreshID
        defer { if profileRefreshID == refreshID { profileRefreshID = nil } }
        let scope = RecordingOwner(pairing), token = pairing.token
        let epoch = preparationEpoch
        do {
            let result = try await client.realtimeProfile(subjectID: pairing.subjectID, transport: capabilities?.transport)
            guard acceptsPreparation(epoch, owner: scope, token: token) else { return }
            profile = result
            capabilities?.profile = result
            if notice?.hasPrefix("声音状态未能更新：") == true { notice = nil }
        }
        catch {
            guard acceptsPreparation(epoch, owner: scope, token: token),
                  !(error is CancellationError), (error as? URLError)?.code != .cancelled else { return }
            if state != .failed || notice == nil { notice = "声音状态未能更新：\(error.localizedDescription)" }
        }
    }
    func enrolled(_ profile: RealtimeVoiceProfile) { self.profile = profile }
    func resetProfile() { profile = nil }
    func resetConnection() {
        guard !isActive else { return }
        invalidatePreparation()
        clearAudioLevels()
        capabilities = nil; profile = nil; answer = nil; question = ""; identifiedSpeakerNames = []
        pairing = nil; client = nil; notice = nil
    }

    static func validate(_ ticket: VoiceCallTicket) throws {
        let validTransport: Bool
        if ticket.transport == "volcengine" {
            validTransport = ticket.app_id?.count == 24 && ticket.bot_identity == "twin_" + ticket.call_id
                && ticket.livekit_url == nil && ticket.token.hasPrefix("001" + (ticket.app_id ?? ""))
        } else if ticket.transport == nil || ticket.transport == "livekit" {
            let url = URLComponents(string: ticket.livekit_url ?? "")
            validTransport = url?.scheme == "wss" && url?.host != nil && url?.user == nil
                && url?.password == nil && url?.query == nil && url?.fragment == nil
        } else { validTransport = false }
        guard validTransport, ticket.call_id.hasPrefix("vc_"), ticket.room == ticket.call_id,
              ticket.participant_identity == "user_" + ticket.call_id,
              !ticket.token.isEmpty, let expiry = date(ticket.expires_at), expiry > Date(),
              expiry.timeIntervalSinceNow <= 31 * 60 else { throw APIError.invalidResponse }
    }
    private static func date(_ text: String) -> Date? {
        let fractional = ISO8601DateFormatter(); fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: text) ?? ISO8601DateFormatter().date(from: text)
    }
    func start(cloudConsent: String, voiceConsent: String, voiceMode: String = "personal", recordingConsent: String? = nil, speakerConsent: String? = nil, enrollOwnerVoice: Bool = false) async {
        guard !Task.isCancelled, !isActive, let pairing, let client, let capabilities, capabilities.available,
              voiceMode == "default" && capabilities.default_voice_available == true ||
              voiceMode == "personal" && profile?.ready == true && profile?.voice_consent_id == voiceConsent else { return }
        invalidatePreparation()
        notice = nil; state = .connecting; muted = false; isChangingMute = false; answer = nil; question = ""
        clearAudioLevels()
        retiredTurns = []; activeTurn = nil; speakerTurn = nil; identifiedSpeakerNames = []; generation = UUID()
        agentReady = false; microphoneReady = false; domesticAgentConnected = false
        domesticRecovering = false; domesticRecoveryAvailable = false
        personalPlayedTurns = []
        speakerEnabled = true; audioRoute = "手机扬声器（连接后启用）"; audioRouteSymbol = "speaker.wave.2.fill"
        let current = generation
        let permitted = await recordPermission()
        guard current == generation else { return }
        guard !Task.isCancelled else { await end(); return }
        guard permitted else { state = .failed; notice = "请在 iPhone 设置中允许麦克风权限。"; return }
        do {
            let fresh = try await client.realtimeCapabilities(subjectID: pairing.subjectID)
            guard current == generation else { return }
            try Task.checkCancellation()
            self.capabilities = fresh; self.profile = fresh.profile
            let voiceReady = voiceMode == "default" ? fresh.default_voice_available == true : fresh.profile.ready && fresh.profile.voice_consent_id == voiceConsent
            guard fresh.available, voiceReady else {
                await end(message: "声音或服务尚未就绪，请刷新状态后重新开始。"); return
            }
            guard fresh.policy == capabilities.policy else {
                await end(message: "语音用途已变化，请阅读并重新确认后开始。"); return
            }
            observeAudio(current: current)
            let result = try await client.startVoiceCall(subjectID: pairing.subjectID, cloudConsent: cloudConsent,
                                                        voiceConsent: voiceConsent, policy: capabilities.policy, voiceMode: voiceMode, recordingConsent: recordingConsent, speakerConsent: speakerConsent, enrollOwnerVoice: enrollOwnerVoice, transport: capabilities.transport)
            guard current == generation, !Task.isCancelled else {
                try? await client.endVoiceCall(subjectID: pairing.subjectID, callID: result.call_id, transport: result.transport)
                if current == generation { await end() }
                return
            }
            ticket = result
            try Self.validate(result)
            guard (result.voice_mode ?? "personal") == voiceMode else { throw APIError.invalidResponse }
            guard result.transport == fresh.transport else { throw APIError.invalidResponse }
            if result.transport == "volcengine" {
                let transport = domesticFactory()
                domestic = transport
                transport.onAgentConnected = { [weak self] in
                    guard let self, self.generation == current else { return }
                    self.domesticAgentConnected = true
                    self.updateDomesticConnectionState()
                }
                transport.onConversation = { [weak self] event in
                    guard let self, self.generation == current else { return }
                    self.receiveDomesticStage(event)
                }
                transport.onConnectionChanged = { [weak self] state in
                    guard let self, self.generation == current else { return }
                    self.domesticConnectionChanged(state, current: current)
                }
                transport.onAudioLevels = { [weak self] microphone, playback in
                    guard let self, self.generation == current, self.domestic != nil else { return }
                    self.receiveAudioLevels(microphone: microphone, playback: playback)
                }
                transport.onFailure = { [weak self, weak transport] in
                    let message = transport?.failureMessage ?? "国内语音连接已中断，请重新开始。"
                    Task { @MainActor in
                        guard let self, self.generation == current else { return }
                        await self.end(message: message)
                    }
                }
                transport.onSpeechBegan = { [weak self] in
                    Task { @MainActor in
                        guard let self, self.generation == current else { return }
                        await self.userBeganSpeaking()
                    }
                }
                if result.capture_enabled == true {
                    transport.onCaptured = { [weak self] turn, data in
                        self?.uploadDomesticSegment(data, identifier: turn, sample: false, current: current)
                    }
                    transport.onSample = { [weak self] identifier, data in
                        self?.uploadDomesticSegment(data, identifier: identifier, sample: true, current: current)
                    }
                }
                startDomesticHeartbeat(current: current, client: client, pairing: pairing, ticket: result)
                try await transport.connect(result)
                guard current == generation, !Task.isCancelled else {
                    await transport.disconnect()
                    if current == generation { await end() }
                    return
                }
                try await client.activateDomesticVoice(subjectID: pairing.subjectID, callID: result.call_id)
                guard current == generation, !Task.isCancelled else {
                    await transport.disconnect()
                    if current == generation { await end() }
                    return
                }
                try transport.microphone(true)
                microphoneReady = true
                try transport.selectSpeaker(true)
                updateDomesticConnectionState()
                if domesticRecovering, domesticRecoveryAvailable { validateDomesticRecovery(current: current) }
            } else {
                let connected = Room(delegate: self)
                room = connected
                try await roomActions.connect(connected, result)
                guard current == generation, !Task.isCancelled else {
                    await connected.disconnect()
                    if current == generation { await end() }
                    return
                }
                try await roomActions.microphone(connected, true)
                guard current == generation, !Task.isCancelled else {
                    await connected.disconnect()
                    if current == generation { await end() }
                    return
                }
                microphoneReady = true
                try roomActions.selectSpeaker(true)
            }
            updateAudioRoute()
            if agentReady, state == .connecting { state = .listening }
            // Wait for the agent's ready event; a transport connection alone is insufficient.
            expiryTask = Task { [weak self] in
                let seconds = max(0, Self.date(result.expires_at)!.timeIntervalSinceNow)
                try? await Task.sleep(for: .seconds(seconds))
                guard !Task.isCancelled, let self, self.generation == current else { return }
                await self.end(message: "本次通话已到期，可以重新开始。")
            }
            agentTimeout = Task { [weak self] in
                guard let self else { return }
                try? await Task.sleep(for: self.agentReadyTimeout)
                guard !Task.isCancelled, self.generation == current, self.state == .connecting else { return }
                await self.end(message: "语音助手未能接入，请重新开始通话。")
            }
        } catch {
            guard current == generation else { return }
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled {
                await end(); return
            }
            await end(message: "通话未能连接：\(error.localizedDescription)")
        }
    }
    func toggleMute() async {
        guard [.awaitingSpeech, .listening, .thinking, .speaking].contains(state), !isChangingMute else { return }
        if let domestic {
            do { try domestic.microphone(muted); muted.toggle(); microphoneAudioLevel = nil }
            catch { await end(message: "麦克风状态无法更新，通话已结束。") }
            return
        }
        guard let room else { return }
        let current = generation, target = !muted
        isChangingMute = true
        defer { if generation == current { isChangingMute = false } }
        do {
            try await roomActions.microphone(room, !target)
            guard generation == current, self.room === room else { return }
            muted = target
            microphoneAudioLevel = nil
        } catch {
            guard generation == current, self.room === room else { return }
            await end(message: "麦克风状态无法更新，通话已结束。")
        }
    }
    func selectSpeaker(_ enabled: Bool) async {
        guard canSelectAudioOutput else { return }
        do {
            if let domestic { try domestic.selectSpeaker(enabled) }
            else { try roomActions.selectSpeaker(enabled) }
            speakerEnabled = enabled
            updateAudioRoute()
        } catch {
            await end(message: "音频输出切换失败，通话已结束。请检查手机音频后重新开始。")
        }
    }
    func interrupt() async {
        guard [.thinking, .speaking].contains(state), let interruptedTurn = activeTurn else { return }
        if domestic != nil, let ticket, let client, let pairing {
            let current = generation
            stopPersonalAudio()
            retiredTurns.insert(interruptedTurn); activeTurn = nil; identifiedSpeakerNames = []
            state = .listening; remoteVolume(0)
            do { try await client.interruptDomesticVoice(subjectID: pairing.subjectID, callID: ticket.call_id, turnID: interruptedTurn) }
            catch {
                guard self.generation == current, self.ticket?.call_id == ticket.call_id else { return }
                await end(message: "打断请求未能送达，通话已结束。")
            }
            return
        }
        guard let room else { return }
        let current = generation
        retiredTurns.insert(interruptedTurn)
        activeTurn = nil; speakerTurn = nil; identifiedSpeakerNames = []; state = .listening; remoteVolume(0)
        do { try await roomActions.interrupt(room, interruptedTurn) }
        catch {
            guard generation == current, self.room === room else { return }
            await end(message: "打断请求未能送达，通话已结束。")
        }
    }
    func endCurrentCallOnBackground() {
        endCurrentCall(message: "已切到后台，语音通话已结束。返回后可重新开始。")
    }
    func endCurrentCall(message: String? = nil, resetConnectionAfter: Bool = false) {
        guard isActive else {
            if resetConnectionAfter { resetConnection() }
            return
        }
        let current = generation
        Task { @MainActor [weak self] in
            guard let self, self.generation == current, self.isActive else { return }
            await self.end(message: message, resetConnectionAfter: resetConnectionAfter)
        }
    }
    func end(message: String? = nil, resetConnectionAfter: Bool = false) async {
        guard state != .ending else { return }
        invalidatePreparation()
        generation = UUID(); expiryTask?.cancel(); expiryTask = nil; agentTimeout?.cancel(); agentTimeout = nil
        state = .ending; isChangingMute = false; speakerTurn = nil; identifiedSpeakerNames = []
        let oldRoom = room, oldTicket = ticket, oldPairing = pairing, oldClient = client
        let oldDomestic = domestic
        oldDomestic?.diagnostic(message == nil ? "user_ended" : "client_ended_with_notice")
        stopPersonalAudio()
        domesticLease?.cancel(); domesticLease = nil
        domesticLastLeaseSuccess = nil
        domesticRecoveryTimeout?.cancel(); domesticRecoveryTimeout = nil
        domesticRecoveryValidation?.cancel(); domesticRecoveryValidation = nil
        domesticRecoveryEpoch = UUID(); domesticRecovering = false; domesticRecoveryAvailable = false
        for task in domesticUploads.values { task.cancel() }; domesticUploads.removeAll()
        domestic = nil; domesticHeartbeat?.cancel(); domesticHeartbeat = nil; domesticStage = nil
        room = nil; ticket = nil
        for observer in [audioInterruption, audioResetObservation, routeObservation, lockObservation].compactMap({ $0 }) {
            NotificationCenter.default.removeObserver(observer)
        }
        audioInterruption = nil; audioResetObservation = nil; routeObservation = nil; lockObservation = nil
        agentReady = false; microphoneReady = false
        if let oldRoom {
            for participant in oldRoom.remoteParticipants.values {
                for publication in participant.trackPublications.values {
                    (publication.track as? RemoteAudioTrack)?.volume = 0
                }
            }
        }
        // Microphone and playback stop locally before waiting for Backend deletion.
        await oldDomestic?.disconnect()
        await oldRoom?.disconnect()
        roomActions.releaseAudioRoute()
        state = message == nil ? .idle : .failed; muted = false; activeTurn = nil; notice = message
        if resetConnectionAfter { resetConnection() }
        if let oldTicket, let oldPairing, let oldClient {
            try? await oldClient.endVoiceCall(subjectID: oldPairing.subjectID, callID: oldTicket.call_id, transport: oldTicket.transport)
        }
    }
    func receive(_ event: VoiceCallEvent) {
        guard isActive, state != .ending else { return }
        if event.type == "ended" {
            let current = generation
            Task {
                guard generation == current else { return }
                await end(message: event.message ?? "语音通话已结束，请重新开始。")
            }; return
        }
        guard !domesticRecovering else { return }
        if event.type == "state", event.turn_id == nil, event.state == "listening", state == .connecting {
            agentReady = true
            if microphoneReady { state = .listening; agentTimeout?.cancel() }
            return
        }
        guard agentReady, microphoneReady else { return }
        if let turn = event.turn_id, retiredTurns.contains(turn) { return }
        if event.type == "speaker" {
            guard let turn = event.turn_id, turn == activeTurn, turn == speakerTurn else { return }
            identifiedSpeakerNames = Array(NSOrderedSet(array: (event.speaker_names ?? [])
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty })) as? [String] ?? []
            if let message = event.message { notice = message }
            return
        }
        if event.type == "question", let turn = event.turn_id {
            if let old = activeTurn { retiredTurns.insert(old) }
            if notice == Self.unknownResponseNotice || notice == "网络已恢复，可以继续说话。" { notice = nil }
            activeTurn = turn; speakerTurn = turn; identifiedSpeakerNames = []; question = event.text ?? ""; answer = nil; state = .thinking
        } else if event.type == "answer", event.turn_id == activeTurn, let answer = event.answer {
            self.answer = answer
        } else if event.type == "state", event.turn_id != nil, event.turn_id == activeTurn {
            if let next = State(rawValue: event.state ?? ""), [.listening, .thinking, .speaking].contains(next) {
                state = next; agentTimeout?.cancel()
                if next == .speaking { remoteVolume(1) }
            }
        } else if event.type == "error", event.turn_id == activeTurn {
            notice = event.message; state = .listening
        }
    }
    private func receiveDomesticStage(_ event: VolcengineVoiceTransport.Conversation) {
        guard isActive, state != .ending, !domesticRecovering else { return }
        domesticStage = event
        let turn = "ve_" + String(event.RoundID)
        if [1, 2, 3, 5].contains(event.Stage.Code), !agentReady {
            agentReady = true
            if microphoneReady { state = .listening; agentTimeout?.cancel() }
            if event.Stage.Code == 1 { return }
        }
        guard agentReady, microphoneReady, !retiredTurns.contains(turn) else { return }
        if [2, 3].contains(event.Stage.Code), activeTurn != turn {
            stopPersonalAudio()
            receive(VoiceCallEvent(type: "question", turn_id: turn, text: "", state: nil, answer: nil, message: nil))
        }
        guard activeTurn == turn else { return }
        if ticket?.voice_mode == "personal", personalPlayedTurns.contains(turn), event.Stage.Code != 4 { return }
        switch event.Stage.Code {
        case 1, 5: if personalTurn == nil { state = .listening }
        case 2: state = .thinking
        case 3: state = .speaking; remoteVolume(1)
        case 4: stopPersonalAudio(); state = .listening; remoteVolume(0)
        default: break
        }
    }
    private func updateDomesticConnectionState() {
        guard domestic != nil, !domesticRecovering, microphoneReady, state == .connecting else { return }
        if agentReady { state = .listening; agentTimeout?.cancel() }
        else if domesticAgentConnected { state = .awaitingSpeech; agentTimeout?.cancel() }
    }
    private func domesticConnectionChanged(_ connection: DomesticVoiceConnectionState, current: UUID) {
        guard generation == current, domestic != nil, isActive, state != .ending else { return }
        switch connection {
        case .recovering:
            let firstInterruption = !domesticRecovering
            domesticRecovering = true; domesticRecoveryAvailable = false; domesticRecoveryEpoch = UUID()
            domesticRecoveryValidation?.cancel(); domesticRecoveryValidation = nil
            stopPersonalAudio(); remoteVolume(0)
            // An interrupted reply cannot resume from the middle or be replayed by
            // a late status result after the connection recovers.
            if let turn = activeTurn {
                retiredTurns.insert(turn); activeTurn = nil; speakerTurn = nil
                if let client, let pairing, let ticket {
                    Task { try? await client.interruptDomesticVoice(subjectID: pairing.subjectID, callID: ticket.call_id, turnID: turn) }
                }
            }
            domesticStage = nil; identifiedSpeakerNames = []
            state = .reconnecting; notice = "连接波动，正在恢复语音…"
            agentTimeout?.cancel(); agentTimeout = nil
            if firstInterruption {
                domesticRecoveryTimeout = Task { [weak self] in
                    guard let self else { return }
                    try? await Task.sleep(for: self.domesticRetryGrace)
                    guard !Task.isCancelled, self.generation == current, self.domesticRecovering else { return }
                    self.domestic?.diagnostic("rtc_recovery_timeout")
                    await self.end(message: "语音连接持续中断，请重新开始。")
                }
            }
        case .connected:
            guard domesticRecovering else { return }
            domesticRecoveryAvailable = true
            if microphoneReady { validateDomesticRecovery(current: current) }
        }
    }
    private func validateDomesticRecovery(current: UUID) {
        guard domesticRecoveryValidation == nil, domesticRecovering, domesticRecoveryAvailable,
              let client, let pairing, let ticket else { return }
        let epoch = domesticRecoveryEpoch
        domesticRecoveryValidation = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    try await client.domesticVoiceLease(subjectID: pairing.subjectID, callID: ticket.call_id)
                    guard let self, !Task.isCancelled, self.generation == current,
                          self.domesticRecoveryEpoch == epoch, self.domesticRecovering,
                          self.domesticRecoveryAvailable, let domestic = self.domestic else { return }
                    try domestic.resumeAfterReconnect(microphone: !self.muted)
                    self.domesticLastLeaseSuccess = .now
                    self.domesticRecovering = false; self.domesticRecoveryAvailable = false
                    self.domesticRecoveryTimeout?.cancel(); self.domesticRecoveryTimeout = nil
                    self.domesticRecoveryValidation = nil
                    self.state = self.agentReady ? .listening : .awaitingSpeech
                    self.notice = "网络已恢复，可以继续说话。"
                    domestic.diagnostic("rtc_recovery_lease_confirmed")
                    return
                } catch {
                    guard let self, !Task.isCancelled, self.generation == current,
                          self.domesticRecoveryEpoch == epoch, self.domesticRecovering else { return }
                    if Self.isTerminalDomesticError(error) {
                        await self.end(message: "语音通话已结束或授权已变化，请重新开始。")
                        return
                    }
                    try? await Task.sleep(for: .milliseconds(500))
                }
            }
        }
    }
    private func startDomesticHeartbeat(current: UUID, client: APIClient, pairing: Pairing, ticket: VoiceCallTicket) {
        domesticLastLeaseSuccess = .now
        domesticLease = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    try await client.domesticVoiceLease(subjectID: pairing.subjectID, callID: ticket.call_id)
                    guard let self, self.generation == current, !Task.isCancelled else { return }
                    self.domesticLastLeaseSuccess = .now
                    if self.notice == "连接波动，正在重试…" { self.notice = nil }
                    try await Task.sleep(for: .seconds(2))
                } catch {
                    guard let self, self.generation == current, !Task.isCancelled else { return }
                    self.domestic?.diagnostic(Self.isTerminalDomesticError(error) ? "lease_rejected" : "lease_transient_error")
                    let elapsed = self.domesticLastLeaseSuccess?.duration(to: .now) ?? self.domesticRetryGrace
                    if Self.isTerminalDomesticError(error) || elapsed >= self.domesticRetryGrace {
                        await self.end(message: "通话连接已失效或网络持续中断，请重新开始。")
                        return
                    }
                    self.notice = "连接波动，正在重试…"
                    try? await Task.sleep(for: .milliseconds(500))
                }
            }
        }
        domesticHeartbeat = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    let status = try await client.domesticVoiceHeartbeat(subjectID: pairing.subjectID, callID: ticket.call_id)
                    guard !Task.isCancelled, let self, self.generation == current else { return }
                    guard status.call_id == ticket.call_id else { throw APIError.invalidResponse }
                    // Status authenticates and renews the same call lease on the
                    // backend, even when a separate lease request is delayed.
                    self.domesticLastLeaseSuccess = .now
                    if self.domesticRecovering {
                        try await Task.sleep(for: .milliseconds(750))
                        continue
                    }
                    if status.turn_id != nil, !status.question.isEmpty, self.microphoneReady, !self.agentReady {
                        self.agentReady = true; self.agentTimeout?.cancel()
                    }
                    if let retired = status.retired_turn_id, self.activeTurn == retired {
                        self.retiredTurns.insert(retired); self.activeTurn = nil
                        self.stopPersonalAudio(); self.identifiedSpeakerNames = []; self.state = .listening
                        self.notice = "相关记忆已更新，可以继续说话。"
                    }
                    if let turn = status.turn_id, !self.retiredTurns.contains(turn), self.agentReady, self.microphoneReady {
                        let round = Int(turn.dropFirst(3)) ?? -1
                        if round >= (self.domesticStage?.RoundID ?? -1) {
                            self.domestic?.captureTurn(round)
                            if self.activeTurn != turn {
                                self.receive(VoiceCallEvent(type: "question", turn_id: turn, text: status.question, state: nil, answer: nil, message: nil))
                            } else { self.question = status.question }
                            if let answer = status.answer { self.answer = answer }
                            if let event = self.domesticStage { self.receiveDomesticStage(event) }
                            if self.activeTurn == turn {
                                self.identifiedSpeakerNames = status.speaker_names ?? []
                                if let message = status.speaker_message { self.notice = message }
                                if status.answer?.response_type == "UNKNOWN" {
                                    self.notice = Self.unknownResponseNotice
                                    if self.personalTurn == nil, self.state == .thinking { self.state = .listening }
                                }
                                self.startPersonalAudio(status, current: current)
                            }
                        }
                    }
                    if status.failed, let turn = status.turn_id, self.activeTurn == turn,
                       !self.retiredTurns.contains(turn) {
                        self.notice = "这一轮未能生成回答，请再说一次。"; self.state = .listening
                    }
                    try await Task.sleep(for: .milliseconds(750))
                } catch {
                    guard !Task.isCancelled, let self, self.generation == current else { return }
                    self.domestic?.diagnostic(Self.isTerminalDomesticError(error) ? "status_rejected" : "status_transient_error")
                    if Self.isTerminalDomesticError(error) {
                        await self.end(message: "语音通话已结束或授权已变化，请重新开始。")
                        return
                    }
                    // Answer publication and speaker workers cannot stop the lease loop.
                    try? await Task.sleep(for: .milliseconds(750))
                }
            }
        }
    }
    private static func isTerminalDomesticError(_ error: Error) -> Bool {
        if case APIError.server(let code, _) = error { return [401, 403, 404, 410, 422].contains(code) }
        if case APIError.invalidResponse = error { return true }
        if case APIError.invalidCertificate = error { return true }
        return false
    }
    private func uploadDomesticSegment(_ data: Data, identifier: String, sample: Bool, current: UUID) {
        guard generation == current, let ticket, ticket.capture_enabled == true, let pairing, let client,
              domesticUploads.count < 4 else { return }
        let id = UUID()
        domesticUploads[id] = Task { [weak self] in
            defer { self?.domesticUploads[id] = nil }
            do {
                try await client.uploadDomesticVoice(subjectID: pairing.subjectID, callID: ticket.call_id,
                    segmentID: identifier, sample: sample, audio: data)
            } catch {
                guard let self, !Task.isCancelled, self.generation == current else { return }
                self.domestic?.diagnostic("capture_upload_failed")
                self.notice = "这一段声音未能整理，通话可以继续。"
            }
        }
    }
    private func stopPersonalAudio() {
        personalAudio?.cancel(); personalAudio = nil; personalTurn = nil
        playbackAudioLevel = nil
        domestic?.stopPersonalAudio()
    }
    private func startPersonalAudio(_ status: DomesticVoiceStatus, current: UUID) {
        guard !domesticRecovering, ticket?.voice_mode == "personal", let turn = status.turn_id, activeTurn == turn,
              let answer = status.answer, !answer.stale,
              !personalPlayedTurns.contains(turn), let ticket, let pairing, let client, let domestic else { return }
        stopPersonalAudio(); personalPlayedTurns.insert(turn); personalTurn = turn; state = .thinking
        personalAudio = Task { [weak self] in
            do {
                let bytes = try await client.domesticVoiceAudio(subjectID: pairing.subjectID, callID: ticket.call_id,
                    turnID: turn, answerID: answer.id)
                guard let self, self.generation == current, self.activeTurn == turn, !Task.isCancelled else { return }
                self.state = .speaking
                try await domestic.playPersonalAudio(bytes)
                guard self.generation == current, self.personalTurn == turn, !Task.isCancelled else { return }
                self.personalTurn = nil; self.state = .listening
            } catch {
                guard let self, self.generation == current, self.personalTurn == turn, !Task.isCancelled else { return }
                self.personalTurn = nil; self.state = .listening
                domestic.diagnostic("personal_audio_failed")
                self.notice = "这一轮本人声音未能播放，回答文字仍可查看。"
            }
        }
    }
    private func observeAudio(current: UUID) {
        audioResetObservation = NotificationCenter.default.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification,
            object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    guard let self, self.generation == current, self.isActive else { return }
                    await self.end(message: "系统音频服务已重置，语音通话已结束。请重新开始。")
                }
            }
        audioInterruption = NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification,
            object: nil, queue: .main) { [weak self] notification in
                let began = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt == AVAudioSession.InterruptionType.began.rawValue
                guard began else { return }
                Task { @MainActor in
                    guard let self, self.generation == current else { return }
                    await self.end(message: "语音通话被系统中断，请重新开始。")
                }
            }
        routeObservation = NotificationCenter.default.addObserver(forName: AVAudioSession.routeChangeNotification,
            object: nil, queue: .main) { [weak self] notification in
                let rawReason = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
                let reason = rawReason.flatMap(AVAudioSession.RouteChangeReason.init(rawValue:)) ?? .unknown
                let previousRoute = notification.userInfo?[AVAudioSessionRouteChangePreviousRouteKey] as? AVAudioSessionRouteDescription
                let previousOutputs = previousRoute?.outputs.map(\.portType) ?? []
                Task { @MainActor in
                    guard let self, self.generation == current else { return }
                    await self.audioRouteChanged(reason: reason, previousOutputs: previousOutputs)
                }
            }
        lockObservation = NotificationCenter.default.addObserver(forName: UIApplication.protectedDataWillBecomeUnavailableNotification,
            object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    guard let self, self.generation == current else { return }
                    await self.end(message: "手机已锁定，语音通话已结束。解锁后可重新开始。")
                }
            }
    }
    private func updateAudioRoute() {
        let ports = domestic == nil ? roomActions.outputPorts() : AVAudioSession.sharedInstance().currentRoute.outputs.map(\.portType)
        audioRoute = ports.map { port in
            switch port {
            case .builtInSpeaker: "手机扬声器"
            case .builtInReceiver: "手机听筒"
            case .bluetoothHFP, .bluetoothA2DP, .bluetoothLE: "蓝牙耳机"
            case .headphones, .headsetMic, .usbAudio: "有线耳机或音频设备"
            default: "系统音频设备"
            }
        }.joined(separator: "、")
        if audioRoute.isEmpty { audioRoute = "系统音频路线" }
        audioRouteSymbol = ports.contains(.builtInSpeaker) ? "speaker.wave.2.fill"
            : ports.contains(.builtInReceiver) ? "iphone" : "headphones"
    }
    func audioRouteChanged(reason: AVAudioSession.RouteChangeReason, previousOutputs: [AVAudioSession.Port] = []) async {
        guard isActive, state != .ending else { return }
        if speakerEnabled {
            // A device or category change can clear iOS's temporary speaker override.
            // Do not loop on the notification caused by our own override.
            if microphoneReady, reason != .override, !(domestic == nil ? roomActions.outputPorts() : AVAudioSession.sharedInstance().currentRoute.outputs.map(\.portType)).contains(.builtInSpeaker) {
                await selectSpeaker(true)
            }
        } else if reason == .oldDeviceUnavailable,
                  previousOutputs.contains(where: { $0 != .builtInSpeaker && $0 != .builtInReceiver }) {
            // Preserve privacy when the user explicitly chose a headset/receiver route.
            await end(message: "耳机或音频设备已断开，通话已结束。可重新开始并使用手机扬声器。")
            return
        }
        updateAudioRoute()
    }
    func userBeganSpeaking() async {
        guard isActive, !muted else { return }
        speakerTurn = nil; identifiedSpeakerNames = []
        await interrupt()
    }
    #if DEBUG
    func showIsolatedEnrollmentPreview() {
        guard ProcessInfo.processInfo.arguments.contains("--uitest-voice-enrollment") else { return }
        let ready = ProcessInfo.processInfo.arguments.contains("--uitest-voice-ready")
        profile = RealtimeVoiceProfile(ready: ready, profile_id: ready ? "fixture-profile" : nil, status: ready ? "ready" : "missing", model_version: nil, voice_consent_id: ready ? "fixture-only" : nil)
        capabilities = RealtimeVoiceCapabilities(available: true, default_voice_available: true, policy: "fixture-only", notice: "测试预览，无音频传输", profile: profile!, dialogue_capture_available: true, natural_voice_preparation: true)
    }
    func showIsolatedUITestPreview() {
        guard ProcessInfo.processInfo.arguments.contains("--uitest-voice-call") else { return }
        state = .listening; audioRoute = "手机扬声器（测试）"; audioRouteSymbol = "speaker.wave.2.fill"
        notice = "测试预览，无音频传输"
        if ProcessInfo.processInfo.arguments.contains("--uitest-identified-speaker") {
            identifiedSpeakerNames = ["小王"]
        }
    }
    #endif
    private func remoteVolume(_ volume: Double) {
        if volume == 0 { playbackAudioLevel = nil }
        domestic?.volume(volume)
        guard let room else { return }
        for participant in room.remoteParticipants.values {
            for publication in participant.trackPublications.values {
                (publication.track as? RemoteAudioTrack)?.volume = volume
            }
        }
    }
    nonisolated func room(_ room: Room, didUpdateSpeakingParticipants participants: [Participant]) {
        let localSpeaking = participants.contains { $0.identity == room.localParticipant.identity }
        let microphone = Double(room.localParticipant.audioLevel)
        let agentLevels = room.remoteParticipants.values.filter { $0.kind == .agent }
            .map { ($0.identity?.stringValue, Double($0.audioLevel)) }
        Task { @MainActor [weak self] in
            guard let self, self.room === room else { return }
            let playback = agentLevels.filter { self.ticket?.bot_identity == nil || $0.0 == self.ticket?.bot_identity }
                .map(\.1).max()
            self.receiveAudioLevels(microphone: microphone, playback: playback)
            if localSpeaking, [.listening, .thinking, .speaking].contains(self.state) {
                await self.userBeganSpeaking()
            }
        }
    }
    nonisolated func room(_ room: Room, participant: RemoteParticipant?, didReceiveData data: Data,
                          forTopic topic: String, encryptionType: EncryptionType) {
        guard topic == "remember.twin.voice.v1", participant?.kind == .agent,
              data.count <= 64 * 1024, let event = try? JSONDecoder().decode(VoiceCallEvent.self, from: data) else { return }
        Task { @MainActor [weak self] in
            guard let self, self.room === room else { return }; self.receive(event)
        }
    }
    nonisolated func room(_ room: Room, didDisconnectWithError error: LiveKitError?) {
        Task { @MainActor [weak self] in
            guard let self, self.room === room else { return }
            await self.end(message: "实时连接已断开，可以重新开始。")
        }
    }
    nonisolated func roomIsReconnecting(_ room: Room) {
        Task { @MainActor [weak self] in
            guard let self, self.room === room else { return }
            await self.end(message: "实时连接已中断，通话已结束。请检查网络后重新开始。")
        }
    }
    nonisolated func roomDidReconnect(_ room: Room) {
        Task { @MainActor [weak self] in
            guard let self, self.room === room else { return }
            await self.end(message: "连接已变化，请重新开始语音通话。")
        }
    }
}

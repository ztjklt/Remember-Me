import SwiftUI

@main
struct RememberMeApp: App {
    @StateObject private var model = makeModel()
    @Environment(\.scenePhase) private var scenePhase

    private static func makeModel() -> AppModel {
        #if DEBUG
        if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "--uitest-review-pairing"),
           ProcessInfo.processInfo.arguments.count > index + 1,
           let data = Data(base64Encoded: ProcessInfo.processInfo.arguments[index + 1]),
           let pairing = try? JSONDecoder().decode(Pairing.self, from: data),
           URL(string: pairing.baseURL)?.host == "127.0.0.1" {
            let suite = "remember-ui-review-" + UUID().uuidString
            return AppModel(recordingStore: LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(suite)),
                            defaults: UserDefaults(suiteName: suite)!, pairing: pairing)
        }
        if ProcessInfo.processInfo.arguments.contains("--uitest-offline") {
            let suite = "remember-ui-offline-" + UUID().uuidString
            let root = FileManager.default.temporaryDirectory.appendingPathComponent(suite)
            if ProcessInfo.processInfo.arguments.contains("--uitest-recording-delete") {
                let store = LocalRecordingStore(root: root)
                for (index, title) in ["早晨散步的录音", "周末看书的录音"].enumerated() {
                    let id = "00000000-0000-0000-0000-00000000000\(index + 1)"
                    let draft = RecordingDraft(id: id, fileURL: root.appendingPathComponent(id + ".m4a"),
                                               recordedAt: Date(), durationMS: 12000, questionID: nil,
                                               calibrationID: nil, consentConfirmedAt: Date())
                    var record = LocalRecording(draft: draft, owner: nil)
                    record.machineTranscript = title
                    try! store.save(record)
                    try! Data([0, 1, 2]).write(to: draft.fileURL)
                }
            }
            if ProcessInfo.processInfo.arguments.contains("--uitest-twin-audio-motion") {
                // A generated test signal, isolated from any real recording or voice sample.
                try! makeTwinAudioMotionFixture(in: root)
            }
            if ProcessInfo.processInfo.arguments.contains("--uitest-capture-draft") {
                // A fictional text-only draft; no microphone, network, or real account.
                let id = "00000000-0000-0000-0000-000000000017"
                let draft = RecordingDraft(id: id, fileURL: root.appendingPathComponent(id + ".m4a"),
                    recordedAt: Date(), durationMS: 10000, questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
                var record = LocalRecording(draft: draft, owner: nil, episodeID: "fixture-capture", status: "reviewing")
                record.machineTranscript = "虚构示例：我心清很好。"
                record.reviewDraft = "虚构示例：我心情很好。"
                record.automaticCorrection = TranscriptCorrection(status: "completed", draft: record.reviewDraft,
                    edits: [TranscriptCorrectionEdit(before: "心清", after: "心情", category: "word", action: "auto",
                        reason: "虚构测试的同音字校对", start: 6, end: 8)])
                try! LocalRecordingStore(root: root).save(record)
            }
            let isolatedDefaults = UserDefaults(suiteName: suite)!
            if ProcessInfo.processInfo.arguments.contains("--uitest-guest") { isolatedDefaults.set(true, forKey: "guest-access-mode") }
            let model = AppModel(recordingStore: LocalRecordingStore(root: root),
                                 defaults: isolatedDefaults, pairing: nil,
                                 recordPermission: { false })
            if ProcessInfo.processInfo.arguments.contains("--uitest-guest") { model.guestAccess.showIsolatedUITestPreview() }
            if ProcessInfo.processInfo.arguments.contains("--uitest-twin-feedback") {
                // Isolated UI state only: no actor, network calls or real approvals.
                let answer = #"{"answer_id":"fixture-answer","question":"时间紧时会怎么选？","answer":"根据记录，他会结合当时情况选择。","response_type":"SIMULATION","evidence":[],"model_version":"fixture","person_model_version":1,"stale":false,"expression":{"status":"available","text":"根据记录，他会先看看情况，再做选择。","model_version":"fixture-style","prompt_version":"expression-checked-v1"}}"#
                model.receiveTwinAnswer(try! JSONDecoder().decode(TwinAnswerRecord.self, from: Data(answer.utf8)))
                model.cloudConsentID = "fixture-not-a-real-consent"
                if ProcessInfo.processInfo.arguments.contains("--uitest-twin-chat") {
                    let turnID = model.twinChat.begin("为什么会这样选？")
                    let second = #"{"answer_id":"fixture-second","question":"为什么会这样选？","answer":"目前还没有足够的原话来确定原因。你可以录下当时的考虑。","response_type":"UNKNOWN","evidence":[],"model_version":"fixture","person_model_version":1,"stale":false}"#
                    model.receiveTwinAnswer(try! JSONDecoder().decode(TwinAnswerRecord.self, from: Data(second.utf8)), turnID: turnID)
                }
                if ProcessInfo.processInfo.arguments.contains("--uitest-twin-failure") {
                    let failed = model.twinChat.begin("这个问题还没回答。")
                    model.twinChat.fail(failed, message: "暂时没能回答，请稍后重试。")
                }
                if ProcessInfo.processInfo.arguments.contains("--uitest-twin-complete") {
                    let run = #"{"calibration_id":"fixture-calibration","twin_answer_id":"fixture-answer","question":"时间紧时会怎么选？","locked_answer":"根据记录，他会先看看情况，再做选择。","status":"complete","summary":"真人回答补充了时间紧时先行动的条件。","dimensions":[{"dimension":"DECISION","alignment":"PARTIAL","note":"补充了赶时间这个条件。","human_excerpt":"赶时间时我会先行动。"}]}"#
                    model.calibrationRun = try! JSONDecoder().decode(CalibrationRecord.self, from: Data(run.utf8))
                }
            }
            if ProcessInfo.processInfo.arguments.contains("--uitest-twin-conversation") {
                let first = #"{"answer_id":"conversation-first","question":"我喜欢安静的咖啡馆。","answer":"你刚才提到喜欢安静的咖啡馆。","response_type":"CONVERSATION","evidence":[],"model_version":"fixture","person_model_version":0,"stale":false,"conversation_id":"fixture-chat","context_turn_count":0}"#
                model.receiveTwinAnswer(try! JSONDecoder().decode(TwinAnswerRecord.self, from:Data(first.utf8)))
                let next = model.twinChat.begin("那周末呢？", conversationMode:true)
                let second = #"{"answer_id":"conversation-second","question":"那周末呢？","answer":"沿着刚才的偏好，周末可以先找一家安静的咖啡馆坐坐；这是建议，具体安排由你决定。","response_type":"CONVERSATION","evidence":[],"model_version":"fixture","person_model_version":0,"stale":false,"conversation_id":"fixture-chat","parent_answer_id":"conversation-first","context_turn_count":1}"#
                model.receiveTwinAnswer(try! JSONDecoder().decode(TwinAnswerRecord.self,from:Data(second.utf8)),turnID:next)
                model.cloudCapabilities = try! JSONDecoder().decode(BackendCapabilities.self,from:Data(#"{"stt":"fixture","stt_processing":"test","stt_configured":false,"ai_available":true,"twin_conversation":true,"chat_memory":true}"#.utf8))
                if ProcessInfo.processInfo.arguments.contains("--uitest-chat-history-memory") {
                    model.cloudCapabilities = try! JSONDecoder().decode(BackendCapabilities.self,from:Data(#"{"stt":"fixture","stt_processing":"test","stt_configured":false,"ai_available":true,"twin_conversation":true,"chat_memory":true,"chat_history_memory":true}"#.utf8))
                    model.chatHistoryMemory = try! JSONDecoder().decode(ChatHistoryMemory.self,from:Data(#"{"enabled":true,"available_turn_count":82,"items":[{"answer_id":"old-source","question":"我喜欢橙色书签，但还没有决定去哪。","answer":null,"assistant_stale":true,"created_at":"2026-10-01T00:00:00Z"}],"summaries":[{"summary":"书签偏好与未决定的安排｜本人消息：喜欢橙色书签，但还没有决定去哪。","source_answer_ids":["old-source"],"created_at":"2026-10-13T00:00:00Z"}]}"#.utf8))
                    model.twinArchive = model.chatHistoryMemory!.items
                    model.episodes = [try! JSONDecoder().decode(EpisodeRecord.self, from: Data(#"{"episode_id":"archive-saved-text","status":"ready","source":"IOS_TEXT","recorded_at":"2026-10-01T00:00:00Z","transcript":"这是一段另外保存的本人文字原话。"}"#.utf8))]
                }
                model.cloudConsentID="fixture-not-a-real-grant"
            }
            if ProcessInfo.processInfo.arguments.contains("--uitest-voice-call") {
                model.realtimeVoice.showIsolatedUITestPreview()
            }
            if ProcessInfo.processInfo.arguments.contains("--uitest-memory-detail") {
                let sample = #"{"memory_item_id":"design-memory","episode_id":"design-episode","content":"父亲总会在我出门前把吃的装进包里。","memory_type":"EVENT","source_type":"SUBJECT","confidence":1,"model_version":"isolated-ui-fixture","recorded_at":"2026-10-12T12:00:00Z","transcript":"父亲总会在我出门前把吃的装进包里。","capture_source":"IOS_TEXT","evidence":[{"evidence_id":"design-source","excerpt":"父亲总会在我出门前把吃的装进包里。","source_type":"SUBJECT","source_ref":"design-episode"}]}"#
                model.memories = [try! JSONDecoder().decode(MemoryRecord.self, from: Data(sample.utf8))]
            }
            if ProcessInfo.processInfo.arguments.contains("--uitest-voice-enrollment") {
                model.realtimeVoice.showIsolatedEnrollmentPreview()
                if ProcessInfo.processInfo.arguments.contains("--uitest-default-voice") {
                    model.cloudConsentID = "fixture-not-a-real-grant"
                } else {
                    model.voiceSampleURL = root.appendingPathComponent("fixture-no-audio.m4a")
                    if ProcessInfo.processInfo.arguments.contains("--uitest-guided-voice-sample") {
                        model.voiceSampleTranscript = AppModel.voiceReadingPrompt
                        model.voiceSampleReadingPrompt = AppModel.voiceReadingPrompt
                    }
                }
            }
            return model
        }
        #endif
        return AppModel()
    }

    #if DEBUG
    private static func makeTwinAudioMotionFixture(in root: URL) throws {
        let sampleRate = 16_000
        let sampleCount = sampleRate * 10
        let id = "00000000-0000-0000-0000-000000000010"
        let url = root.appendingPathComponent(id + ".wav")
        var wav = Data()
        func append16(_ value: UInt16) {
            wav.append(UInt8(truncatingIfNeeded: value))
            wav.append(UInt8(truncatingIfNeeded: value >> 8))
        }
        func append32(_ value: UInt32) {
            wav.append(UInt8(truncatingIfNeeded: value))
            wav.append(UInt8(truncatingIfNeeded: value >> 8))
            wav.append(UInt8(truncatingIfNeeded: value >> 16))
            wav.append(UInt8(truncatingIfNeeded: value >> 24))
        }
        wav.append(contentsOf: "RIFF".utf8)
        append32(UInt32(36 + sampleCount * 2))
        wav.append(contentsOf: "WAVEfmt ".utf8)
        append32(16); append16(1); append16(1)
        append32(UInt32(sampleRate)); append32(UInt32(sampleRate * 2))
        append16(2); append16(16)
        wav.append(contentsOf: "data".utf8)
        append32(UInt32(sampleCount * 2))
        for index in 0..<sampleCount {
            let time = Double(index) / Double(sampleRate)
            let pulse = Int(time / 1.35)
            let position = time.truncatingRemainder(dividingBy: 1.35)
            let amplitude = [0.07, 0.28, 0.72][pulse % 3]
            // Each one-second pulse has a gentle entrance and 350 ms of true silence.
            let gate = position < 1 ? min(1, position / 0.025) * min(1, (1 - position) / 0.025) : 0
            let envelope = 0.62 + 0.38 * sin(time * .pi * 5)
            let tone = 0.65 * sin(2 * .pi * 330 * time) + 0.35 * sin(2 * .pi * 440 * time)
            let sample = Int16((tone * amplitude * gate * envelope * Double(Int16.max)).rounded())
            append16(UInt16(bitPattern: sample))
        }
        let draft = RecordingDraft(id: id, fileURL: url, recordedAt: Date(), durationMS: 10_000,
                                   questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        var record = LocalRecording(draft: draft, owner: nil)
        record.machineTranscript = "合成测试音频：330 / 440 Hz 音调与静音；不是任何人的录音或声音样本。"
        try LocalRecordingStore(root: root).save(record)
        try wav.write(to: url, options: .atomic)
    }
    #endif

    var body: some Scene {
        WindowGroup {
            content
                .tint(RMColors.action)
                .environmentObject(model)
                .onOpenURL {
                    guard !model.isGuestMode else { return }
                    if $0.scheme == "rememberme", $0.host == "recording" { if !model.isRecorderPresented { model.showActiveRecording = true } }
                    else { model.importPairingLink($0) }
                }
                .task(id: scenePhase) {
                    guard scenePhase == .active else { return }
                    #if DEBUG
                    if ProcessInfo.processInfo.arguments.contains("--uitest-live-activity") { model.startLiveActivityPreview() }
                    #endif
                    if model.isGuestMode { await model.guestAccess.validate(); return }
                    model.recoverInterruptedRecordings()
                    model.devices.reconcile(owner: model.pairing.map(RecordingOwner.init))
                    model.processDeviceRecordingQueue()
                    await model.refresh()
                    if model.episodeID != nil { await model.pollEpisode() }
                }
                .onChange(of: model.pairing.map(RecordingOwner.init)) { _, owner in model.devices.reconcile(owner: owner) }
                .onChange(of: model.isUsingRealtimeAudio) { _, active in
                    if !active { model.processDeviceRecordingQueue() }
                }
                .onChange(of: model.isBusy) { _, busy in
                    if !busy { model.processDeviceRecordingQueue() }
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .background {
                        model.cancelNaturalCallStart()
                        model.realtimeVoice.endCurrentCallOnBackground()
                        model.guestAccess.stopTransientAudio(); RMKeyboard.dismiss()
                        model.stopAuxiliaryForBackground(); model.stopPlayback()
                    }
                }
        }
    }
    @ViewBuilder private var content: some View {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-offline") && ProcessInfo.processInfo.arguments.contains("--uitest-twin-audio-motion") {
            NavigationStack { TwinAudioMotionPreview() }
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-offline") && ProcessInfo.processInfo.arguments.contains("--uitest-entrustment") {
            // Isolated local draft only. No pairing, server save or real source is supplied.
            NavigationStack { EntrustmentSetupView() }
                .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("--uitest-entrustment-dark") ? .dark : .light)
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-recording-activity-style") {
            NavigationStack { RecordingActivityStylePreview() }
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-speaker-recording") {
            SpeakerRecordingView(archive: SpeakerLocalArchive())
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-design-system") {
            NavigationStack { DesignSystemShowcase() }
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-personal-model") {
            NavigationStack { PersonalModelView() }
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-personal-learning") {
            NavigationStack { PersonalLearningView() }
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-memory-detail"), let memory = model.memories.first {
            NavigationStack { MemoryDetailView(memory: memory) }
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-voice-call") || ProcessInfo.processInfo.arguments.contains("--uitest-voice-enrollment") {
            NavigationStack { TwinVoiceCallView(call: model.realtimeVoice) }
        } else if ProcessInfo.processInfo.arguments.contains("--uitest-memory-garden") {
            NavigationStack { MemoryGardenHome() }
        } else { RootView() }
        #else
        RootView()
        #endif
    }
}

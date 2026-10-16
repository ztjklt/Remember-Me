import XCTest
@testable import RememberMe

private final class ECSRequestGate: @unchecked Sendable {
    private let lock = NSLock()
    private var path: String?
    private var pending: ECSRequestProtocol?
    func hold(_ path: String?) { lock.lock(); defer { lock.unlock() }; self.path = path; pending = nil }
    func capture(_ request: ECSRequestProtocol) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard path != nil, request.request.url?.path == path else { return false }
        pending = request; return true
    }
    var hasPending: Bool { lock.lock(); defer { lock.unlock() }; return pending != nil }
    func release(_ data: Data, status: Int = 200) {
        lock.lock(); let request = pending; pending = nil; path = nil; lock.unlock()
        request?.finish(status: status, data: data)
    }
}

private final class ECSRequestProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var response: ((URLRequest) throws -> (Int, Data))?
    static let gate = ECSRequestGate()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        if Self.gate.capture(self) { return }
        do {
            let (status, data) = try Self.response!(request)
            finish(status: status, data: data)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    func finish(status: Int, data: Data) {
        let reply = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                    headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: reply, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }
}

@MainActor
final class ECSConnectionTests: XCTestCase {
    func testRetiredAudioDownloadCannotInterruptNewRecordingWithFailureNotice() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        ECSRequestProtocol.gate.hold("/api/v1/episodes/source/audio")
        let playback = Task { await model.playOriginal(episodeID: "source") }
        defer { playback.cancel(); ECSRequestProtocol.gate.release(Data(), status: 503) }
        for _ in 0..<100 { if ECSRequestProtocol.gate.hasPending { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(ECSRequestProtocol.gate.hasPending)
        model.stopPlayback(); model.isSpeakerRecording = true
        ECSRequestProtocol.gate.release(Data(#"{"error_message":"slow old download"}"#.utf8), status: 503)
        await playback.value
        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.playbackLoading)
        XCTAssertFalse(model.isPlaying)
    }
    func testClosingIdleVoiceScreenDoesNotUnlockUnrelatedWork() throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.isBusy = true
        model.cancelNaturalCallStart()
        XCTAssertTrue(model.isBusy)
    }

    func testCancelledOrBackgroundVoicePreflightCannotCreateGrantsOrCall() async throws {
        for mode in ["close", "task", "background"] {
            var active = true
            let (model, store, pairing, defaults, name) = try chatFixture(applicationIsActive: { active })
            defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
            ECSRequestProtocol.response = { request in
                XCTAssertEqual(request.httpMethod, "GET", "Canceled preflight must not create consent or a call")
                return (200, Data(#"{"available":true,"default_voice_available":true,"policy":"test","notice":"fixture","profile":{"ready":false,"status":"missing"}}"#.utf8))
            }
            model.realtimeVoice.configure(pairing, client: try client())
            await model.realtimeVoice.prepare()
            ECSRequestProtocol.gate.hold("/api/v1/consents")
            let start = Task { await model.startNaturalVoiceCall(useDefault: true) }
            defer { start.cancel(); ECSRequestProtocol.gate.release(Data("[]".utf8)) }
            for _ in 0..<100 { if ECSRequestProtocol.gate.hasPending { break }; try await Task.sleep(for: .milliseconds(10)) }
            XCTAssertTrue(ECSRequestProtocol.gate.hasPending, mode)
            switch mode {
            case "close": model.cancelNaturalCallStart()
            case "task": start.cancel()
            default: active = false
            }
            ECSRequestProtocol.gate.release(Data("[]".utf8))
            await start.value
            XCTAssertFalse(model.isBusy, mode)
            XCTAssertFalse(model.realtimeVoice.isActive, mode)
            XCTAssertNil(model.cloudConsentID, mode)
            XCTAssertNil(model.errorMessage, mode)
        }
    }

    func testBackgroundVoiceStartMakesNoRequest() async throws {
        let (model, store, _, defaults, name) = try chatFixture(applicationIsActive: { false })
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        ECSRequestProtocol.response = { _ in XCTFail("Background start must not reach the backend"); return (500, Data()) }
        await model.startNaturalVoiceCall(useDefault: true)
        XCTAssertFalse(model.isBusy)
        XCTAssertFalse(model.realtimeVoice.isActive)
    }

    func testDeviceQueueYieldsToRecordingAndResumesWithSameIdempotencyKey() async throws {
        var active = true
        let (model, store, pairing, defaults, name) = try chatFixture(applicationIsActive: { active })
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let id = UUID().uuidString
        try FileManager.default.createDirectory(at: store.root, withIntermediateDirectories: true)
        let file = store.root.appendingPathComponent(id + ".wav")
        let original = Data([1, 2, 3]); try original.write(to: file)
        var draft = RecordingDraft(id: id, fileURL: file, recordedAt: Date(), durationMS: 5000,
            questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        draft.captureSource = "WORK_3200"
        draft.captureMetadata = ["device_recording_consent_id":"recording", "device_speaker_consent_id":"speaker"]
        let record = LocalRecording(draft: draft, owner: RecordingOwner(pairing))
        try store.save(record); model.localRecordings.append(record)
        ECSRequestProtocol.response = { [self] request in
            if request.url?.path == "/api/v1/consents" {
                return (200, Data(#"[{"consent_id":"recording","scope":"RECORDING","status":"granted"},{"consent_id":"speaker","scope":"SPEAKER_IDENTIFICATION","status":"granted"}]"#.utf8))
            }
            if request.url?.path.hasSuffix("/capabilities") == true {
                return (200, Data(#"{"stt":"fixture","stt_processing":"local","stt_configured":true,"ai_available":true}"#.utf8))
            }
            if request.httpMethod == "POST" {
                XCTAssertEqual(request.url?.path, "/api/v1/episodes")
                XCTAssertTrue(String(decoding: requestBody(request), as: UTF8.self).contains(id))
                return (200, Data(#"{"episode_id":"same-device-episode"}"#.utf8))
            }
            return readFixture(request, cloudGranted: false)
        }
        ECSRequestProtocol.gate.hold("/api/v1/episodes")
        model.processDeviceRecordingQueue()
        for _ in 0..<100 { if ECSRequestProtocol.gate.hasPending { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(ECSRequestProtocol.gate.hasPending)
        XCTAssertTrue(model.isSyncingDeviceRecordings)
        XCTAssertFalse(model.recordingStartBlocked)
        XCTAssertTrue(model.prepareNewRecording(), "The UI entry must let foreground capture preempt an upload")
        active = false
        await model.startRecording() // Isolated permission denial; no microphone capture.
        XCTAssertFalse(model.isSyncingDeviceRecordings)
        XCTAssertNil(model.localRecordings.first?.episodeID)
        XCTAssertEqual(try Data(contentsOf: file), original)
        ECSRequestProtocol.gate.release(Data(#"{"episode_id":"same-device-episode"}"#.utf8))
        active = true
        model.processDeviceRecordingQueue()
        for _ in 0..<200 { if !model.isSyncingDeviceRecordings { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(model.isSyncingDeviceRecordings)
        XCTAssertEqual(model.localRecordings.first?.episodeID, "same-device-episode")
        XCTAssertEqual(try Data(contentsOf: file), original)
    }

    func testConfirmedRevocationsRejectEarlierInFlightGrantLists() async throws {
        let staleGrants = Data(#"[{"consent_id":"recording","scope":"RECORDING","status":"granted"},{"consent_id":"cloud","scope":"CLOUD_TWIN","status":"granted"},{"consent_id":"voice","scope":"VOICE","status":"granted"}]"#.utf8)
        for flow in ["cloud", "voice", "realtimeVoice"] {
            let (model, store, _, defaults, name) = try chatFixture()
            defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
            model.cloudConsentID = "cloud"; model.voiceConsentID = "voice"
            ECSRequestProtocol.gate.hold("/api/v1/consents")
            ECSRequestProtocol.response = { request in
                if request.httpMethod == "POST", request.url?.path.hasSuffix("/revoke") == true {
                    return (200, Data("{}".utf8))
                }
                throw URLError(.timedOut)
            }
            let refresh = Task { await model.refresh() }
            defer { refresh.cancel(); ECSRequestProtocol.gate.release(staleGrants) }
            for _ in 0..<100 { if ECSRequestProtocol.gate.hasPending { break }; try await Task.sleep(for: .milliseconds(10)) }
            XCTAssertTrue(ECSRequestProtocol.gate.hasPending, flow)
            let revision = model.memoryContentRevision
            switch flow {
            case "cloud": await model.revokeCloudTwin()
            case "voice": await model.revokeVoice()
            default: await model.revokeRealtimeVoice()
            }
            XCTAssertNotEqual(model.memoryContentRevision, revision, flow)
            ECSRequestProtocol.gate.release(staleGrants)
            await refresh.value
            if flow == "cloud" { XCTAssertNil(model.cloudConsentID, flow) }
            else { XCTAssertNil(model.voiceConsentID, flow) }
            XCTAssertNil(model.errorMessage, flow)
        }
    }
    func testLateVoiceRevocationCannotClearReplacementCredentials() async throws {
        for realtime in [false, true] {
            let (model, store, pairing, defaults, name) = try chatFixture()
            defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
            model.voiceConsentID = "voice"
            ECSRequestProtocol.gate.hold("/api/v1/consents/voice/revoke")
            ECSRequestProtocol.response = { _ in throw URLError(.timedOut) }
            let revoke = Task { if realtime { await model.revokeRealtimeVoice() } else { await model.revokeVoice() } }
            defer { revoke.cancel(); ECSRequestProtocol.gate.release(Data("{}".utf8)) }
            for _ in 0..<100 { if ECSRequestProtocol.gate.hasPending { break }; try await Task.sleep(for: .milliseconds(10)) }
            XCTAssertTrue(ECSRequestProtocol.gate.hasPending)
            model.pairing = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint,
                token: "replacement-token", actorID: pairing.actorID, subjectID: pairing.subjectID, consentID: pairing.consentID)
            model.voiceConsentID = "replacement-voice"; model.voiceProfileReady = true
            let revision = model.memoryContentRevision
            ECSRequestProtocol.gate.release(Data("{}".utf8)); await revoke.value
            XCTAssertEqual(model.voiceConsentID, "replacement-voice")
            XCTAssertTrue(model.voiceProfileReady)
            XCTAssertEqual(model.memoryContentRevision, revision)
            XCTAssertNil(model.errorMessage)
        }
    }
    func testRefreshMetadataHasBoundedReadDeadlines() async throws {
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.timeoutInterval, 30, request.url!.path)
            return readFixture(request)
        }
        let api = try client()
        _ = try await api.consents(subjectID: "subject")
        _ = try await api.memories("subject")
        _ = try await api.episodes("subject")
        _ = try await api.model("subject")
        _ = try await api.questions("subject")
        _ = try await api.calibrations(subjectID: "subject")
    }

    func testConfirmedRevocationClearsCachedAccessBeforeLaterMetadataTimeout() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.cloudConsentID = "cloud"; model.voiceConsentID = "voice"
        model.modelVersion = 7
        model.receiveTwinAnswer(try chatAnswer("private-answer", question: "已有的问题"))
        ECSRequestProtocol.response = { request in
            if request.url?.path == "/api/v1/consents" {
                return (200, Data(#"[{"consent_id":"recording","scope":"RECORDING","status":"granted"}]"#.utf8))
            }
            throw URLError(.timedOut)
        }

        await model.refresh()

        XCTAssertNil(model.cloudConsentID); XCTAssertNil(model.voiceConsentID)
        XCTAssertNil(model.twinAnswer)
        XCTAssertTrue(model.twinChat.turns.isEmpty)
        XCTAssertEqual(model.modelVersion, 0)
        XCTAssertNotNil(model.errorMessage)
    }

    func testTimedOutRefreshPreservesCurrentContentConsentsAndDraft() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.modelVersion = 7
        model.cloudConsentID = "cloud"
        model.voiceConsentID = "voice"
        model.queryDraft = "还没有发送的问题"
        model.receiveTwinAnswer(try chatAnswer("visible-answer", question: "已有的问题"))
        ECSRequestProtocol.response = { _ in throw URLError(.timedOut) }

        await model.refresh()

        XCTAssertEqual(model.modelVersion, 7)
        XCTAssertEqual(model.twinAnswer?.id, "visible-answer")
        XCTAssertEqual(model.cloudConsentID, "cloud")
        XCTAssertEqual(model.voiceConsentID, "voice")
        XCTAssertEqual(model.queryDraft, "还没有发送的问题")
        XCTAssertTrue(model.errorMessage?.contains("当前内容已保留") == true)
    }

    func testServiceUnavailableRefreshPreservesContentForRetry() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.modelVersion = 7
        model.cloudConsentID = "cloud"
        model.receiveTwinAnswer(try chatAnswer("visible-answer", question: "已有的问题"))
        ECSRequestProtocol.response = { _ in
            (503, Data(#"{"error":{"message":"服务暂时不可用"}}"#.utf8))
        }

        await model.refresh()

        XCTAssertEqual(model.modelVersion, 7)
        XCTAssertEqual(model.cloudConsentID, "cloud")
        XCTAssertEqual(model.twinAnswer?.id, "visible-answer")
        XCTAssertNotNil(model.errorMessage)
    }

    func testForbiddenRefreshStillClearsContentAndConsents() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.modelVersion = 7
        model.cloudConsentID = "cloud"; model.voiceConsentID = "voice"
        model.receiveTwinAnswer(try chatAnswer("visible-answer", question: "已有的问题"))
        ECSRequestProtocol.response = { _ in
            (403, Data(#"{"error":{"message":"本人空间访问已撤销"}}"#.utf8))
        }

        await model.refresh()

        XCTAssertEqual(model.modelVersion, 0)
        XCTAssertNil(model.twinAnswer)
        XCTAssertNil(model.cloudConsentID); XCTAssertNil(model.voiceConsentID)
        XCTAssertTrue(model.errorMessage?.contains("403") == true)
    }

    func testCancelledRefreshKeepsCurrentContentWithoutShowingAnAlert() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.modelVersion = 7
        model.receiveTwinAnswer(try chatAnswer("visible-answer", question: "已有的问题"))
        ECSRequestProtocol.response = { _ in throw URLError(.cancelled) }

        await model.refresh()

        XCTAssertNil(model.errorMessage)
        XCTAssertEqual(model.modelVersion, 7)
        XCTAssertEqual(model.twinAnswer?.id, "visible-answer")
    }

    func testCancelledRefreshTaskDoesNotReplaceAnExistingNotice() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.modelVersion = 7
        model.errorMessage = "原音已保存，请核对文字。"
        ECSRequestProtocol.response = { _ in throw URLError(.cancelled) }
        let refresh = Task { await model.refresh() }
        refresh.cancel()
        await refresh.value

        XCTAssertEqual(model.errorMessage, "原音已保存，请核对文字。")
        XCTAssertEqual(model.modelVersion, 7)
    }

    func testUnauthorizedRefreshStillClearsContentAndShowsTheFailure() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.modelVersion = 7
        model.receiveTwinAnswer(try chatAnswer("visible-answer", question: "已有的问题"))
        ECSRequestProtocol.response = { _ in
            (401, Data(#"{"error":{"message":"登录已失效，请重新登录。"}}"#.utf8))
        }

        await model.refresh()

        XCTAssertEqual(model.modelVersion, 0)
        XCTAssertNil(model.twinAnswer)
        XCTAssertEqual(model.errorMessage, "服务返回 401：登录已失效，请重新登录。")
    }

    func testLeavingChatHistoryWhileLoadingDoesNotShowACancellationAlert() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.cloudConsentID = "cloud"
        model.cloudCapabilities = try JSONDecoder().decode(BackendCapabilities.self, from: Data(#"{"stt":"fixture","stt_processing":"test","stt_configured":false,"ai_available":true,"chat_history_memory":true}"#.utf8))
        ECSRequestProtocol.response = { _ in throw URLError(.cancelled) }

        await model.loadChatHistoryMemory()

        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.isLoadingChatMemory)
        XCTAssertEqual(model.cloudConsentID, "cloud")
    }

    func testHistoricalChatSearchEncodesQueryAndReferencesWithoutForgedMessages() async throws {
        ECSRequestProtocol.response = { [self] request in try historicalFixtureReply(request) }
        let reply = try await client().chatHistoryMemory(subjectID: "subject", cloudConsentID: "cloud", query: "以前 & 后来？+ #", answerIDs: ["old", "older"])
        XCTAssertEqual(reply.available_turn_count, 80)
        XCTAssertNil(reply.items[0].answer)
        XCTAssertEqual(reply.items[0].question, "我还没决定。")
    }
    nonisolated private func historicalFixtureReply(_ request: URLRequest) throws -> (Int, Data) {
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertTrue(request.url!.path.hasSuffix("/twin/chat-memory"))
            let query = URLComponents(url: request.url!.absoluteURL, resolvingAgainstBaseURL: true)?.queryItems ?? []
            XCTAssertEqual(query.first(where: { $0.name == "q" })?.value, "以前 & 后来？+ #")
            XCTAssertEqual(query.first(where: { $0.name == "answer_ids" })?.value, "old,older")
            return (200, Data(#"{"enabled":true,"available_turn_count":80,"items":[{"answer_id":"old","question":"我还没决定。","answer":null,"assistant_stale":true,"created_at":"2026-10-01T00:00:00Z"}],"summaries":[]}"#.utf8))
    }
    func testHistoricalChatSwitchAndClearUseScopedEndpoints() async throws {
        var methods: [String] = []
        ECSRequestProtocol.response = { [self] request in
            methods.append(request.httpMethod!)
            XCTAssertEqual(request.url!.path, "/api/v1/subjects/subject/twin/chat-memory")
            if request.httpMethod == "PUT" {
                let body = try JSONSerialization.jsonObject(with: requestBody(request)) as! [String: Any]
                XCTAssertEqual(Set(body.keys), ["enabled"])
                XCTAssertEqual(body["enabled"] as? Bool, false)
            }
            return (200, Data(#"{"enabled":false}"#.utf8))
        }
        try await client().setChatHistoryMemory(subjectID: "subject", enabled: false)
        try await client().clearChatHistoryMemory(subjectID: "subject")
        XCTAssertEqual(methods, ["PUT", "DELETE"])
    }
    func testHistoricalMemoryClearInvalidatesVisibleRepliesButKeepsUserHistory() async throws {
        let (model, store, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.cloudCapabilities = try JSONDecoder().decode(BackendCapabilities.self, from: Data(#"{"stt":"fixture","stt_processing":"test","stt_configured":false,"ai_available":true,"chat_history_memory":true}"#.utf8))
        model.cloudConsentID = "cloud"
        model.receiveTwinAnswer(try chatAnswer("saved", question: "本人旧消息"))
        ECSRequestProtocol.response = { [self] request in emptyChatMemoryReply(request) }
        await model.clearChatHistoryMemory()
        let turn = try XCTUnwrap(model.twinChat.turns.first)
        XCTAssertTrue(turn.invalidated)
        XCTAssertEqual(turn.question, "本人旧消息")
        XCTAssertEqual(model.chatHistoryMemory?.available_turn_count, 0)
    }
    nonisolated private func emptyChatMemoryReply(_ request: URLRequest) -> (Int, Data) {
        if request.httpMethod == "DELETE" { return (200, Data(#"{"enabled":true}"#.utf8)) }
        return (200, Data(#"{"enabled":true,"available_turn_count":0,"items":[],"summaries":[]}"#.utf8))
    }
    func testHistoricalRecallMetadataKeepsOldAnswersCompatible() throws {
        let old = try chatAnswer("old", question: "旧回答")
        XCTAssertNil(old.recalled_turn_count)
        let reply = try JSONDecoder().decode(TwinAnswerRecord.self, from: Data(#"{"answer_id":"new","question":"回顾","answer":"你以前说还没决定","response_type":"CONVERSATION","evidence":[],"model_version":"fixture","person_model_version":1,"stale":false,"recalled_turn_count":1,"recalled_answer_ids":["old"],"history_summary_status":"ready"}"#.utf8))
        XCTAssertEqual(reply.recalled_turn_count, 1)
        XCTAssertEqual(reply.recalled_answer_ids, ["old"])
    }

    func testOwnerTwinArchiveUsesScopedConsentAndPreservesOpaqueCursor() async throws {
        let cursor = "page+/=&?", consent = "cloud+grant"
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/v1/subjects/subject/twin/answer-history")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer fixture-token")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            XCTAssertEqual(archiveQueryValue(request, name: "cloud_consent_id"), consent)
            XCTAssertEqual(archiveQueryValue(request, name: "cursor"), cursor)
            let formDecodedQuery = request.url!.query!.replacingOccurrences(of: "+", with: " ").removingPercentEncoding!
            XCTAssertTrue(formDecodedQuery.contains("cloud_consent_id=" + consent))
            XCTAssertTrue(formDecodedQuery.contains("cursor=" + cursor))
            return (200, Data(#"{"items":[{"answer_id":"old","question":"以前聊过的事","answer":null,"assistant_stale":true,"created_at":"2026-10-01T00:00:00Z"}],"next_cursor":"next-page"}"#.utf8))
        }
        let history = try await client().twinAnswerHistory(subjectID: "subject", cloudConsentID: consent, cursor: cursor)
        XCTAssertEqual(history.items.map(\.id), ["old"])
        XCTAssertNil(history.items[0].answer)
        XCTAssertTrue(history.items[0].assistant_stale)
        XCTAssertEqual(history.next_cursor, "next-page")
    }

    func testOwnerTwinArchivePaginatesWithoutDuplicatingTurnsAndRefreshReplacesResults() async throws {
        let (model, store, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.cloudConsentID = "cloud"
        var requests = 0
        ECSRequestProtocol.response = { [self] request in
            requests += 1
            let cursor = archiveQueryValue(request, name: "cursor")
            switch requests {
            case 1:
                XCTAssertNil(cursor)
                return (200, Data(#"{"items":[{"answer_id":"first","question":"最近文字对话","answer":"先前的回答","assistant_stale":false,"created_at":"2026-10-16T01:00:00Z"}],"next_cursor":"older-page"}"#.utf8))
            case 2:
                XCTAssertEqual(cursor, "older-page")
                return (200, Data(#"{"items":[{"answer_id":"first","question":"重复边界","answer":"先前的回答","assistant_stale":false,"created_at":"2026-10-16T01:00:00Z"},{"answer_id":"older","question":"较早语音对话","answer":null,"assistant_stale":true,"created_at":"2026-10-15T01:00:00Z"}],"next_cursor":null}"#.utf8))
            default:
                XCTAssertEqual(requests, 3)
                XCTAssertNil(cursor)
                return (200, Data(#"{"items":[{"answer_id":"fresh","question":"新对话","answer":"新回答","assistant_stale":false,"created_at":"2026-10-16T02:00:00Z"}],"next_cursor":null}"#.utf8))
            }
        }
        await model.loadTwinArchive()
        XCTAssertEqual(model.twinArchiveOwner, RecordingOwner(pairing))
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["first"])
        XCTAssertEqual(model.twinArchiveCursor, "older-page")
        await model.loadTwinArchive(nextPage: true)
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["first", "older"])
        XCTAssertEqual(model.visibleTwinArchive[0].question, "最近文字对话")
        XCTAssertNil(model.twinArchiveCursor)
        await model.loadTwinArchive(nextPage: true)
        XCTAssertEqual(requests, 2, "An exhausted archive must not fetch the first page again")
        await model.loadTwinArchive()
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["fresh"])
        XCTAssertEqual(requests, 3)
        XCTAssertNil(model.twinArchiveError)
        XCTAssertFalse(model.isLoadingTwinArchive)
    }

    func testOwnerTwinArchiveFailureKeepsLoadedTurnsAndAllowsRetry() async throws {
        let (model, store, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        model.cloudConsentID = "cloud"
        model.twinArchiveOwner = RecordingOwner(pairing)
        model.twinArchive = [archiveTurn("kept")]; model.twinArchiveCursor = "retry-page"
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(archiveQueryValue(request, name: "cursor"), "retry-page")
            return (503, Data(#"{"error":{"message":"fixture offline"}}"#.utf8))
        }
        await model.loadTwinArchive(nextPage: true)
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["kept"])
        XCTAssertEqual(model.twinArchiveCursor, "retry-page")
        XCTAssertNotNil(model.twinArchiveError)
        XCTAssertFalse(model.isLoadingTwinArchive)
        ECSRequestProtocol.response = { _ in (200, Data(#"{"items":[],"next_cursor":null}"#.utf8)) }
        await model.loadTwinArchive(nextPage: true)
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["kept"])
        XCTAssertNil(model.twinArchiveCursor); XCTAssertNil(model.twinArchiveError)
    }

    func testArchiveDeleteSuccessRemovesOnlyChosenTurnFromArchiveAndProtectedIndex() async throws {
        let (model, store, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let owner = RecordingOwner(pairing), chosen = archiveTurn("chosen")
        model.cloudConsentID = "cloud"
        model.twinArchiveOwner = owner; model.twinArchive = [chosen, archiveTurn("kept")]
        model.receiveTwinAnswer(try chatAnswer("kept", question: "保留的对话"))
        let next = model.twinChat.begin("删除的对话", conversationMode: true)
        model.receiveTwinAnswer(try chatAnswer("chosen", question: "删除的对话"), turnID: next)
        model.queryDraft = "尚未发送的草稿"
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(request.url?.path, "/api/v1/subjects/subject/twin/answers/chosen")
            return (200, Data(#"{"deleted":true,"cleanup_pending":false}"#.utf8))
        }
        let complete = await model.deleteArchivedTwinTurn(chosen, owner: owner)
        XCTAssertTrue(complete)
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["kept"])
        XCTAssertEqual(model.visibleTwinArchive[0].question, "本人原话 kept")
        XCTAssertNil(model.visibleTwinArchive[0].answer, "A cached reply may quote the deleted turn")
        XCTAssertTrue(model.visibleTwinArchive[0].assistant_stale)
        XCTAssertEqual(model.twinChat.turns.map { $0.answer?.id }, ["kept"])
        XCTAssertEqual(model.twinAnswer?.id, "kept")
        XCTAssertTrue(model.twinChat.turns[0].invalidated)
        XCTAssertEqual(model.queryDraft, "尚未发送的草稿")
        let persisted = try TwinChatStore(root: store.root.appendingPathComponent("ChatIndex")).load(pairing)
        XCTAssertEqual(persisted.map(\.answerID), ["kept"])
        XCTAssertFalse(model.isBusy)
        ECSRequestProtocol.response = { _ in
            (200, Data(#"{"items":[{"answer_id":"kept","question":"本人原话 kept","answer":"重新核验的回答","assistant_stale":false,"created_at":"2026-10-16T01:00:00Z"}],"next_cursor":null}"#.utf8))
        }
        await model.loadTwinArchive()
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["kept"])
        XCTAssertEqual(model.visibleTwinArchive[0].answer, "重新核验的回答")
        XCTAssertFalse(model.visibleTwinArchive[0].assistant_stale)
    }

    func testArchiveDeletePendingHidesContentAndCanRetryCleanup() async throws {
        let (model, store, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let owner = RecordingOwner(pairing), chosen = archiveTurn("chosen")
        model.cloudConsentID = "cloud"
        model.twinArchiveOwner = owner; model.twinArchive = [chosen, archiveTurn("kept")]
        model.receiveTwinAnswer(try chatAnswer("chosen", question: "删除的对话"))
        ECSRequestProtocol.response = { _ in (200, Data(#"{"deleted":true,"cleanup_pending":true}"#.utf8)) }
        let pending = await model.deleteArchivedTwinTurn(chosen, owner: owner)
        XCTAssertFalse(pending)
        let tombstone = try XCTUnwrap(model.visibleTwinArchive.first)
        XCTAssertEqual(tombstone.id, "chosen"); XCTAssertTrue(tombstone.deletion_pending == true)
        XCTAssertEqual(tombstone.question, "对话已删除，清理待重试")
        XCTAssertNil(tombstone.answer)
        XCTAssertEqual(model.visibleTwinArchive.last?.id, "kept")
        XCTAssertEqual(model.visibleTwinArchive.last?.question, "本人原话 kept")
        XCTAssertNil(model.visibleTwinArchive.last?.answer)
        XCTAssertTrue(model.visibleTwinArchive.last?.assistant_stale == true)
        XCTAssertTrue(model.twinChat.turns.isEmpty); XCTAssertNil(model.twinAnswer)
        XCTAssertNotNil(model.twinArchiveError)
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/subjects/subject/twin/answers/chosen")
            return (200, Data(#"{"deleted":true,"cleanup_pending":false}"#.utf8))
        }
        let completed = await model.deleteArchivedTwinTurn(tombstone, owner: owner)
        XCTAssertTrue(completed)
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["kept"])
        XCTAssertNil(model.twinArchiveError, "A successful cleanup retry must dismiss the old failure notice")
        XCTAssertFalse(model.isBusy)
    }

    func testArchiveDeleteFailedReceiptAndNetworkFailureKeepOriginalForRetry() async throws {
        let (model, store, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let owner = RecordingOwner(pairing), chosen = archiveTurn("chosen")
        model.cloudConsentID = "cloud"
        model.twinArchiveOwner = owner; model.twinArchive = [chosen, archiveTurn("kept")]
        model.receiveTwinAnswer(try chatAnswer("chosen", question: "不能丢失的对话"))
        for status in [200, 503] {
            ECSRequestProtocol.response = { _ in
                (status, Data((status == 200 ? #"{"deleted":false,"cleanup_pending":false}"# : #"{"error":{"message":"fixture offline"}}"#).utf8))
            }
            let complete = await model.deleteArchivedTwinTurn(chosen, owner: owner)
            XCTAssertFalse(complete)
            XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["chosen", "kept"])
            XCTAssertEqual(model.visibleTwinArchive[0].question, chosen.question)
            XCTAssertEqual(model.visibleTwinArchive[0].answer, chosen.answer)
            XCTAssertNil(model.visibleTwinArchive[0].deletion_pending)
            XCTAssertEqual(model.twinChat.turns.first?.answer?.id, "chosen")
            XCTAssertEqual(model.twinAnswer?.id, "chosen")
            XCTAssertNotNil(model.twinArchiveError)
            XCTAssertFalse(model.isBusy)
        }
    }

    func testArchiveVisibilityAndDeletionRejectAnotherActorSubjectAndService() async throws {
        let (model, store, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let owner = RecordingOwner(pairing), turn = archiveTurn("private")
        model.cloudConsentID = "cloud"
        model.twinArchiveOwner = owner; model.twinArchive = [turn]
        ECSRequestProtocol.response = { _ in XCTFail("A foreign owner must not delete this archive"); return (500, Data()) }
        for foreign in [
            Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token, actorID: "other", subjectID: pairing.subjectID, consentID: "recording"),
            Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token, actorID: pairing.actorID, subjectID: "other", consentID: "recording"),
            Pairing(baseURL: "https://other.invalid", fingerprint: pairing.fingerprint, token: pairing.token, actorID: pairing.actorID, subjectID: pairing.subjectID, consentID: "recording")
        ] {
            model.pairing = foreign
            XCTAssertTrue(model.visibleTwinArchive.isEmpty)
            let deleted = await model.deleteArchivedTwinTurn(turn, owner: owner)
            XCTAssertFalse(deleted)
            XCTAssertEqual(model.twinArchive.map(\.id), ["private"])
        }
    }

    func testArchiveRequestsRequireConsentAndRemainBlockedInGuestMode() async throws {
        let (model, store, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let owner = RecordingOwner(pairing), turn = archiveTurn("owner-private")
        model.twinArchiveOwner = owner; model.twinArchive = [turn]
        ECSRequestProtocol.response = { _ in XCTFail("Missing consent or guest mode must not call owner archive endpoints"); return (500, Data()) }
        await model.loadTwinArchive()
        XCTAssertTrue(model.visibleTwinArchive.isEmpty)
        model.cloudConsentID = "cloud"
        XCTAssertEqual(model.visibleTwinArchive.map(\.id), ["owner-private"])
        model.cloudConsentID = nil
        XCTAssertTrue(model.visibleTwinArchive.isEmpty, "Revoked consent must hide already-cached owner history")
        await model.loadTwinArchive()
        defaults.set(true, forKey: "guest-access-mode")
        let api = try client()
        let guest = AppModel(recordingStore: store, defaults: defaults, pairing: pairing, apiClientFactory: { _ in api })
        // Even stale owner fields must not bypass the guest-mode guard.
        guest.pairing = pairing; guest.cloudConsentID = "cloud"
        guest.twinArchiveOwner = owner; guest.twinArchive = [turn]
        XCTAssertTrue(guest.isGuestMode); XCTAssertTrue(guest.visibleTwinArchive.isEmpty)
        await guest.loadTwinArchive()
        let deleted = await guest.deleteArchivedTwinTurn(turn, owner: owner)
        XCTAssertFalse(deleted)
        XCTAssertEqual(guest.twinArchive.map(\.id), ["owner-private"])
        XCTAssertFalse(guest.isLoadingTwinArchive)
    }

    func testRemovingSavedChatAnswerKeepsOtherTurnsAndBreaksDeletedParentLink() throws {
        let saved = [
            TwinChatStoredTurn(id: UUID(), question: "被删除的对话", answerID: "chosen"),
            TwinChatStoredTurn(id: UUID(), question: "后续对话", answerID: "kept", previousAnswerID: "chosen", conversationMode: true),
            TwinChatStoredTurn(id: UUID(), question: "独立对话", answerID: "independent")
        ]
        var history = TwinChatHistory(stored: saved)
        history.receive(try chatAnswer("kept", question: "后续对话"), for: saved[1].id)
        let pending = history.begin("还没回答的问题", conversationMode: true)
        history.removeAnswer("chosen")
        XCTAssertEqual(history.turns.map(\.question), ["后续对话", "独立对话", "还没回答的问题"])
        XCTAssertNil(history.turns[0].previousAnswerID)
        XCTAssertEqual(history.turns[0].answer?.id, "kept")
        XCTAssertTrue(history.turns[0].invalidated)
        XCTAssertEqual(history.turns[1].savedAnswerID, "independent")
        XCTAssertEqual(history.turns[2].id, pending)
        XCTAssertEqual(history.turns[2].previousAnswerID, "independent")
        XCTAssertEqual(history.turns[2].failure, "资料已更新，请重新发送这条消息。")
        XCTAssertNotNil(history.turns[2].requestID)
    }

    private func archiveTurn(_ id: String) -> HistoricalChatTurn {
        HistoricalChatTurn(answer_id: id, question: "本人原话 " + id, answer: "当时回复 " + id,
                           assistant_stale: false, created_at: "2026-10-16T01:00:00Z")
    }
    nonisolated private func archiveQueryValue(_ request: URLRequest, name: String) -> String? {
        URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?
            .first(where: { $0.name == name })?.value
    }
    private func automaticRecordingFixture() throws -> (AppModel, LocalRecordingStore, Pairing, UserDefaults, String) {
        let (model, store, _, defaults, name) = try chatFixture()
        let pairing = Pairing(baseURL: ECSConfiguration.baseURL, fingerprint: "", token: "fixture-token",
            actorID: "actor", subjectID: "subject", consentID: "recording", connectionKind: "cloudbase")
        XCTAssertTrue(model.applyConnection(pairing, persist: false))
        try addAutomaticDraft(model, store: store)
        return (model, store, pairing, defaults, name)
    }
    private func addAutomaticDraft(_ model: AppModel, store: LocalRecordingStore) throws {
        let id = UUID().uuidString
        try FileManager.default.createDirectory(at: store.root, withIntermediateDirectories: true)
        let file = store.root.appendingPathComponent(id + ".m4a")
        try Data([1, 2, 3]).write(to: file) // Synthetic bytes; no microphone or remote provider.
        let draft = RecordingDraft(id: id, fileURL: file, recordedAt: Date(), durationMS: 10000,
            questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        let record = LocalRecording(draft: draft, owner: model.pairing.map(RecordingOwner.init))
        try store.save(record); model.localRecordings.append(record)
        XCTAssertTrue(model.selectLocalRecording(id))
    }
    nonisolated private func automaticFixtureReply(_ request: URLRequest, policy: String = "fixture-asr-v1", revoked: Bool = false) throws -> (Int, Data) {
        let path = request.url!.path
        let value: [String: Any]
        if path.hasSuffix("/capabilities") {
            value = ["stt":"fixture", "stt_processing":"cloud", "stt_configured":true,
                     "cloud_asr_policy":policy, "ai_available":true]
        } else if path == "/api/v1/consents" {
            return (200, Data((revoked ? "[]" : #"[{"consent_id":"recording","scope":"RECORDING","status":"granted"}]"#).utf8))
        } else if path == "/api/v1/episodes" {
            value = ["episode_id":"automatic-episode"]
        } else if path.hasSuffix("/transcript-review") {
            value = ["state":"reviewing", "transcript":"这是一段合成测试文字。"]
        } else if path == "/api/v1/episodes/automatic-episode" {
            value = ["status":"transcribing"]
        } else { XCTFail("Unexpected automatic-transcription request: \(path)"); return (404, Data()) }
        return (200, try JSONSerialization.data(withJSONObject: value))
    }
    func testFirstCloudApprovalIsRequiredThenNextRecordingTransfersAutomaticallyToReview() async throws {
        let (model, store, pairing, defaults, name) = try automaticRecordingFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        var uploads = 0
        ECSRequestProtocol.response = { [self] request in
            if request.httpMethod == "POST" {
                XCTAssertEqual(request.url!.path, "/api/v1/episodes"); uploads += 1
                XCTAssertTrue(String(decoding: requestBody(request), as: UTF8.self).contains("fixture-asr-v1"))
            }
            return try automaticFixtureReply(request)
        }
        let policy = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertEqual(policy, "fixture-asr-v1"); XCTAssertEqual(uploads, 0)
        let id = try XCTUnwrap(model.draft?.id)
        await model.approveAutomaticTranscription(policy!, recordingID: id, scope: ReviewScope(pairing))
        XCTAssertEqual(uploads, 1); XCTAssertTrue(model.isTranscriptReviewReady)
        XCTAssertEqual(model.transcriptDraft, "这是一段合成测试文字。")
        XCTAssertNil(model.localRecordings.first(where: { $0.id == id })?.reviewedAt) // AI memory still needs user review.
        XCTAssertTrue(model.hasAutomaticTranscriptionApproval(policy!, pairing: pairing))
        try addAutomaticDraft(model, store: store)
        let nextPolicy = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertNil(nextPolicy); XCTAssertEqual(uploads, 2); XCTAssertTrue(model.isTranscriptReviewReady)
    }
    func testChangedAsrPurposeAndRevokedRecordingConsentRequireFreshConfirmation() async throws {
        let (model, store, pairing, defaults, name) = try automaticRecordingFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        ECSRequestProtocol.response = { [self] request in try automaticFixtureReply(request) }
        await model.approveAutomaticTranscription("fixture-asr-v1", recordingID: model.draft!.id, scope: ReviewScope(pairing))
        try addAutomaticDraft(model, store: store)
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(request.httpMethod, "GET")
            return try automaticFixtureReply(request, policy: "fixture-asr-v2")
        }
        let changed = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertEqual(changed, "fixture-asr-v2")
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(request.httpMethod, "GET") // Revocation must never auto-create a new grant.
            return try automaticFixtureReply(request, revoked: true)
        }
        let revoked = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertEqual(revoked, "fixture-asr-v1")
        XCTAssertFalse(model.hasAutomaticTranscriptionApproval("fixture-asr-v1", pairing: pairing))
        XCTAssertNil(model.episodeID)
    }
    func testAutomaticApprovalIsBoundToServerActorAndSubjectAndSettingsStopTransfers() async throws {
        let (model, store, pairing, defaults, name) = try automaticRecordingFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        ECSRequestProtocol.response = { [self] request in try automaticFixtureReply(request) }
        await model.approveAutomaticTranscription("fixture-asr-v1", recordingID: model.draft!.id, scope: ReviewScope(pairing))
        for foreign in [Pairing(baseURL: pairing.baseURL, fingerprint: "", token: "fixture-token", actorID: "other", subjectID: "subject", consentID: "recording"),
                        Pairing(baseURL: pairing.baseURL, fingerprint: "", token: "fixture-token", actorID: "actor", subjectID: "other", consentID: "recording"),
                        Pairing(baseURL: "https://other.invalid", fingerprint: String(repeating: "a", count: 64), token: "fixture-token", actorID: "actor", subjectID: "subject", consentID: "recording")] {
            XCTAssertFalse(model.hasAutomaticTranscriptionApproval("fixture-asr-v1", pairing: foreign))
        }
        try addAutomaticDraft(model, store: store); model.automaticTranscriptionEnabled = false
        ECSRequestProtocol.response = { _ in XCTFail("Disabled automatic mode must not make a network request"); return (500, Data()) }
        _ = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertNil(model.episodeID); XCTAssertNotNil(model.draft)
    }
    func testAutomaticNetworkFailureKeepsOriginalWithoutCreatingEpisodeOrConsent() async throws {
        let (model, store, _, defaults, name) = try automaticRecordingFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let id = model.draft!.id; let file = model.draft!.fileURL
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.httpMethod, "GET"); return (503, Data(#"{"error":{"message":"offline fixture"}}"#.utf8))
        }
        _ = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertEqual(model.draft?.id, id); XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
        XCTAssertNil(model.episodeID); XCTAssertNotNil(model.errorMessage)
        XCTAssertEqual(model.processingStatus, "原音已保存，待转写")
    }
    private func conversationCaps() throws -> BackendCapabilities {
        try JSONDecoder().decode(BackendCapabilities.self, from: Data(#"{"stt":"fixture","stt_processing":"test","stt_configured":false,"ai_available":true,"twin_conversation":true,"chat_memory":true}"#.utf8))
    }
    nonisolated private func dialogueData(_ id: String, question: String, parent: String? = nil) throws -> Data {
        var value: [String: Any] = ["answer_id":id,"question":question,"answer":"承接前文的会话回应。",
            "response_type":"CONVERSATION","evidence":[],"model_version":"fixture","person_model_version":0,"stale":false,"conversation_id":"conversation-fixture","context_turn_count":parent == nil ? 0 : 1]
        if let parent { value["parent_answer_id"] = parent }
        return try JSONSerialization.data(withJSONObject: value)
    }
    func testConversationSendsOnlyServerParentAndStableRequestID() async throws {
        ECSRequestProtocol.response = { [self] request in
            let value = try JSONSerialization.jsonObject(with: requestBody(request)) as! [String: Any]
            XCTAssertEqual(value["previous_answer_id"] as? String, "earlier")
            XCTAssertEqual(value["request_id"] as? String, "stable")
            XCTAssertEqual(value["conversation_mode"] as? Bool, true)
            XCTAssertNil(value["messages"]); XCTAssertNil(value["system"])
            return (200, try dialogueData("reply", question:"为什么呢", parent:"earlier"))
        }
        let answer = try await client().askTwin(subjectID:"subject",question:"为什么呢",cloudConsentID:"cloud",
            conversationMode:true,previousAnswerID:"earlier",requestID:"stable")
        XCTAssertEqual(answer.response_type,"CONVERSATION")
        XCTAssertEqual(answer.parent_answer_id,"earlier"); XCTAssertEqual(answer.context_turn_count,1)
    }
    func testSourceConflictRetryKeepsMessageAndParentButRenewsRejectedRequest() async throws {
        let (model, recordings, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName:name); try? FileManager.default.removeItem(at:recordings.root) }
        model.cloudCapabilities = try conversationCaps(); model.cloudConsentID = "cloud"
        model.receiveTwinAnswer(try chatAnswer("earlier", question: "前面的问题"))
        model.queryDraft = "为什么呢"
        var firstRequest: String?
        ECSRequestProtocol.response = { [self] request in
            let body = try JSONSerialization.jsonObject(with:requestBody(request)) as! [String:Any]
            firstRequest = body["request_id"] as? String
            return (409, Data(#"{"error":{"code":"SOURCE_CHANGED","message":"资料已变化"}}"#.utf8))
        }
        await model.askTwin()
        let id = try XCTUnwrap(model.twinChat.turns.last?.id)
        XCTAssertNotNil(model.twinChat.turns.last?.failure)
        ECSRequestProtocol.response = { [self] request in
            let body = try JSONSerialization.jsonObject(with:requestBody(request)) as! [String:Any]
            XCTAssertNotEqual(body["request_id"] as? String, firstRequest)
            XCTAssertEqual(body["previous_answer_id"] as? String,"earlier")
            return (200, try dialogueData("retry",question:"为什么呢",parent:"earlier"))
        }
        await model.retryTwin(id)
        XCTAssertEqual(model.twinChat.turns.count,2)
        XCTAssertEqual(model.twinChat.turns.last?.answer?.id,"retry")
    }
    func testConversationWorksAndRestoresBeforeAnyRecordingGrantThenNewChatResetsParent() async throws {
        let (model, recordings, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName:name); try? FileManager.default.removeItem(at:recordings.root) }
        model.cloudCapabilities = try conversationCaps()
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url!.path,"/api/v1/consents")
            return (200,Data(#"[{"consent_id":"cloud","scope":"CLOUD_TWIN","status":"granted"}]"#.utf8))
        }
        await model.refresh()
        XCTAssertNotNil(model.cloudConsentID); XCTAssertTrue(model.episodes.isEmpty)
        model.queryDraft="我喜欢安静的咖啡馆。"
        ECSRequestProtocol.response = { [self] request in
            let value = try JSONSerialization.jsonObject(with:requestBody(request)) as! [String:Any]
            XCTAssertNil(value["previous_answer_id"]); XCTAssertEqual(value["conversation_mode"] as? Bool,true)
            return (200,try dialogueData("first",question:"我喜欢安静的咖啡馆。"))
        }
        await model.askTwin()
        model.queryDraft="那周末呢？"
        ECSRequestProtocol.response = { [self] request in
            let value = try JSONSerialization.jsonObject(with:requestBody(request)) as! [String:Any]
            XCTAssertEqual(value["previous_answer_id"] as? String,"first")
            return (200,try dialogueData("second",question:"那周末呢？",parent:"first"))
        }
        await model.askTwin()
        let api=try client()
        let restored=AppModel(recordingStore:recordings,defaults:defaults,pairing:pairing,apiClientFactory:{_ in api})
        restored.cloudCapabilities=try conversationCaps()
        ECSRequestProtocol.response = { [self] request in
            switch request.url!.path {
            case "/api/v1/consents": return (200,Data(#"[{"consent_id":"cloud","scope":"CLOUD_TWIN","status":"granted"}]"#.utf8))
            case "/api/v1/subjects/subject/twin/answers/first":return (200,try dialogueData("first",question:"我喜欢安静的咖啡馆。"))
            case "/api/v1/subjects/subject/twin/answers/second":return (200,try dialogueData("second",question:"那周末呢？",parent:"first"))
            default: XCTFail("Unexpected personal-data read before recording consent");return (404,Data())
            }
        }
        await restored.refresh()
        XCTAssertEqual(restored.twinChat.turns.count,2)
        XCTAssertEqual(restored.twinChat.turns[1].previousAnswerID,"first")
        XCTAssertEqual(restored.twinChat.turns[1].conversationMode,true)
        restored.newTwinChat(); restored.queryDraft="新话题"
        ECSRequestProtocol.response = { [self] request in
            let value=try JSONSerialization.jsonObject(with:requestBody(request)) as! [String:Any]
            XCTAssertNil(value["previous_answer_id"])
            return (200,try dialogueData("new",question:"新话题"))
        }
        await restored.askTwin()
        XCTAssertEqual(restored.twinChat.turns.count,1)
    }
    func testRememberSendsOnlyConfirmedSavedMessageIDNotAssistantOrReplacementText() async throws {
        ECSRequestProtocol.response = { [self] request in
            XCTAssertTrue(request.url!.path.hasSuffix("/saved/remember"))
            let value=try JSONSerialization.jsonObject(with:requestBody(request)) as! [String:Any]
            XCTAssertEqual(Set(value.keys),["cloud_consent_id","recording_consent_id","confirmed"])
            XCTAssertEqual(value["confirmed"] as? Bool,true)
            return (201,Data(#"{"episode_id":"text-episode","memory_item_id":"note","status":"ready","source":"IOS_TEXT"}"#.utf8))
        }
        let memory=try await client().rememberChatMessage(subjectID:"subject",answerID:"saved",cloudConsentID:"cloud",recordingConsentID:"recording")
        XCTAssertEqual(memory.source,"IOS_TEXT")
    }
    private func chatAnswer(_ id: String, question: String, stale: Bool = false) throws -> TwinAnswerRecord {
        let payload: [String: Any] = ["answer_id": id, "question": question, "answer": "有来源的回答",
                                      "response_type": "ORIGINAL", "evidence": [], "model_version": "fixture",
                                      "person_model_version": 1, "stale": stale]
        return try JSONDecoder().decode(TwinAnswerRecord.self, from: JSONSerialization.data(withJSONObject: payload))
    }
    nonisolated private func answerData(_ id: String, question: String, stale: Bool = false) throws -> Data {
        try JSONSerialization.data(withJSONObject: ["answer_id": id, "question": question, "answer": "有来源的回答",
            "response_type": "ORIGINAL", "evidence": [], "model_version": "fixture", "person_model_version": 1, "stale": stale])
    }
    private func chatFixture(applicationIsActive: @escaping @MainActor () -> Bool = { true }) throws -> (AppModel, LocalRecordingStore, Pairing, UserDefaults, String) {
        let name = "chat-lifecycle-" + UUID().uuidString
        let store = LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(name))
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                              token: "fixture-token", actorID: "actor", subjectID: "subject", consentID: "recording")
        let api = try client()
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: pairing, apiClientFactory: { _ in api },
            recordPermission: { false }, applicationIsActive: applicationIsActive)
        return (model, store, pairing, defaults, name)
    }
    nonisolated private func readFixture(_ request: URLRequest, cloudGranted: Bool = true) -> (Int, Data) {
        let path = request.url!.path
        let text: String
        switch path {
        case "/api/v1/consents":
            text = cloudGranted ? #"[{"consent_id":"recording","scope":"RECORDING","status":"granted"},{"consent_id":"cloud","scope":"CLOUD_TWIN","status":"granted"}]"# : #"[{"consent_id":"recording","scope":"RECORDING","status":"granted"}]"#
        case "/api/v1/subjects/subject/person-model": text = #"{"version":1,"domains":[]}"#
        case "/api/v1/subjects/subject/episodes": text = #"{"items":[{"episode_id":"ready","status":"ready","source":"IOS_MIC","recorded_at":"2026-10-13T00:00:00Z"}]}"#
        case "/api/v1/subjects/subject/memories", "/api/v1/subjects/subject/questions", "/api/v1/subjects/subject/calibrations": text = #"{"items":[]}"#
        default: return (404, Data(#"{"error":{"message":"fixture optional service"}}"#.utf8))
        }
        return (200, Data(text.utf8))
    }
    func testProtectedChatIndexStoresOnlyLastTwentyQuestionsAndIDsInExactScope() throws {
        let (_, recordings, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        var history = TwinChatHistory()
        for index in 0..<25 {
            let id = history.begin("问题 \(index)")
            history.receive(try chatAnswer("answer-\(index)", question: "问题 \(index)"), for: id)
        }
        let store = TwinChatStore(root: recordings.root.appendingPathComponent("ChatIndex"))
        try store.save(history, pairing: pairing)
        let restored = try store.load(pairing)
        XCTAssertEqual(restored.count, 20); XCTAssertEqual(restored.first?.question, "问题 5")
        let text = String(decoding: try Data(contentsOf: store.file(pairing)), as: UTF8.self)
        XCTAssertFalse(text.contains("有来源的回答")); XCTAssertFalse(text.contains("fixture-token"))
        XCTAssertFalse(text.contains("evidence"))
        let other = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token,
                            actorID: "other", subjectID: pairing.subjectID, consentID: "recording")
        XCTAssertTrue(try store.load(other).isEmpty)
        var unreadable = TwinChatHistory(stored: restored)
        XCTAssertNil(unreadable.turns.first?.answer)
        unreadable.receive(try chatAnswer("answer-5", question: "问题 5", stale: true), for: restored[0].id)
        XCTAssertTrue(unreadable.turns[0].invalidated)
        try store.remove(pairing); XCTAssertTrue(try store.load(pairing).isEmpty)
    }
    func testRestartRevalidatesStoredAnswersAndConsentLossHidesHistory() async throws {
        let (model, recordings, pairing, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        var history = TwinChatHistory()
        let first = history.begin("旧问题"); history.receive(try chatAnswer("old", question: "旧问题"), for: first)
        let last = history.begin("新问题"); history.receive(try chatAnswer("fresh", question: "新问题"), for: last)
        let store = TwinChatStore(root: recordings.root.appendingPathComponent("ChatIndex"))
        try store.save(history, pairing: pairing)
        ECSRequestProtocol.response = { [self] request in
            if request.url!.path.hasSuffix("/twin/answers/old") { return (200, try answerData("old", question: "旧问题", stale: true)) }
            if request.url!.path.hasSuffix("/twin/answers/fresh") { return (200, try answerData("fresh", question: "新问题")) }
            return readFixture(request)
        }
        await model.refresh()
        XCTAssertEqual(model.twinChat.turns.count, 2)
        XCTAssertTrue(model.twinChat.turns[0].invalidated)
        XCTAssertFalse(model.twinChat.turns[1].invalidated)
        XCTAssertEqual(model.twinAnswer?.id, "fresh"); XCTAssertFalse(model.isRestoringChat)
        ECSRequestProtocol.response = { [self] request in readFixture(request, cloudGranted: false) }
        await model.refresh()
        XCTAssertTrue(model.twinChat.turns.isEmpty); XCTAssertNil(model.twinAnswer)
    }
    func testFailedSendRetriesSameTurnWithoutDiscardingNextDraft() async throws {
        let (model, recordings, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        ECSRequestProtocol.response = { [self] request in readFixture(request) }
        await model.refresh()
        model.queryDraft = "原问题"
        ECSRequestProtocol.response = { _ in (503, Data(#"{"error":{"message":"fixture unavailable"}}"#.utf8)) }
        await model.askTwin()
        XCTAssertEqual(model.twinChat.turns.count, 1)
        XCTAssertNotNil(model.twinChat.turns[0].failure)
        let id = model.twinChat.turns[0].id
        model.queryDraft = "还没写完的新问题"
        ECSRequestProtocol.response = { [self] request in
            let body = try JSONSerialization.jsonObject(with: requestBody(request)) as! [String: Any]
            XCTAssertEqual(body["question"] as? String, "原问题")
            return (200, try answerData("retried", question: "原问题"))
        }
        await model.retryTwin(id)
        XCTAssertEqual(model.twinChat.turns.count, 1)
        XCTAssertNil(model.twinChat.turns[0].failure)
        XCTAssertEqual(model.twinChat.turns[0].answer?.id, "retried")
        XCTAssertEqual(model.queryDraft, "还没写完的新问题")
    }
    func testCorrectionOfEarlierMessageRechecksAndLocksThatAnswerID() async throws {
        let (model, recordings, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        model.cloudConsentID = "cloud"
        model.receiveTwinAnswer(try chatAnswer("earlier", question: "较早问题"))
        let later = model.twinChat.begin("最新问题")
        model.receiveTwinAnswer(try chatAnswer("latest", question: "最新问题"), turnID: later)
        ECSRequestProtocol.response = { [self] request in
            if request.httpMethod == "GET" {
                XCTAssertTrue(request.url!.path.hasSuffix("/earlier"))
                return (200, try answerData("earlier", question: "较早问题"))
            }
            let body = try JSONSerialization.jsonObject(with: requestBody(request)) as! [String: Any]
            XCTAssertEqual(body["twin_answer_id"] as? String, "earlier")
            return (201, Data(#"{"calibration_id":"locked","twin_answer_id":"earlier","question":"较早问题","locked_answer":"有来源的回答","status":"awaiting_human","dimensions":[]}"#.utf8))
        }
        await model.startCalibration(answerID: "earlier")
        XCTAssertEqual(model.calibrationRun?.twin_answer_id, "earlier")
        XCTAssertEqual(model.twinAnswer?.id, "latest")
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(request.httpMethod, "GET")
            return (200, try answerData("latest", question: "最新问题", stale: true))
        }
        await model.startCalibration(answerID: "latest")
        XCTAssertEqual(model.calibrationRun?.twin_answer_id, "earlier")
        XCTAssertTrue(model.twinChat.turns[1].invalidated)
    }
    func testSavedAnswerReadRejectsWrongIdentityAndUsesShortTimeout() async throws {
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(request.timeoutInterval, 15)
            return (200, try answerData("wrong", question: "错误记录"))
        }
        do { _ = try await client().twinAnswer(subjectID: "subject", answerID: "expected"); XCTFail("Wrong identity accepted") }
        catch { XCTAssertTrue(error is APIError) }
    }
    func testCalibrationTranscriptResumesOnlyCurrentLinkedEpisode() throws {
        let (model, recordings, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        let run = try JSONDecoder().decode(CalibrationRecord.self, from: Data(#"{"calibration_id":"linked","twin_answer_id":"saved","question":"问题","status":"awaiting_human","human_episode_id":"human-episode","dimensions":[]}"#.utf8))
        let episode = try JSONDecoder().decode(EpisodeRecord.self, from: Data(#"{"episode_id":"human-episode","status":"reviewing","source":"IOS_MIC","recorded_at":"2026-10-13T00:00:00Z"}"#.utf8))
        model.cloudConsentID = "cloud"; model.calibrationRun = run
        XCTAssertFalse(model.resumeCalibrationTranscript(run))
        model.episodes = [episode]
        XCTAssertTrue(model.resumeCalibrationTranscript(run))
        XCTAssertEqual(model.episodeID, "human-episode")
        XCTAssertNil(model.draft)
        model.calibrationRun = nil
        XCTAssertFalse(model.resumeCalibrationTranscript(run))
    }
    func testRetryRecordingStopsAtTranscriptReviewInsteadOfWaitingForReady() async throws {
        let (model, recordings, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        model.episodeID = "ready"
        ECSRequestProtocol.response = { [self] request in
            if request.url!.path.hasSuffix("/retry") { return (200, Data(#"{}"#.utf8)) }
            if request.url!.path == "/api/v1/episodes/ready" { return (200, Data(#"{"status":"reviewing"}"#.utf8)) }
            if request.url!.path.hasSuffix("/transcript-review") { return (200, Data(#"{"state":"reviewing","transcript":"需要本人核对的文字"}"#.utf8)) }
            return readFixture(request)
        }
        await model.retryEpisode("ready")
        XCTAssertTrue(model.isTranscriptReviewReady)
        XCTAssertEqual(model.transcriptDraft, "需要本人核对的文字")
        XCTAssertFalse(model.isBusy); XCTAssertFalse(model.isPollingEpisode)
    }
    func testRecordingStatusRecoversAfterTransientTimeoutWithoutUploadingAgain() async throws {
        let (model, recordings, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        model.episodeID = "accepted-recording"
        var reads = 0
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.httpMethod, "GET", "Only status reads may be retried")
            if request.url!.path.hasSuffix("/transcript-review") {
                return (200, Data(#"{"state":"reviewing","transcript":"已接收的原音转写"}"#.utf8))
            }
            reads += 1
            if reads == 1 { throw URLError(.timedOut) }
            return (200, Data(#"{"status":"reviewing"}"#.utf8))
        }

        await model.pollEpisode()

        XCTAssertEqual(reads, 2)
        XCTAssertTrue(model.isTranscriptReviewReady)
        XCTAssertEqual(model.transcriptDraft, "已接收的原音转写")
        XCTAssertEqual(model.episodeID, "accepted-recording")
        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.isPollingEpisode)
    }

    func testRecordingStatusDoesNotRetryDeniedAccessOrCancelledReads() async throws {
        let (model, recordings, _, defaults, name) = try chatFixture()
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: recordings.root) }
        model.episodeID = "accepted-recording"
        var reads = 0
        ECSRequestProtocol.response = { _ in
            reads += 1
            return (403, Data(#"{"error":{"message":"授权已撤销"}}"#.utf8))
        }
        await model.pollEpisode()
        XCTAssertEqual(reads, 1)
        XCTAssertFalse(model.isPollingEpisode)
        XCTAssertTrue(model.errorMessage?.contains("403") == true)

        model.errorMessage = nil
        ECSRequestProtocol.response = { _ in reads += 1; throw URLError(.cancelled) }
        await model.pollEpisode()
        XCTAssertEqual(reads, 2)
        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.isPollingEpisode)
    }
    func testChatCompletesExactPendingTurnAndDoesNotDuplicateOnRefresh() throws {
        var history = TwinChatHistory()
        let first = history.begin("第一个问题")
        history.receive(try chatAnswer("first", question: "第一个问题"), for: first)
        let second = history.begin("第二个问题")
        // A refresh while another request is in flight must not fill its bubble.
        history.receive(try chatAnswer("first", question: "第一个问题"))
        XCTAssertNil(history.turns[1].answer)
        history.receive(try chatAnswer("second", question: "第二个问题"), for: second)
        history.receive(try chatAnswer("second", question: "第二个问题"))
        XCTAssertEqual(history.turns.count, 2)
        XCTAssertEqual(history.turns.map(\.question), ["第一个问题", "第二个问题"])
        XCTAssertEqual(history.turns.map { $0.answer?.id }, ["first", "second"])
    }
    func testChatFailureIsExplicitAndLateResultCannotRestoreClearedSession() throws {
        var history = TwinChatHistory()
        let request = history.begin("失败的问题")
        history.fail(request, message: "请重试")
        XCTAssertEqual(history.turns.first?.failure, "请重试")
        XCTAssertNil(history.turns.first?.answer)
        history = TwinChatHistory()
        history.receive(try chatAnswer("late", question: "失败的问题"), for: request)
        XCTAssertTrue(history.turns.isEmpty)
    }
    func testChatSourceChangeInvalidatesOldAnswersAndScopeChangeClearsDraft() throws {
        var history = TwinChatHistory()
        history.receive(try chatAnswer("old", question: "原问题"))
        let next = history.begin("新问题")
        history.receive(try chatAnswer("new", question: "新问题"), for: next)
        history.receive(try chatAnswer("new", question: "新问题", stale: true))
        XCTAssertTrue(history.turns.allSatisfy(\.invalidated))
        let name = "chat-scope-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        let store = LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(name))
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: store.root) }
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        model.receiveTwinAnswer(try chatAnswer("old", question: "旧账号问题"))
        model.queryDraft = "旧账号尚未发送的问题"
        let pairing = Pairing(baseURL: ECSConfiguration.baseURL, fingerprint: "", token: "fixture",
                              actorID: "new-actor", subjectID: "new-subject", consentID: "", connectionKind: "cloudbase")
        XCTAssertTrue(model.applyConnection(pairing, persist: false))
        XCTAssertTrue(model.twinChat.turns.isEmpty); XCTAssertTrue(model.queryDraft.isEmpty)
        XCTAssertNil(model.twinAnswer)
    }
    func testCloudBaseUsesSystemTrustOnlyForConfiguredOrigin() throws {
        let client = try APIClient(baseURL: ECSConfiguration.baseURL, fingerprint: "")
        XCTAssertEqual(client.baseURL.host, "remember-ios-api-327435-12-1411199312.sh.run.tcloudbase.com")
        XCTAssertThrowsError(try APIClient(baseURL: "https://other.invalid", fingerprint: ""))
        XCTAssertThrowsError(try APIClient(baseURL: "https://39.108.183.47", fingerprint: ""))
        XCTAssertNoThrow(try APIClient(baseURL: "https://39.108.183.47", fingerprint: String(repeating: "a", count: 64)))
    }

    func testCloudBasePairingUsesCloudConsentFlow() throws {
        let pairing = Pairing(baseURL: ECSConfiguration.baseURL, fingerprint: "", token: "fixture",
                              actorID: "actor", subjectID: "subject", consentID: "", connectionKind: "cloudbase")
        XCTAssertTrue(pairing.isCloud)
    }

    func testSystemTrustStillRefusesRedirects() {
        let session = URLSession(configuration: .ephemeral)
        let request = URLRequest(url: URL(string: ECSConfiguration.baseURL)!)
        let task = session.dataTask(with: request)
        let response = HTTPURLResponse(url: request.url!, statusCode: 302, httpVersion: nil,
                                       headerFields: ["Location": "https://other.invalid"])!
        let redirect = URLRequest(url: URL(string: "https://other.invalid")!)
        var called = false
        SystemCertificateTrust().urlSession(session, task: task, willPerformHTTPRedirection: response,
                                           newRequest: redirect) { forwarded in
            called = true
            XCTAssertNil(forwarded)
        }
        XCTAssertTrue(called)
        session.invalidateAndCancel()
    }

    private func client() throws -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ECSRequestProtocol.self]
        return try APIClient(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                             token: "fixture-token", session: URLSession(configuration: config))
    }
    nonisolated private func requestBody(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var data = Data()
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let count = stream.read(buffer, maxLength: 4096)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }
    func testLoginAndSpaceDecodingUseSharedBackend() async throws {
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/accounts/login")
            XCTAssertEqual(request.httpMethod, "POST")
            return (200, Data(#"{"actor_token":"fixture-token","actor_id":"actor","display_name":"本人"}"#.utf8))
        }
        let api = try client()
        let login = try await api.login(username: "fixture", password: "fixture-password")
        XCTAssertEqual(login.actor_id, "actor")
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/workbench/spaces")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer fixture-token")
            return (200, Data(#"{"actor_id":"actor","display_name":"本人","items":[{"subject_id":"subject","display_name":"本人","role":"owner"},{"subject_id":"shared","display_name":"亲友","role":"reader"}]}"#.utf8))
        }
        let spaces = try await api.spaces()
        XCTAssertEqual(spaces.items.map(\.role), ["owner", "reader"])
    }
    func testSemanticSearchPreservesQueryAndDecodesOriginalOnlyResult() async throws {
        let query = "A&B? 去哪里阅读+休息#2024"
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/subjects/subject/memory-search")
            let parts = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)
            XCTAssertEqual(parts?.queryItems, [URLQueryItem(name: "q", value: query)])
            let formValue = request.url?.query?.dropFirst(2).replacingOccurrences(of: "+", with: " ").removingPercentEncoding
            XCTAssertEqual(formValue, query)
            return (200, Data(#"{"items":[{"memory_item_id":"episode:fixture","statement":"核对后的原文","evidence":[{"evidence_id":"source-fixture","episode_id":"fixture","excerpt":"我去图书馆，因为那里安静。","source_type":"IOS_MIC"}]}]}"#.utf8))
        }
        let results = try await client().searchMemories(subjectID: "subject", query: query)
        XCTAssertEqual(results.first?.id, "episode:fixture")
        XCTAssertEqual(results.first?.evidence.first?.episode_id, "fixture")
        XCTAssertEqual(results.first?.evidence.first?.excerpt, "我去图书馆，因为那里安静。")
    }
    func testChangingSearchQueryClearsEarlierResultsAndError() throws {
        let name = "search-reset-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        let store = LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(name))
        defer { try? FileManager.default.removeItem(at: store.root); defaults.removePersistentDomain(forName: name) }
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        model.memorySearchCompleted = true; model.memorySearchError = "旧问题失败"; model.isSearchingMemories = true
        model.memorySearchQuery = "新的问题"
        XCTAssertFalse(model.memorySearchCompleted); XCTAssertFalse(model.isSearchingMemories)
        XCTAssertNil(model.memorySearchError); XCTAssertTrue(model.memorySearchResults.isEmpty)
    }

    func testTwinShowsOnlyCheckedSimulationWordingAndKeepsOriginalFallback() throws {
        let base: [String: Any] = ["answer_id": "fixture-answer", "question": "fixture-question",
            "answer": "有依据的回答", "response_type": "SIMULATION", "evidence": [],
            "model_version": "fixture-model", "person_model_version": 1, "stale": false]
        func decode(_ kind: String = "SIMULATION", _ status: String = "available", _ text: String = "参考范例的措辞", stale: Bool = false) throws -> TwinAnswerRecord {
            var json = base; json["response_type"] = kind; json["stale"] = stale
            json["expression"] = ["status": status, "text": text, "model_version": "fixture-style", "prompt_version": "expression-checked-v1"]
            return try JSONDecoder().decode(TwinAnswerRecord.self, from: JSONSerialization.data(withJSONObject: json))
        }
        XCTAssertEqual(try decode().displayText, "参考范例的措辞")
        XCTAssertEqual(try decode("ORIGINAL").displayText, "有依据的回答")
        XCTAssertNil(try decode(stale: true).checkedExpression)
        for status in ["rejected", "unavailable"] {
            XCTAssertEqual(try decode("SIMULATION", status).displayText, "有依据的回答")
        }
        for text in ["  ", String(repeating: "字", count: 501)] {
            XCTAssertEqual(try decode("SIMULATION", "available", text).displayText, "有依据的回答")
        }
        XCTAssertEqual(try JSONDecoder().decode(TwinAnswerRecord.self, from: JSONSerialization.data(withJSONObject: base)).displayText, "有依据的回答")
    }
    func testFeedbackLocksSavedAnswerBeforeAnyHumanUpload() async throws {
        ECSRequestProtocol.response = { [self] request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/v1/subjects/subject/calibrations")
            let body = try JSONSerialization.jsonObject(with: requestBody(request)) as! [String: String]
            XCTAssertEqual(body, ["twin_answer_id": "saved-fixture", "cloud_consent_id": "consent-fixture"])
            return (200, Data(#"{"calibration_id":"cal-fixture","twin_answer_id":"saved-fixture","question":"原问题","locked_answer":"先锁定的回答","locked_response_type":"SIMULATION","locked_model_version":"fixture","status":"awaiting_human","dimensions":[]}"#.utf8))
        }
        let lock = try await client().startCalibration(subjectID: "subject", answerID: "saved-fixture", cloudConsentID: "consent-fixture")
        XCTAssertEqual(lock.status, "awaiting_human")
        XCTAssertEqual(lock.locked_answer, "先锁定的回答")
        XCTAssertNil(lock.human_episode_id)
    }

    func testQueryConsentPolicyIsSentWithAudio() async throws {
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/subjects/subject/twin/transcribe-query")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Cloud-ASR-Policy"), "policy-fixture")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "audio/mp4")
            return (200, Data(#"{"text":"我的问题","stt_model_version":"fixture-asr"}"#.utf8))
        }
        let result = try await client().transcribeQuery(subjectID: "subject", audio: Data([1, 2]), cloudASRPolicy: "policy-fixture")
        XCTAssertEqual(result.text, "我的问题")
    }
    func testUploadPreservesIdentityIdempotencyAndConsentPolicy() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
        try Data([1, 2, 3]).write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        let draft = RecordingDraft(id: "stable-upload", fileURL: file, recordedAt: Date(), durationMS: 10000,
                                   questionID: "question", calibrationID: "calibration", consentConfirmedAt: Date())
        ECSRequestProtocol.response = { [self] request in
            let body = String(decoding: requestBody(request), as: UTF8.self)
            XCTAssertTrue(body.contains("IOS_MIC"))
            XCTAssertTrue(body.contains("stable-upload"))
            XCTAssertTrue(body.contains("policy-fixture"))
            XCTAssertTrue(body.contains("calibration"))
            XCTAssertTrue(body.contains("question"))
            XCTAssertTrue(body.contains("recording-consent"))
            return (201, Data(#"{"episode_id":"episode-fixture"}"#.utf8))
        }
        let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                              token: "fixture-token", actorID: "actor", subjectID: "subject", consentID: "recording-consent")
        let uploaded = try await client().upload(draft, pairing: pairing, cloudASRPolicy: "policy-fixture")
        XCTAssertEqual(uploaded, "episode-fixture")
    }
    func testStructuredServerFailureIsReadable() async throws {
        ECSRequestProtocol.response = { _ in
            (409, Data(#"{"error":{"code":"SOURCE_CHANGED","message":"资料已变化，请重新提问。"}}"#.utf8))
        }
        do { _ = try await client().spaces(); XCTFail("Expected rejection") }
        catch { XCTAssertTrue(error.localizedDescription.contains("资料已变化")) }
    }
    func testOldPairingDecodesWithoutCloudFields() throws {
        let old = Data(#"{"baseURL":"https://mac.invalid","fingerprint":"aaaa","token":"fixture","actorID":"actor","subjectID":"subject","consentID":"consent"}"#.utf8)
        let pairing = try JSONDecoder().decode(Pairing.self, from: old)
        XCTAssertFalse(pairing.isCloud)
    }
    func testChangingServiceArchivesPendingEpisodeInOriginalScope() throws {
        let name = "ecs-isolation-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        let store = LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(name))
        defer {
            try? FileManager.default.removeItem(at: store.root)
            defaults.removePersistentDomain(forName: name)
        }
        let mac = Pairing(baseURL: "https://mac.invalid", fingerprint: String(repeating: "a", count: 64),
                          token: "fixture", actorID: "old-actor", subjectID: "old-subject", consentID: "consent")
        let draft = RecordingDraft(id: UUID().uuidString, fileURL: store.root.appendingPathComponent("old.m4a"),
                                   recordedAt: Date(), durationMS: 10000, questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: mac)
        model.draft = draft; model.episodeID = "mac-episode"
        let cloud = Pairing(baseURL: ECSConfiguration.baseURL, fingerprint: ECSConfiguration.fingerprint,
                            token: "cloud-fixture", actorID: "new-actor", subjectID: "new-subject", consentID: "", connectionKind: "ecs")
        XCTAssertTrue(model.applyConnection(cloud, persist: false))
        XCTAssertNil(model.draft); XCTAssertNil(model.episodeID)
        XCTAssertTrue(model.visibleLocalRecordings.isEmpty)
        let retained = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(retained.owner, RecordingOwner(mac))
        XCTAssertEqual(retained.episodeID, "mac-episode")
        XCTAssertTrue(model.applyConnection(mac, persist: false))
        XCTAssertEqual(model.visibleLocalRecordings.first?.id, draft.id)
    }
}

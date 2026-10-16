import XCTest
@testable import RememberMe

@MainActor
private final class SecretRecorderFixture: EntrustmentSecretRecording {
    let file = FileManager.default.temporaryDirectory.appendingPathComponent("entrust-secret-test-\(UUID().uuidString).m4a")
    var cancelCount = 0
    var startCount = 0
    var beforeStart: (() -> Void)?
    func start(isAllowed: @escaping @MainActor () -> Bool) async throws {
        beforeStart?()
        guard isAllowed() else { throw CancellationError() }
        startCount += 1; try Data([1, 2, 3]).write(to: file)
    }
    func finish() throws -> URL { file }
    func cancel() { cancelCount += 1; try? FileManager.default.removeItem(at: file) }
}

@MainActor
private final class SecretSpeechFixture: LocalSpeechTranscriber {
    var result: Result<String, Error> = .success("那年雨夜你把蓝围巾藏进饼干盒里")
    var suspend = false
    var continuation: CheckedContinuation<String, Error>?
    var receivedURL: URL?
    func transcribe(_ file: URL) async throws -> String {
        receivedURL = file
        if suspend { return try await withCheckedThrowingContinuation { continuation = $0 } }
        return try result.get()
    }
}

@MainActor
final class EntrustmentDraftTests: XCTestCase {
    private let phrase = "那年雨夜你把蓝围巾藏进饼干盒里"
    private func savedPlan(confirmationRequired: Bool? = nil, id: String = "existing-plan", revision: Int = 3,
                           status: String = "confirmed") throws -> GuestEntrustmentPlan {
        var fields: [String: Any] = ["plan_id": id, "subject_id": "owner-space", "recipient_label": "女儿小雨",
            "condition": "after_verified_transition", "status": status, "episode_count": 2, "voice_allowed": true, "revision": revision]
        if let confirmationRequired { fields["secret_confirmation_required"] = confirmationRequired }
        return try JSONDecoder().decode(GuestEntrustmentPlan.self, from: JSONSerialization.data(withJSONObject: fields))
    }
    private func preview(_ id: String = "private-source") throws -> GuestPreview {
        try JSONDecoder().decode(GuestPreview.self, from: JSONSerialization.data(withJSONObject: [
            "source_version": "confirmed-snapshot", "episode_ids": [id], "includes_full_audio": true,
            "notice": "整段开放", "items": [["episode_id": id, "recorded_at": "2026-10-16", "transcript": "完整私密原话",
                "duration_ms": 1000, "memories": ["专属故事"]]]]))
    }
    private func readyDraft() throws -> EntrustmentSetupModel {
        let model = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        model.recipientLabel = "女儿小雨"; model.secret = phrase; model.secretReviewed = true
        model.selectedEpisodeIDs = ["private-source"]; try model.acceptPreview(preview())
        model.sourceReviewed = true; model.privateDetailConfirmed = true; model.scopeConfirmed = true; model.stage = .confirmation
        return model
    }
    func testShortRepeatedOrPunctuationPaddedSecretsCannotAdvance() {
        let model = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        model.stage = .secret
        for invalid in ["生日快乐", "哈哈哈哈哈哈哈哈哈哈哈哈哈哈", "a b c ! ，。。。。。。。。", "1234123412341234"] {
            model.secret = invalid; model.secretReviewed = true
            XCTAssertFalse(model.secretMeetsMinimum); XCTAssertFalse(model.canContinue)
        }
        model.secret = phrase
        XCTAssertTrue(model.secretMeetsMinimum); XCTAssertFalse(model.canContinue)
        model.secretReviewed = true; XCTAssertTrue(model.canContinue)
        model.privateDetailConfirmed = true; model.secret += "啊"
        XCTAssertFalse(model.secretReviewed); XCTAssertFalse(model.privateDetailConfirmed)
    }
    func testSaveRequiresExplicitPrivateDetailAndWholeSourceConfirmations() throws {
        let model = try readyDraft()
        model.privateDetailConfirmed = false
        XCTAssertThrowsError(try model.makeDraft(handoverConsentID: "handover", voiceConsentID: nil))
        model.privateDetailConfirmed = true; model.scopeConfirmed = false
        XCTAssertThrowsError(try model.makeDraft(handoverConsentID: "handover", voiceConsentID: nil))
        model.scopeConfirmed = true; model.sourceReviewed = false
        XCTAssertThrowsError(try model.makeDraft(handoverConsentID: "handover", voiceConsentID: nil))
    }
    func testGuestDraftBindsLabelAndOnlyPreviewedSourcesWithoutRecipientAccount() throws {
        let model = try readyDraft()
        let payload = try model.makeDraft(handoverConsentID: "handover", voiceConsentID: nil)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(payload)) as? [String: Any])
        XCTAssertEqual(json["recipient_label"] as? String, "女儿小雨")
        XCTAssertEqual(json["episode_ids"] as? [String], ["private-source"])
        XCTAssertEqual(json["source_version"] as? String, "confirmed-snapshot")
        XCTAssertEqual(json["private_detail_confirmed"] as? Bool, true)
        XCTAssertEqual(json["secret"] as? String, phrase)
        XCTAssertNil(json["recipient_username"]); XCTAssertNil(json["recipient_actor_id"])
        model.selectedEpisodeIDs.insert("another-source")
        XCTAssertNil(model.preview); XCTAssertFalse(model.sourceReviewed); XCTAssertFalse(model.scopeConfirmed)
        XCTAssertThrowsError(try model.makeDraft(handoverConsentID: "handover", voiceConsentID: nil))
    }
    func testMismatchedOrPartialPreviewCannotConfirmScope() throws {
        let model = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        model.selectedEpisodeIDs = ["expected"]
        XCTAssertThrowsError(try model.acceptPreview(preview("unexpected")))
        XCTAssertNil(model.preview)
        model.stage = .sources; XCTAssertFalse(model.canContinue)
    }
    func testFutureHandoverRequiresSeparateStewardAndVoiceNeedsConsent() throws {
        let model = try readyDraft()
        model.future = true; model.stage = .conditions
        XCTAssertFalse(model.canContinue)
        model.steward = "verified-steward"; XCTAssertTrue(model.canContinue)
        model.stage = .confirmation; model.allowVoice = true
        model.scopeConfirmed = true
        XCTAssertThrowsError(try model.makeDraft(handoverConsentID: "handover", voiceConsentID: nil))
        let payload = try model.makeDraft(handoverConsentID: "handover", voiceConsentID: "voice")
        XCTAssertEqual(payload.condition, "after_verified_transition"); XCTAssertEqual(payload.voice_consent_id, "voice")
    }
    func testLocalVoiceResultNeedsReviewAndTemporaryAudioIsDeleted() async throws {
        let recorder = SecretRecorderFixture(), speech = SecretSpeechFixture()
        let model = EntrustmentSetupModel(recorder: recorder, speech: speech)
        await model.startRecording(); XCTAssertTrue(model.isRecording)
        await model.finishRecording()
        XCTAssertEqual(model.secret, phrase); XCTAssertFalse(model.secretReviewed)
        XCTAssertEqual(speech.receivedURL, recorder.file)
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder.file.path))
        XCTAssertFalse(model.isRecording); XCTAssertFalse(model.isTranscribing)
        model.clearSecret(); XCTAssertTrue(model.secret.isEmpty)
    }
    func testOfflineRecognitionFailureDeletesAudioAndDoesNotExposeProviderText() async {
        let recorder = SecretRecorderFixture(), speech = SecretSpeechFixture()
        speech.result = .failure(LocalSpeechError.failed("provider echoed secret: \(phrase)"))
        let model = EntrustmentSetupModel(recorder: recorder, speech: speech)
        await model.startRecording(); await model.finishRecording()
        XCTAssertTrue(model.secret.isEmpty)
        XCTAssertFalse(model.notice?.contains(phrase) ?? true)
        XCTAssertTrue(model.notice?.contains("不会转交云端识别") == true)
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder.file.path))
    }
    func testCancelClearsFileImmediatelyAndLateOfflineResultCannotRestoreSecret() async {
        let recorder = SecretRecorderFixture(), speech = SecretSpeechFixture(); speech.suspend = true
        let model = EntrustmentSetupModel(recorder: recorder, speech: speech)
        await model.startRecording()
        let task = Task { await model.finishRecording() }
        while speech.continuation == nil { await Task.yield() }
        XCTAssertTrue(FileManager.default.fileExists(atPath: recorder.file.path))
        model.clearSecret()
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder.file.path))
        speech.continuation?.resume(returning: phrase); await task.value
        XCTAssertTrue(model.secret.isEmpty); XCTAssertNil(model.notice); XCTAssertFalse(model.isTranscribing)
    }
    func testAbandonedPrivateAudioRemovedAtInitialization() throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("entrust-secret-abandoned-\(UUID().uuidString).m4a")
        try Data([4, 5, 6]).write(to: file)
        _ = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    }
    func testEveryActiveCaptureKindBlocksPrivateSecretSetup() {
        let states = [EntrustmentCaptureState(recording: true), .init(startingRecording: true), .init(queryRecording: true),
            .init(voiceRecording: true), .init(speakerRecording: true), .init(realtimeCall: true), .init(deviceRecording: true)]
        XCTAssertFalse(EntrustmentCaptureState().blocked)
        for state in states { XCTAssertTrue(state.blocked) }
    }
    func testExistingCaptureDoesNotStartSecretRecorderOrStopOrdinaryRecording() async {
        let recorder = SecretRecorderFixture()
        let guarded = EntrustmentSetupModel(recorder: recorder, speech: SecretSpeechFixture())
        guarded.secret = phrase
        await guarded.startRecording(captureAllowed: { false })
        XCTAssertEqual(recorder.startCount, 0); XCTAssertFalse(guarded.isRecording); XCTAssertTrue(guarded.secret.isEmpty)
        XCTAssertTrue(guarded.notice?.contains("先结束") == true)
    }
    func testCaptureThatStartsDuringPermissionCheckBlocksSecretRecorder() async {
        let recorder = SecretRecorderFixture(), speech = SecretSpeechFixture()
        let model = EntrustmentSetupModel(recorder: recorder, speech: speech)
        var allowed = true
        recorder.beforeStart = { allowed = false }
        await model.startRecording(captureAllowed: { allowed })
        XCTAssertEqual(recorder.startCount, 0); XCTAssertFalse(model.isRecording)
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder.file.path))
    }
    func testRealAppRecordingPermissionInFlightBlocksSecretWithoutCancellingOriginal() async {
        let name = "EntrustmentCapture-\(UUID().uuidString)", root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: root) }
        var permission: CheckedContinuation<Bool, Never>?
        let app = AppModel(recordingStore: LocalRecordingStore(root: root), defaults: defaults, pairing: nil,
            recordPermission: { await withCheckedContinuation { permission = $0 } })
        let normalCapture = Task { await app.startRecording() }
        while permission == nil { await Task.yield() }
        XCTAssertTrue(app.isStartingRecording); XCTAssertTrue(app.entrustmentCaptureState.blocked)
        let recorder = SecretRecorderFixture()
        let guarded = EntrustmentSetupModel(recorder: recorder, speech: SecretSpeechFixture())
        await guarded.startRecording(captureAllowed: { !app.entrustmentCaptureState.blocked })
        XCTAssertEqual(recorder.startCount, 0); XCTAssertTrue(app.isStartingRecording)
        permission?.resume(returning: false); await normalCapture.value
        XCTAssertFalse(app.isStartingRecording); XCTAssertFalse(guarded.isRecording)
    }
    func testExistingServerPlanDefaultsToNoSecretReconfirmation() throws {
        XCTAssertFalse(try savedPlan().secret_confirmation_required)
        XCTAssertFalse(try savedPlan(confirmationRequired: false).secret_confirmation_required)
        XCTAssertTrue(try savedPlan(confirmationRequired: true).secret_confirmation_required)
    }
    func testSecretIndexConfirmationClearsInputAndPreservesExistingPlan() async throws {
        let draft = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        let confirmation = EntrustmentSecretIndexModel(), pending = try savedPlan(confirmationRequired: true)
        let indexed = try savedPlan(confirmationRequired: false)
        draft.secret = phrase; draft.secretReviewed = true
        let result = await confirmation.confirm(plan: pending, draft: draft, isCurrent: { true }, submit: { secret in
            XCTAssertEqual(secret, self.phrase)
            XCTAssertTrue(draft.secret.isEmpty); XCTAssertFalse(draft.secretReviewed)
            return indexed
        })
        XCTAssertEqual(result?.id, pending.id); XCTAssertEqual(result?.revision, pending.revision)
        XCTAssertEqual(result?.condition, pending.condition); XCTAssertEqual(result?.episode_count, pending.episode_count)
        XCTAssertEqual(result?.voice_allowed, pending.voice_allowed)
        XCTAssertTrue(draft.selectedEpisodeIDs.isEmpty); XCTAssertNil(draft.preview)
        XCTAssertFalse(confirmation.isBusy); XCTAssertNil(confirmation.notice)
    }
    func testSecretIndexFailureClearsInputAndDoesNotEchoServerSecret() async throws {
        let draft = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        let confirmation = EntrustmentSecretIndexModel(), pending = try savedPlan(confirmationRequired: true)
        draft.secret = phrase; draft.secretReviewed = true
        let result = await confirmation.confirm(plan: pending, draft: draft, isCurrent: { true }, submit: { _ in
            throw APIError.server(422, "provider echoed \(self.phrase)")
        })
        XCTAssertNil(result); XCTAssertTrue(draft.secret.isEmpty); XCTAssertFalse(draft.secretReviewed)
        XCTAssertFalse(confirmation.notice?.contains(phrase) ?? true)
        XCTAssertNotNil(confirmation.notice); XCTAssertFalse(confirmation.isBusy)
    }
    func testSecretIndexRejectsWrongPlanChangedRevisionAndRevokedResponse() async throws {
        let draft = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        let confirmation = EntrustmentSecretIndexModel(), pending = try savedPlan(confirmationRequired: true)
        let wrongResults = [try savedPlan(confirmationRequired: false, id: "other-plan"),
            try savedPlan(confirmationRequired: false, revision: 4), try savedPlan(confirmationRequired: false, status: "revoked")]
        for wrong in wrongResults {
            draft.secret = phrase; draft.secretReviewed = true
            let result = await confirmation.confirm(plan: pending, draft: draft, isCurrent: { true }, submit: { _ in wrong })
            XCTAssertNil(result); XCTAssertTrue(draft.secret.isEmpty); XCTAssertNotNil(confirmation.notice)
        }
    }
    func testCancelSecretIndexConfirmationIgnoresLateResponse() async throws {
        let draft = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        let confirmation = EntrustmentSecretIndexModel(), pending = try savedPlan(confirmationRequired: true)
        let indexed = try savedPlan(confirmationRequired: false)
        var response: CheckedContinuation<GuestEntrustmentPlan, Error>?
        draft.secret = phrase; draft.secretReviewed = true
        let task = Task { await confirmation.confirm(plan: pending, draft: draft, isCurrent: { true }, submit: { _ in
            try await withCheckedThrowingContinuation { response = $0 }
        }) }
        while response == nil { await Task.yield() }
        confirmation.clear(draft: draft)
        XCTAssertFalse(confirmation.isBusy); XCTAssertTrue(draft.secret.isEmpty)
        response?.resume(returning: indexed)
        let result = await task.value
        XCTAssertNil(result); XCTAssertNil(confirmation.notice); XCTAssertTrue(draft.secret.isEmpty)
    }
    func testAccountChangeOrPlanRevocationIgnoresPendingSecretIndexResponse() async throws {
        let draft = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        let confirmation = EntrustmentSecretIndexModel(), pending = try savedPlan(confirmationRequired: true)
        let indexed = try savedPlan(confirmationRequired: false)
        var current = true
        var response: CheckedContinuation<GuestEntrustmentPlan, Error>?
        draft.secret = phrase; draft.secretReviewed = true
        let task = Task { await confirmation.confirm(plan: pending, draft: draft, isCurrent: { current }, submit: { _ in
            try await withCheckedThrowingContinuation { response = $0 }
        }) }
        while response == nil { await Task.yield() }
        current = false; response?.resume(returning: indexed)
        let result = await task.value
        XCTAssertNil(result); XCTAssertNil(confirmation.notice); XCTAssertTrue(draft.secret.isEmpty)
    }
    func testSecretIndexRequiresReviewedOriginalAndConfirmedPlan() async throws {
        let draft = EntrustmentSetupModel(recorder: SecretRecorderFixture(), speech: SecretSpeechFixture())
        let confirmation = EntrustmentSecretIndexModel(), pending = try savedPlan(confirmationRequired: true)
        var calls = 0
        draft.secret = phrase
        let unreviewed = await confirmation.confirm(plan: pending, draft: draft, isCurrent: { true }, submit: { _ in calls += 1; return pending })
        XCTAssertNil(unreviewed); XCTAssertEqual(calls, 0)
        draft.secretReviewed = true
        let revoked = try savedPlan(confirmationRequired: true, status: "revoked")
        let result = await confirmation.confirm(plan: revoked, draft: draft, isCurrent: { true }, submit: { _ in calls += 1; return revoked })
        XCTAssertNil(result); XCTAssertEqual(calls, 0)
        confirmation.clear(draft: draft); XCTAssertTrue(draft.secret.isEmpty)
    }
}

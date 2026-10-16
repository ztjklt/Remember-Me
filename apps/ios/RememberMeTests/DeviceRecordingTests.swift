import AVFoundation
import XCTest
@testable import RememberMe

@MainActor
final class DeviceRecordingTests: XCTestCase {
    private func owner(_ name: String = "qa") -> RecordingOwner {
        RecordingOwner(Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                               token: "test-only", actorID: name, subjectID: name, consentID: "grant"))
    }
    private func wav(seconds: Int, url: URL) throws {
        let rate = 16000, bytes = rate * seconds * 2
        var data = Data()
        func text(_ s: String) { data.append(Data(s.utf8)) }
        func u16(_ x: UInt16) { var x=x.littleEndian; withUnsafeBytes(of: &x) { data.append(contentsOf: $0) } }
        func u32(_ x: UInt32) { var x=x.littleEndian; withUnsafeBytes(of: &x) { data.append(contentsOf: $0) } }
        text("RIFF");u32(UInt32(bytes+36));text("WAVEfmt ");u32(16);u16(1);u16(1);u32(UInt32(rate));u32(UInt32(rate*2));u16(2);u16(16);text("data");u32(UInt32(bytes))
        data.append(Data(repeating: 0, count: bytes));try data.write(to:url)
    }
    func testInterruptedCaptureRecoversActualDurationAndKeepsOriginal() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let suite = "recording-recovery-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { try? FileManager.default.removeItem(at: root); defaults.removePersistentDomain(forName: suite) }
        let store = LocalRecordingStore(root: root)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let id = UUID().uuidString, audio = root.appendingPathComponent(id + ".wav")
        try wav(seconds: 2, url: audio)
        let draft = RecordingDraft(id: id, fileURL: audio, recordedAt: Date(), durationMS: 0,
                                   questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        try store.save(LocalRecording(draft: draft, owner: nil, status: "recording"))
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        model.recoverInterruptedRecordings()
        let restored = try XCTUnwrap(try store.load().recordings.first)
        XCTAssertEqual(restored.draft.durationMS, 2000)
        XCTAssertEqual(restored.status, "saved")
        XCTAssertTrue(FileManager.default.fileExists(atPath: audio.path))
    }
    func testLongDeviceRecordingSplitsPreservesFramesAndNeverReappearsAfterDeletion() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let subjectOwner=owner(), transfer=root.appendingPathComponent("transfer/"+owner().storageNamespace)
        try FileManager.default.createDirectory(at:transfer,withIntermediateDirectories:true)
        let original=transfer.appendingPathComponent("sdk-decoded.wav");try wav(seconds:360,url:original)
        let store=LocalRecordingStore(root:root.appendingPathComponent("archive"))
        let file=BeanDownloadedFile(device:RecordingBeanDevice(id:"bean-qa",mac:"qa-device",name:"QA",product:"D3200"),fileID:1_792_000_000,url:original,root:transfer)
        let imported=try DeviceRecordingImporter.importFile(file,owner:subjectOwner,store:store,authorization:[:])
        XCTAssertEqual(imported.records.count,2)
        XCTAssertEqual(imported.records.reduce(0) { $0 + $1.draft.durationMS },360_000)
        XCTAssertEqual(imported.records.reduce(AVAudioFramePosition(0)) { $0 + (try! AVAudioFile(forReading:$1.draft.fileURL)).length },5_760_000)
        XCTAssertTrue(imported.records.allSatisfy { $0.draft.captureSource=="WORK_3200" && $0.owner==subjectOwner })
        XCTAssertTrue(FileManager.default.fileExists(atPath:original.path))
        XCTAssertEqual(try AVAudioFile(forReading:original).length,5_760_000)
        for record in imported.records { try store.remove(record) }
        XCTAssertTrue(try store.load().recordings.isEmpty)
        XCTAssertTrue(try DeviceRecordingImporter.importFile(file,owner:subjectOwner,store:store,authorization:[:]).records.isEmpty)
        XCTAssertTrue(try store.load().recordings.isEmpty)
    }
    func testImportRejectsOtherSpacePathsAndPreservesSourceMetadataAfterRelocation() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let a=owner(), b=owner("other"), transfer=root.appendingPathComponent(a.storageNamespace)
        try FileManager.default.createDirectory(at:transfer,withIntermediateDirectories:true)
        let url=transfer.appendingPathComponent("source.wav");try wav(seconds:1,url:url)
        let store=LocalRecordingStore(root:root.appendingPathComponent("archive"))
        let file=BeanDownloadedFile(device:RecordingBeanDevice(id:"qa",mac:"qa",name:"QA",product:"D3200"),fileID:1_792_000_000,url:url,root:transfer)
        XCTAssertThrowsError(try DeviceRecordingImporter.importFile(file,owner:b,store:store,authorization:[:]))
        let result=try DeviceRecordingImporter.importFile(file,owner:a,store:store,authorization:["device_recording_consent_id":"grant-qa"])
        let stored=try XCTUnwrap(try store.load().recordings.first)
        XCTAssertEqual(stored.draft.captureMetadata?["device_recording_consent_id"],"grant-qa")
        XCTAssertEqual(store.resolved(stored.draft).captureSource,"WORK_3200")
        XCTAssertEqual(result.records.first?.id,stored.id)
    }
    func testPriorityIsClippedAcrossPartsAndOriginalAudioIsArchivedUnchanged() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let person = owner(), transfer = root.appendingPathComponent(person.storageNamespace)
        try FileManager.default.createDirectory(at: transfer, withIntermediateDirectories: true)
        let original = transfer.appendingPathComponent("source.wav"); try wav(seconds: 360, url: original)
        var file = BeanDownloadedFile(device: .init(id: "qa", mac: "qa", name: "QA", product: "D3200"),
            fileID: 1_792_000_000, url: original, root: transfer)
        file.priorityTimeline = .init(markersMS: [290_000, 320_000], isComplete: true)
        let store = LocalRecordingStore(root: root.appendingPathComponent("archive"))
        let parts = try DeviceRecordingImporter.importFile(file, owner: person, store: store, authorization: [:]).records.sorted { $0.draft.recordedAt < $1.draft.recordedAt }
        XCTAssertEqual(parts.count, 2)
        XCTAssertEqual(parts[0].draft.captureMetadata?["priority_ranges_ms"], "[[290000,300000]]")
        XCTAssertEqual(parts[1].draft.captureMetadata?["priority_ranges_ms"], "[[0,20000]]")
        for part in parts {
            XCTAssertEqual(part.draft.captureMetadata?["priority_timeline_complete"], "true")
            let ref = try XCTUnwrap(part.draft.captureMetadata?["device_original_ref"])
            XCTAssertEqual(try Data(contentsOf: store.root.appendingPathComponent("DeviceOriginals/" + ref)), try Data(contentsOf: original))
        }
    }
    func testLiveOpusThenFullFileImportsOnlyNewIdenticalPacketsAndDoesNotResurrectDeletion() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let person = owner(), transfer = root.appendingPathComponent(person.storageNamespace)
        try FileManager.default.createDirectory(at: transfer, withIntermediateDirectories: true)
        let chunk = transfer.appendingPathComponent("live.opus"), complete = transfer.appendingPathComponent("complete.opus")
        let raw = SoundcoreAudioTests.syntheticOpus
        try raw.write(to: chunk); try (raw + raw).write(to: complete)
        let store = LocalRecordingStore(root: root.appendingPathComponent("archive"))
        var file = BeanDownloadedFile(device: .init(id: "qa", mac: "qa", name: "QA", product: "D3200"),
            fileID: 1_792_000_000, url: chunk, root: transfer)
        file.priorityTimeline = .init(markersMS: [100, 300], isComplete: true)
        let first = try XCTUnwrap(DeviceRecordingImporter.importFile(file, owner: person, store: store, authorization: [:]).records.first)
        XCTAssertEqual(first.draft.durationMS, 517)
        XCTAssertEqual(first.draft.captureMetadata?["decoder_leading_trim_ms"], "2.5")
        XCTAssertEqual(try Data(contentsOf: chunk), raw)
        let full = BeanDownloadedFile(device: file.device, fileID: file.fileID, url: complete, root: transfer)
        let remainder = try DeviceRecordingImporter.importFile(full, owner: person, store: store, authorization: [:]).records
        XCTAssertEqual(remainder.count, 1)
        XCTAssertEqual(remainder[0].draft.durationMS, 520)
        XCTAssertEqual(remainder[0].draft.captureMetadata?["source_start_ms"], "520")
        XCTAssertEqual(try store.load().recordings.count, 2)
        try store.remove(first)
        XCTAssertTrue(try DeviceRecordingImporter.importFile(full, owner: person, store: store, authorization: [:]).records.isEmpty)
        XCTAssertEqual(try store.load().recordings.count, 1)
        XCTAssertEqual(try Data(contentsOf: complete), raw + raw)
    }
    func testIdenticalLiveAudioAtDifferentTimesKeepsBothOccurrencesAndDeletedAudioStaysDeleted() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let person = owner(), transfer = root.appendingPathComponent(person.storageNamespace)
        try FileManager.default.createDirectory(at: transfer, withIntermediateDirectories: true)
        let a = transfer.appendingPathComponent("a.opus"), b = transfer.appendingPathComponent("b.opus")
        let complete = transfer.appendingPathComponent("full.opus"), partial = transfer.appendingPathComponent("partial.opus")
        let raw = SoundcoreAudioTests.syntheticOpus
        try raw.write(to: a); try raw.write(to: b); try (raw + raw).write(to: complete)
        try Data(raw.dropFirst(13 * 160)).write(to: partial)
        let store = LocalRecordingStore(root: root.appendingPathComponent("archive"))
        let device = RecordingBeanDevice(id: "qa", mac: "qa", name: "QA", product: "D3200")
        let firstFile = BeanDownloadedFile(device: device, fileID: 1_792_000_000, url: a, root: transfer)
        var laterFile = BeanDownloadedFile(device: device, fileID: firstFile.fileID, url: b, root: transfer)
        laterFile.sourceOffsetMS = 520
        let first = try XCTUnwrap(DeviceRecordingImporter.importFile(firstFile, owner: person, store: store, authorization: [:]).records.first)
        let later = try XCTUnwrap(DeviceRecordingImporter.importFile(laterFile, owner: person, store: store, authorization: [:]).records.first)
        XCTAssertNotEqual(first.id, later.id)
        XCTAssertEqual(later.draft.captureMetadata?["source_start_ms"], "522")
        try store.remove(first)
        let originals = store.root.appendingPathComponent("DeviceOriginals")
        let before = try FileManager.default.contentsOfDirectory(atPath: originals.path)
        let full = BeanDownloadedFile(device: device, fileID: firstFile.fileID, url: complete, root: transfer)
        XCTAssertTrue(try DeviceRecordingImporter.importFile(full, owner: person, store: store, authorization: [:]).records.isEmpty)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: originals.path), before)
        XCTAssertEqual(try store.load().recordings.count, 1)
        var partialReplay = BeanDownloadedFile(device: device, fileID: firstFile.fileID, url: partial, root: transfer)
        partialReplay.sourceOffsetMS = 260
        XCTAssertThrowsError(try DeviceRecordingImporter.importFile(partialReplay, owner: person, store: store, authorization: [:])) {
            guard case DeviceImportFailure.requiresFullSource = $0 else { return XCTFail("Partial deletion replay must wait for its complete source") }
        }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: originals.path), before)
    }

    func testDisposableAppTransferIsRemovedAfterArchiveAndAfterDeletedFullReplay() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let person = owner("isolated-" + UUID().uuidString)
        let transfer = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DeviceTransfers/" + person.storageNamespace)
        defer { try? FileManager.default.removeItem(at: root); try? FileManager.default.removeItem(at: transfer) }
        try FileManager.default.createDirectory(at: transfer, withIntermediateDirectories: true)
        let input = transfer.appendingPathComponent("source.opus")
        let raw = SoundcoreAudioTests.syntheticOpus; try raw.write(to: input)
        let store = LocalRecordingStore(root: root.appendingPathComponent("archive"))
        let device = RecordingBeanDevice(id: "qa", mac: "qa", name: "QA", product: "D3200")
        let file = BeanDownloadedFile(device: device, fileID: 1_792_000_000, url: input, root: transfer)
        let first = try XCTUnwrap(DeviceRecordingImporter.importFile(file, owner: person, store: store, authorization: [:]).records.first)
        XCTAssertFalse(FileManager.default.fileExists(atPath: input.path))
        try store.remove(first)
        let partial = transfer.appendingPathComponent("partial-replay.opus")
        try Data(raw.dropFirst(13 * 160)).write(to: partial)
        var partialFile = BeanDownloadedFile(device: device, fileID: file.fileID, url: partial, root: transfer)
        partialFile.sourceOffsetMS = 260
        XCTAssertThrowsError(try DeviceRecordingImporter.importFile(partialFile, owner: person, store: store, authorization: [:]))
        XCTAssertFalse(FileManager.default.fileExists(atPath: partial.path))
        let replay = transfer.appendingPathComponent("replay.opus"); try raw.write(to: replay)
        let repeatFile = BeanDownloadedFile(device: device, fileID: file.fileID, url: replay, root: transfer)
        XCTAssertTrue(try DeviceRecordingImporter.importFile(repeatFile, owner: person, store: store, authorization: [:]).records.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: replay.path))
        XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: store.root.appendingPathComponent("DeviceOriginals").path).isEmpty)
    }
}

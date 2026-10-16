import Foundation
import CryptoKit

struct RecordingOwner: Codable, Equatable, Sendable {
    let subjectID: String
    let actorID: String
    let server: String
    let fingerprint: String

    var storageNamespace: String {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        return SHA256.hash(data: try! encoder.encode(self)).map { String(format: "%02x", $0) }.joined()
    }
    init(_ pairing: Pairing) {
        subjectID = pairing.subjectID
        actorID = pairing.actorID
        server = pairing.baseURL
        fingerprint = pairing.fingerprint
    }
}

struct LocalRecording: Codable, Identifiable, Sendable {
    var draft: RecordingDraft
    var owner: RecordingOwner?
    var episodeID: String?
    var status = "saved"
    var machineTranscript: String?
    var reviewDraft: String?
    var reviewedTranscript: String?
    var reviewedAt: Date?
    var deviceImportKey: String?
    // Absent in older sidecars: upgrading never uploads old local recordings.
    var automaticProcessing: Bool?
    var automaticASRPolicy: String?
    var supplementDraft: String?
    var automaticCorrection: TranscriptCorrection?
    var automaticRetryAt: Date?
    var automaticAttempts: Int?
    var automaticError: String?
    var cloudMachineTranscript: String?
    var cumulativeAnalysis: CaptureAnalysisStatus?
    var id: String { draft.id }

    func isVisible(to pairing: Pairing?) -> Bool {
        owner == nil || pairing.map { owner == RecordingOwner($0) } == true
    }
}

/// One atomic sidecar per recording; original audio and machine text stay intact.
struct LocalRecordingStore: Sendable {
    let root: URL

    init(root: URL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Recordings", isDirectory: true)) {
        self.root = root
    }

    func resolved(_ draft: RecordingDraft) -> RecordingDraft {
        // iOS can relocate the entire container during an update. Resolve only
        // the existing filename, preserving identity and capture provenance.
        let local = root.appendingPathComponent(draft.fileURL.lastPathComponent)
        let url = FileManager.default.fileExists(atPath: local.path) ? local : draft.fileURL
        var result = RecordingDraft(id: draft.id, fileURL: url, recordedAt: draft.recordedAt,
                              durationMS: draft.durationMS, questionID: draft.questionID,
                              calibrationID: draft.calibrationID, consentConfirmedAt: draft.consentConfirmedAt)
        result.captureSource = draft.captureSource; result.captureMetadata = draft.captureMetadata
        return result
    }

    func load() throws -> (recordings: [LocalRecording], unreadableCount: Int) {
        guard FileManager.default.fileExists(atPath: root.path) else { return ([], 0) }
        var records: [LocalRecording] = []
        var unreadable = 0
        for url in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
            .filter({ $0.lastPathComponent.hasSuffix(".recording.json") }) {
            do {
                var record = try JSONDecoder().decode(LocalRecording.self, from: Data(contentsOf: url))
                record.draft = resolved(record.draft)
                records.append(record)
            } catch { unreadable += 1 }
        }
        return (records.sorted { $0.draft.recordedAt > $1.draft.recordedAt }, unreadable)
    }

    func remove(_ record: LocalRecording) throws {
        guard UUID(uuidString: record.id) != nil,
              ["m4a", "wav", "aac", "caf", "mp3"].contains(record.draft.fileURL.pathExtension.lowercased()),
              record.draft.fileURL.deletingPathExtension().lastPathComponent == record.id else {
            throw CocoaError(.fileWriteInvalidFileName)
        }
        // Never follow an old container path or delete another recording's file.
        let audio = root.appendingPathComponent(record.draft.fileURL.lastPathComponent)
        let metadata = root.appendingPathComponent(record.id + ".recording.json")
        if FileManager.default.fileExists(atPath: audio.path) { try FileManager.default.removeItem(at: audio) }
        // A wearable import keeps the untouched codec original as well as its
        // playable WAV. Explicit deletion must not leave that copy behind.
        // Other parts retain their own playable originals if a shared raw file
        // is removed. Content-only coverage receipts still prevent reimport.
        if let ref = record.draft.captureMetadata?["device_original_ref"],
           ref.range(of: "^[a-f0-9]{64}\\.[a-z0-9]{1,8}$", options: .regularExpression) != nil {
            let original = root.appendingPathComponent("DeviceOriginals/" + ref)
            if FileManager.default.fileExists(atPath: original.path) { try FileManager.default.removeItem(at: original) }
        }
        if let owner = record.owner, let ref = record.draft.captureMetadata?["device_transfer_ref"],
           !ref.isEmpty, !ref.hasPrefix("/"), !ref.split(separator: "/").contains("..") {
            let transfers = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("DeviceTransfers/" + owner.storageNamespace, isDirectory: true)
                .resolvingSymlinksInPath().standardizedFileURL
            let original = transfers.appendingPathComponent(ref).resolvingSymlinksInPath().standardizedFileURL
            if original.path.hasPrefix(transfers.path + "/"), FileManager.default.fileExists(atPath: original.path) {
                try FileManager.default.removeItem(at: original)
            }
        }
        // Keep the sidecar until every private copy is removed, so a failed
        // cleanup remains addressable by the existing retry action.
        if FileManager.default.fileExists(atPath: metadata.path) { try FileManager.default.removeItem(at: metadata) }
    }

    func save(_ record: LocalRecording) throws {
        guard UUID(uuidString: record.id) != nil else { throw CocoaError(.fileWriteInvalidFileName) }
        var directory = root
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        let url = root.appendingPathComponent(record.id + ".recording.json")
        // Apply protection when the atomic temporary file is created. Setting it
        // only after rename can prevent a locked-screen checkpoint from writing
        // at all, or briefly publish a sidecar with the wrong inherited class.
        let protection: Data.WritingOptions = record.deviceImportKey == nil && record.status != "recording"
            ? .completeFileProtection : .completeFileProtectionUntilFirstUserAuthentication
        try JSONEncoder().encode(record).write(to: url, options: [.atomic, protection])
    }
}

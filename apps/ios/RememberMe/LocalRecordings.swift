import Foundation

struct RecordingOwner: Codable, Equatable {
    let subjectID: String
    let actorID: String
    let server: String
    let fingerprint: String

    init(_ pairing: Pairing) {
        subjectID = pairing.subjectID
        actorID = pairing.actorID
        server = pairing.baseURL
        fingerprint = pairing.fingerprint
    }
}

struct LocalRecording: Codable, Identifiable {
    var draft: RecordingDraft
    var owner: RecordingOwner?
    var episodeID: String?
    var status = "saved"
    var machineTranscript: String?
    var reviewDraft: String?
    var reviewedTranscript: String?
    var reviewedAt: Date?
    var id: String { draft.id }

    func isVisible(to pairing: Pairing?) -> Bool {
        owner == nil || pairing.map { owner == RecordingOwner($0) } == true
    }
}

/// One atomic sidecar per recording; original audio and machine text stay intact.
struct LocalRecordingStore {
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
        return RecordingDraft(id: draft.id, fileURL: url, recordedAt: draft.recordedAt,
                              durationMS: draft.durationMS, questionID: draft.questionID,
                              calibrationID: draft.calibrationID, consentConfirmedAt: draft.consentConfirmedAt)
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

    func save(_ record: LocalRecording) throws {
        guard UUID(uuidString: record.id) != nil else { throw CocoaError(.fileWriteInvalidFileName) }
        var directory = root
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        let url = root.appendingPathComponent(record.id + ".recording.json")
        try JSONEncoder().encode(record).write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: url.path)
    }
}

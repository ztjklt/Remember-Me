import CryptoKit
import Foundation

struct DevicePacketCoverage: Codable, Sendable {
    let startMS: Int
    let endMS: Int
    let originalRef: String
    var rawSHA256: String? = nil

    static func ledgerURL(store: LocalRecordingStore, device: RecordingBeanDevice, owner: RecordingOwner, fileID: Int32) -> URL {
        let key = owner.storageNamespace + ":" + device.mac + ":" + String(fileID)
        let digest = SHA256.hash(data: Data(key.utf8)).map { String(format: "%02x", $0) }.joined()
        return store.root.appendingPathComponent("DeviceImports/coverage-" + digest + ".json")
    }

    /// Only byte-identical packet ranges may suppress a later complete-file
    /// import. Reused device timestamps or changed audio cannot hide new audio.
    static func uncovered(input: URL, startMS: Int, endMS: Int,
                          previous: [DevicePacketCoverage], originals: URL) throws -> [WearablePriorityRange] {
        var covered: [WearablePriorityRange] = []
        for item in previous {
            let left = max(startMS, item.startMS), right = min(endMS, item.endMS)
            guard left < right, left % 20 == 0, right % 20 == 0,
                  item.startMS >= 0, item.startMS % 20 == 0,
                  item.originalRef == URL(fileURLWithPath: item.originalRef).lastPathComponent,
                  item.originalRef.hasSuffix(".opus") else { continue }
            let archived = originals.appendingPathComponent(item.originalRef)
            let count = (right - left) / 20 * 160
            let a = try digest(input, offset: (left - startMS) / 20 * 160, count: count)
            let currentHash = a.map { String(format: "%02x", $0) }.joined()
            if left == item.startMS, right == item.endMS, let expected = item.rawSHA256 {
                if currentHash == expected { covered.append(.init(startMS: left, endMS: right)) }
            } else if FileManager.default.fileExists(atPath: archived.path) {
                let b = try digest(archived, offset: (left - item.startMS) / 20 * 160, count: count)
                if a == b { covered.append(.init(startMS: left, endMS: right)) }
            } else {
                // The original may have been explicitly erased. A partial
                // replay cannot prove whether it is changed audio; defer to a
                // complete-file comparison instead of resurrecting a deletion.
                throw DeviceImportFailure.requiresFullSource
            }
        }
        var cursor = startMS, remaining: [WearablePriorityRange] = []
        for item in covered.sorted(by: { $0.startMS < $1.startMS }) {
            if cursor < item.startMS { remaining.append(.init(startMS: cursor, endMS: item.startMS)) }
            cursor = max(cursor, item.endMS)
        }
        if cursor < endMS { remaining.append(.init(startMS: cursor, endMS: endMS)) }
        return remaining
    }

    private static func digest(_ url: URL, offset: Int, count: Int) throws -> SHA256.Digest {
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        try handle.seek(toOffset: UInt64(offset))
        var hasher = SHA256(), remaining = count
        while remaining > 0 {
            let bytes = try handle.read(upToCount: min(remaining, 1024 * 1024)) ?? Data()
            guard !bytes.isEmpty else { throw DeviceImportFailure.changedFile }
            hasher.update(data: bytes); remaining -= bytes.count
        }
        return hasher.finalize()
    }
}

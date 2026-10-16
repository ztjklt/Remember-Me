import AVFoundation
import CryptoKit
import Foundation

struct ImportedDeviceAudio: Sendable {
    let records: [LocalRecording]
    let receiptURL: URL
}
enum DeviceImportFailure: Error { case invalidFile, changedFile, requiresFullSource }

/// Imports only a complete SDK decode. Long files become lossless PCM parts;
/// the physical device original is never deleted by this app.
enum DeviceRecordingImporter {
    static func importFile(_ download: BeanDownloadedFile, owner: RecordingOwner,
                           store: LocalRecordingStore, authorization: [String: String]) throws -> ImportedDeviceAudio {
        let input = download.url.resolvingSymlinksInPath().standardizedFileURL
        let allowed = download.root.resolvingSymlinksInPath().standardizedFileURL.path + "/"
        guard download.root.lastPathComponent == owner.storageNamespace, input.path.hasPrefix(allowed), !input.hasDirectoryPath else { throw DeviceImportFailure.invalidFile }
        let attributes = try FileManager.default.attributesOfItem(atPath: input.path)
        guard let size = attributes[.size] as? NSNumber, size.int64Value > 0, size.int64Value <= 2_000_000_000 else { throw DeviceImportFailure.invalidFile }
        let handle = try FileHandle(forReadingFrom: input); defer { try? handle.close() }
        var hasher = SHA256()
        while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty { hasher.update(data: chunk) }
        let checksum = hasher.finalize().map { String(format: "%02x", $0) }.joined()
        let identity = owner.storageNamespace + ":" + download.device.mac + ":" + String(download.fileID) + ":" + checksum
            + (download.sourceOffsetMS == 0 ? "" : ":" + String(download.sourceOffsetMS))
        let importKey = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
        let receipt = store.root.appendingPathComponent("DeviceImports/" + importKey + ".json")
        // Tombstone-like receipts survive list deletion, preventing an automatic
        // sync from recreating a recording the user already deleted.
        if FileManager.default.fileExists(atPath: receipt.path) {
            let ids = try JSONDecoder().decode([String].self, from: Data(contentsOf: receipt))
            guard !ids.isEmpty, ids.allSatisfy({ UUID(uuidString: $0) != nil }) else { throw DeviceImportFailure.invalidFile }
            let current = try FileManager.default.attributesOfItem(atPath: input.path)
            guard (current[.size] as? NSNumber) == size,
                  (current[.modificationDate] as? Date) == (attributes[.modificationDate] as? Date) else { throw DeviceImportFailure.changedFile }
            try removeRedundantTransfer(input, download: download, owner: owner)
            return ImportedDeviceAudio(records: [], receiptURL: receipt)
        }
        let staging = store.root.appendingPathComponent("DeviceImports/staging-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        defer { try? FileManager.default.removeItem(at: staging) }
        let rawOpus = DecodedSoundcoreAudio.isRawOpus(input)
        let decoded = try DecodedSoundcoreAudio.decode(url: input, stagingRoot: staging)
        let audio = try AVAudioFile(forReading: decoded)
        guard audio.length > 0, audio.processingFormat.sampleRate > 0, audio.processingFormat.channelCount > 0,
              audio.processingFormat.channelCount <= 8 else { throw DeviceImportFailure.invalidFile }
        let rate = audio.processingFormat.sampleRate, channels = audio.processingFormat.channelCount
        let depth = min(32, max(16, (audio.fileFormat.settings[AVLinearPCMBitDepthKey] as? Int) ?? 16))
        let framesPerPart = max(1, min(AVAudioFramePosition(rate * 300), AVAudioFramePosition(12 * 1024 * 1024 / Int(channels) / (depth / 8))))
        let buffer = AVAudioPCMBuffer(pcmFormat: audio.processingFormat, frameCapacity: 65536)!
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: rate,
            AVNumberOfChannelsKey: channels, AVLinearPCMBitDepthKey: depth,
            AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
        let trimMS = rawOpus ? DecodedSoundcoreAudio.leadingTrimMilliseconds : 0
        let originalDuration = rawOpus ? Int(size.int64Value / 160) * 20 : Int((Double(audio.length) / rate * 1000).rounded())
        guard download.sourceOffsetMS >= 0 else { throw DeviceImportFailure.invalidFile }
        let inputStart = download.sourceOffsetMS, inputEnd = inputStart + originalDuration
        let fullDuration = max(inputEnd, download.sourceDurationMS ?? inputEnd)
        let timeline = download.priorityTimeline ?? WearablePriorityTimeline()
        let originals = store.root.appendingPathComponent("DeviceOriginals", isDirectory: true)
        try FileManager.default.createDirectory(at: originals, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        let coverageURL = DevicePacketCoverage.ledgerURL(store: store, device: download.device, owner: owner, fileID: download.fileID)
        var coverage = FileManager.default.fileExists(atPath: coverageURL.path)
            ? try JSONDecoder().decode([DevicePacketCoverage].self, from: Data(contentsOf: coverageURL)) : []
        let windows: [WearablePriorityRange]
        if rawOpus {
            do { windows = try DevicePacketCoverage.uncovered(input: input, startMS: inputStart, endMS: inputEnd, previous: coverage, originals: originals) }
            catch DeviceImportFailure.requiresFullSource {
                try removeRedundantTransfer(input, download: download, owner: owner)
                throw DeviceImportFailure.requiresFullSource
            }
        } else { windows = [WearablePriorityRange(startMS: inputStart, endMS: inputEnd)] }
        // A completed offline download may contain the exact packets already
        // imported while recording. Do not recreate a hidden full raw copy of
        // previously deleted ranges merely to discover they are already covered.
        if windows.isEmpty {
            let current = try FileManager.default.attributesOfItem(atPath: input.path)
            guard (current[.size] as? NSNumber) == size,
                  (current[.modificationDate] as? Date) == (attributes[.modificationDate] as? Date) else { throw DeviceImportFailure.changedFile }
            try removeRedundantTransfer(input, download: download, owner: owner)
            return ImportedDeviceAudio(records: [], receiptURL: receipt)
        }
        var records: [LocalRecording] = [], index = 0
        var newCoverage: [DevicePacketCoverage] = []
        let captured = Date(timeIntervalSince1970: Double(UInt32(bitPattern: download.fileID)))
        for window in windows {
          let windowKey = SHA256.hash(data: Data((importKey + ":" + String(window.startMS) + ":" + String(window.endMS)).utf8)).map { String(format: "%02x", $0) }.joined()
          let originalRef = windowKey + "." + (rawOpus ? "opus" : input.pathExtension.lowercased())
          let archived = originals.appendingPathComponent(originalRef)
          if rawOpus {
              let digest = try archivePackets(input, byteOffset: (window.startMS - inputStart) / 20 * 160,
                  byteCount: (window.endMS - window.startMS) / 20 * 160, destination: archived)
              newCoverage.append(.init(startMS: window.startMS, endMS: window.endMS, originalRef: originalRef, rawSHA256: digest))
          } else if !FileManager.default.fileExists(atPath: archived.path) {
              try FileManager.default.copyItem(at: input, to: archived)
              try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: archived.path)
          }
          let windowStart = max(0, AVAudioFramePosition(((Double(window.startMS - inputStart) - trimMS) * rate / 1000).rounded(.up)))
          let windowEnd = min(audio.length, AVAudioFramePosition(((Double(window.endMS - inputStart) - trimMS) * rate / 1000).rounded(.down)))
          audio.framePosition = windowStart
          while audio.framePosition < windowEnd {
            let start = audio.framePosition, frames = min(framesPerPart, windowEnd - start)
            let hash = SHA256.hash(data: Data((importKey + ":" + String(start)).utf8)).map { String(format: "%02x", $0) }.joined()
            let hex = Array(hash.prefix(32)); let raw = [String(hex[0..<8]), String(hex[8..<12]), String(hex[12..<16]), String(hex[16..<20]), String(hex[20..<32])].joined(separator: "-")
            let id = UUID(uuidString: raw)!.uuidString
            let part = staging.appendingPathComponent(id + ".wav")
            do {
                let output = try AVAudioFile(forWriting: part, settings: settings,
                    commonFormat: audio.processingFormat.commonFormat, interleaved: audio.processingFormat.isInterleaved)
                var remaining = frames
                while remaining > 0 {
                    try audio.read(into: buffer, frameCount: AVAudioFrameCount(min(remaining, AVAudioFramePosition(buffer.frameCapacity))))
                    guard buffer.frameLength > 0 else { throw DeviceImportFailure.invalidFile }
                    try output.write(from: buffer); remaining -= AVAudioFramePosition(buffer.frameLength)
                }
            }
            let sourceStart = inputStart + Int((trimMS + Double(start) / rate * 1000).rounded(.down))
            let duration = Int(Double(frames) / rate * 1000)
            guard duration > 0 else { throw DeviceImportFailure.invalidFile }
            var draft = RecordingDraft(id: id, fileURL: store.root.appendingPathComponent(id + ".wav"),
                recordedAt: captured.addingTimeInterval(Double(inputStart) / 1000 + trimMS / 1000 + Double(start) / rate), durationMS: duration,
                questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
            draft.captureSource = "WORK_3200"
            let priority = try timeline.metadata(durationMS: fullDuration, startMS: sourceStart, endMS: sourceStart + duration)
            draft.captureMetadata = authorization.merging(priority) { _, new in new }.merging(["capture_mode": "wearable_continuous", "device_product": download.device.product,
                "device_source_checksum": checksum, "device_file_id": String(download.fileID), "device_part_index": String(index),
                "source_start_ms": String(sourceStart), "source_end_ms": String(sourceStart + duration),
                "source_packet_start_ms": String(inputStart), "source_packet_end_ms": String(inputEnd),
                "decoder_leading_trim_ms": String(trimMS), "device_original_ref": originalRef,
                "device_transfer_ref": String(input.path.dropFirst(allowed.count))]) { _, new in new }
            var record = LocalRecording(draft: draft, owner: owner); record.deviceImportKey = importKey
            records.append(record); index += 1
          }
        }
        let after = try FileManager.default.attributesOfItem(atPath: input.path)
        guard (after[.size] as? NSNumber) == size, (after[.modificationDate] as? Date) == (attributes[.modificationDate] as? Date) else { throw DeviceImportFailure.changedFile }
        // An interrupted import resumes using deterministic part ids. Existing
        // uploaded metadata must never be overwritten with a fresh local draft.
        let existing = Set(try store.load().recordings.map(\.id))
        for record in records where !existing.contains(record.id) {
            let source = staging.appendingPathComponent(record.draft.fileURL.lastPathComponent)
            if FileManager.default.fileExists(atPath: record.draft.fileURL.path) { try FileManager.default.removeItem(at: record.draft.fileURL) }
            try FileManager.default.moveItem(at: source, to: record.draft.fileURL)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: record.draft.fileURL.path)
            try store.save(record)
        }
        try FileManager.default.createDirectory(at: receipt.deletingLastPathComponent(), withIntermediateDirectories: true)
        if rawOpus {
            coverage.append(contentsOf: newCoverage)
            try JSONEncoder().encode(coverage).write(to: coverageURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        }
        try JSONEncoder().encode(records.map(\.id)).write(to: receipt, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        // SDK transfer files are disposable after the unchanged packet originals
        // and playable parts are durable. Hardware originals are untouched.
        try removeRedundantTransfer(input, download: download, owner: owner)
        return ImportedDeviceAudio(records: try store.load().recordings.filter { $0.deviceImportKey == importKey }, receiptURL: receipt)
    }

    private static func removeRedundantTransfer(_ input: URL, download: BeanDownloadedFile, owner: RecordingOwner) throws {
        let systemRoot = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DeviceTransfers/" + owner.storageNamespace, isDirectory: true)
            .resolvingSymlinksInPath().standardizedFileURL
        guard download.root.resolvingSymlinksInPath().standardizedFileURL.path == systemRoot.path,
              input.path.hasPrefix(systemRoot.path + "/") else { return }
        if FileManager.default.fileExists(atPath: input.path) { try FileManager.default.removeItem(at: input) }
    }

    private static func archivePackets(_ input: URL, byteOffset: Int, byteCount: Int, destination: URL) throws -> String {
        let reader = try FileHandle(forReadingFrom: input); defer { try? reader.close() }
        try reader.seek(toOffset: UInt64(byteOffset))
        let temporary = destination.deletingLastPathComponent().appendingPathComponent("archive-" + UUID().uuidString)
        guard FileManager.default.createFile(atPath: temporary.path, contents: nil,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]) else { throw DeviceImportFailure.invalidFile }
        defer { try? FileManager.default.removeItem(at: temporary) }
        let writer = try FileHandle(forWritingTo: temporary)
        var remaining = byteCount, hasher = SHA256()
        do {
            while remaining > 0 {
                let bytes = try reader.read(upToCount: min(remaining, 1024 * 1024)) ?? Data()
                guard !bytes.isEmpty else { throw DeviceImportFailure.changedFile }
                hasher.update(data: bytes); try writer.write(contentsOf: bytes); remaining -= bytes.count
            }
            try writer.close()
        } catch { try? writer.close(); throw error }
        if FileManager.default.fileExists(atPath: destination.path) { try FileManager.default.removeItem(at: destination) }
        try FileManager.default.moveItem(at: temporary, to: destination)
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

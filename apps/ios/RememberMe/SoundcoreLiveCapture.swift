import Foundation

struct SoundcoreLiveChunk: Sendable {
    let fileID: Int32
    let url: URL
    let sourceStartMS: Int
    let sourceEndMS: Int
    let timelineComplete: Bool
}

enum SoundcoreLiveFailure: Error { case invalidPacket }

/// Writes the documented 20 ms / 160-byte OPUS packets without changing them.
/// A gap closes the contiguous piece; it never inserts invented silence.
final class SoundcoreLiveCapture {
    private let root: URL
    private let framesPerChunk: Int
    private var fileID: Int32?
    private var firstSequence = 0
    private var lastSequence: Int?
    private var startedAtZero = false
    private var completeTimeline = false
    private var count = 0
    private var handle: FileHandle?
    private var currentURL: URL?
    var currentFileID: Int32? { fileID }

    init(root: URL, millisecondsPerChunk: Int = 60_000) {
        self.root = root.appendingPathComponent("LiveAudio", isDirectory: true)
        self.framesPerChunk = max(1, millisecondsPerChunk / 20)
    }

    func append(fileID nextID: Int32, sequence: Int, isAppendPreAudio: Bool, data: Data) throws -> [SoundcoreLiveChunk] {
        guard nextID >= 0, (0...4_320_000).contains(sequence), data.count == 160 else {
            completeTimeline = false
            throw SoundcoreLiveFailure.invalidPacket
        }
        var sealed: [SoundcoreLiveChunk] = []
        if fileID != nextID {
            if let previous = try finish() { sealed.append(previous) }
            fileID = nextID; lastSequence = nil
            startedAtZero = sequence == 0 && !isAppendPreAudio
            completeTimeline = startedAtZero
        }
        if let lastSequence, sequence <= lastSequence { return sealed }
        if let lastSequence, sequence != lastSequence + 1 {
            if let previous = try seal() { sealed.append(previous) }
            completeTimeline = false
        }
        if isAppendPreAudio { completeTimeline = false }
        if handle == nil {
            firstSequence = sequence
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true,
                attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
            // Each piece is immutable after closing. Reconnecting cannot
            // overwrite an original already used by an import receipt.
            let url = root.appendingPathComponent("\(nextID)-\(sequence)-\(UUID().uuidString).opus")
            guard FileManager.default.createFile(atPath: url.path, contents: nil,
                attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]) else {
                throw CocoaError(.fileWriteUnknown)
            }
            currentURL = url; handle = try FileHandle(forWritingTo: url)
        }
        try handle?.write(contentsOf: data)
        lastSequence = sequence; count += 1
        if count >= framesPerChunk, let piece = try seal() { sealed.append(piece) }
        return sealed
    }

    func finish() throws -> SoundcoreLiveChunk? {
        let piece = try seal()
        fileID = nil; lastSequence = nil; startedAtZero = false; completeTimeline = false
        return piece
    }

    private func seal() throws -> SoundcoreLiveChunk? {
        guard let handle, let url = currentURL, let fileID, count > 0 else { return nil }
        try handle.synchronize(); try handle.close()
        self.handle = nil; currentURL = nil
        let piece = SoundcoreLiveChunk(fileID: fileID, url: url,
            sourceStartMS: firstSequence * 20, sourceEndMS: (firstSequence + count) * 20,
            timelineComplete: completeTimeline)
        count = 0
        return piece
    }

    deinit { try? handle?.close() }
}

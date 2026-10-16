import AVFoundation
import XCTest
@testable import RememberMe

@MainActor
final class SoundcoreAudioTests: XCTestCase {
    func testHeaderlessOpusDecodesWithAnExplicitFixedOriginTrimAndPreservesOriginal() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let raw = root.appendingPathComponent("recording.opus")
        try Self.syntheticOpus.write(to: raw)
        XCTAssertTrue(DecodedSoundcoreAudio.isRawOpus(raw))
        let wav = try DecodedSoundcoreAudio.decode(url: raw, stagingRoot: root.appendingPathComponent("decoded"))
        XCTAssertNotEqual(raw, wav)
        XCTAssertEqual(try Data(contentsOf: raw), Self.syntheticOpus)
        let audio = try AVAudioFile(forReading: wav)
        XCTAssertEqual(audio.length, 26 * 320 - 40)
        XCTAssertEqual(audio.processingFormat.sampleRate, 16_000)
        XCTAssertEqual(audio.processingFormat.channelCount, 2)
        XCTAssertEqual(DecodedSoundcoreAudio.leadingTrimMilliseconds, 2.5)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: audio.processingFormat, frameCapacity: 4096))
        try audio.read(into: buffer)
        let samples = try XCTUnwrap(buffer.floatChannelData)
        XCTAssertGreaterThan((0..<Int(buffer.frameLength)).map { abs(samples[0][$0]) }.max() ?? 0, 0.01)
        XCTAssertEqual(try DecodedSoundcoreAudio.decode(url: wav, stagingRoot: root), wav)
    }

    func testIncompleteRawPacketFailsWithoutChangingOriginalOrLeavingAWav() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let raw = root.appendingPathComponent("partial.opus")
        let partial = Self.syntheticOpus.dropLast()
        try partial.write(to: raw)
        XCTAssertThrowsError(try DecodedSoundcoreAudio.decode(url: raw, stagingRoot: root)) {
            XCTAssertEqual($0 as? SoundcoreAudioDecodeFailure, .incompletePacket)
        }
        XCTAssertEqual(try Data(contentsOf: raw), Data(partial))
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), ["partial.opus"])
    }

    func testIndependentChunksKeepOneFixedTrimPerChunkWithoutPerPacketDrift() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        // Decode multiple independently timed packet runs, including one twice
        // as long. Trim stays exactly 40 frames, never a proportional rescale.
        for multiplier in [1, 2, 3] {
            let raw = root.appendingPathComponent("chunk-\(multiplier).opus")
            var data = Data()
            for _ in 0..<multiplier { data.append(Self.syntheticOpus) }
            try data.write(to: raw)
            let wav = try DecodedSoundcoreAudio.decode(url: raw, stagingRoot: root)
            let audio = try AVAudioFile(forReading: wav)
            XCTAssertEqual(audio.length, Int64(multiplier * 26 * 320) - 40)
            let durationMS = Double(audio.length) / audio.processingFormat.sampleRate * 1000
            XCTAssertEqual(durationMS + DecodedSoundcoreAudio.leadingTrimMilliseconds,
                Double(multiplier * 26 * 20), accuracy: 0.000_001)
        }
    }

    // Synthetic 440 Hz sine only; no real person's voice. Generated with:
    // ffmpeg -f lavfi -i sine=frequency=440:duration=0.5:sample_rate=16000
    //   -ac 2 -c:a libopus -b:a 64k -vbr off -frame_duration 20
    //   -application voip sample.ogg
    // Strip Ogg pages and the OpusHead/OpusTags packets, retaining 26 sequential
    // 160-byte packets. App decoding itself has no ffmpeg/libopus dependency.
    static let syntheticOpus = Data(base64Encoded: """
        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
        """, options: .ignoreUnknownCharacters)!
}

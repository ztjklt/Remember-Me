import AVFoundation
import AudioToolbox
import Foundation

enum SoundcoreAudioDecodeFailure: Error, Equatable {
    case unsupportedFormat, incompletePacket, decoderUnavailable, invalidPacket, unexpectedTimeline
}

/// The public D3200 SDK writes decrypted, headerless Opus: 160-byte packets,
/// 20 ms each, 16 kHz, stereo. Its "decode completed" callback does not mean PCM.
/// Decode into a disposable WAV while retaining the exact original file.
enum DecodedSoundcoreAudio {
    static let packetBytes = 160
    static let packetMilliseconds = 20
    static let sampleRate: Double = 16_000
    static let framesPerPacket: AVAudioFrameCount = 320

    // The system Opus decoder trims 40 leading frames even with primeMethod
    // .none. Every conversion verifies this exact count. Keep source positions
    // on the original packet clock and shift the decoded origin by 2.5 ms;
    // never scale markers or accumulate this trim across independently timed
    // chunks. No missing packets are replaced with silence or repeated audio.
    static let leadingTrimFrames: AVAudioFramePosition = 40
    static let leadingTrimMilliseconds: Double = 2.5

    static func isRawOpus(_ url: URL) -> Bool {
        guard ["opus", "raw"].contains(url.pathExtension.lowercased()) else { return false }
        return (try? AVAudioFile(forReading: url)) == nil
    }

    /// Already readable audio is returned unchanged. Only the documented raw
    /// SDK format is decoded; partial packets and codec failures are explicit.
    static func decode(url: URL, stagingRoot: URL) throws -> URL {
        if let audio = try? AVAudioFile(forReading: url), audio.length > 0 { return url }
        guard isRawOpus(url) else { throw SoundcoreAudioDecodeFailure.unsupportedFormat }
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        let byteCount = (attributes[.size] as? NSNumber)?.int64Value ?? 0
        guard byteCount > 0, byteCount <= 512 * 1024 * 1024 else {
            throw SoundcoreAudioDecodeFailure.unsupportedFormat
        }
        guard byteCount % Int64(packetBytes) == 0 else { throw SoundcoreAudioDecodeFailure.incompletePacket }

        var description = AudioStreamBasicDescription(mSampleRate: sampleRate,
            mFormatID: kAudioFormatOpus, mFormatFlags: 0, mBytesPerPacket: 0,
            mFramesPerPacket: framesPerPacket, mBytesPerFrame: 0,
            mChannelsPerFrame: 2, mBitsPerChannel: 0, mReserved: 0)
        guard let compressedFormat = AVAudioFormat(streamDescription: &description),
              let pcmFormat = AVAudioFormat(commonFormat: .pcmFormatInt16,
                  sampleRate: sampleRate, channels: 2, interleaved: true),
              let converter = AVAudioConverter(from: compressedFormat, to: pcmFormat),
              let output = AVAudioPCMBuffer(pcmFormat: pcmFormat, frameCapacity: 4096) else {
            throw SoundcoreAudioDecodeFailure.decoderUnavailable
        }
        converter.primeMethod = .none
        let input = AVAudioCompressedBuffer(format: compressedFormat, packetCapacity: 1,
            maximumPacketSize: packetBytes)
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        try FileManager.default.createDirectory(at: stagingRoot, withIntermediateDirectories: true)
        let destination = stagingRoot.appendingPathComponent("soundcore-" + UUID().uuidString + ".wav")
        var succeeded = false
        defer { if !succeeded { try? FileManager.default.removeItem(at: destination) } }
        var consumed: Int64 = 0
        var written: AVAudioFramePosition = 0
        var readFailure: Error?
        var stalled = 0
        do {
            let writer = try AVAudioFile(forWriting: destination, settings: pcmFormat.settings,
                commonFormat: .pcmFormatInt16, interleaved: true)
            while true {
                var conversionError: NSError?
                let before = consumed
                let status = converter.convert(to: output, error: &conversionError) { _, state in
                    guard readFailure == nil, consumed < byteCount else {
                        state.pointee = .endOfStream; return nil
                    }
                    do {
                        let packet = try handle.read(upToCount: packetBytes) ?? Data()
                        guard packet.count == packetBytes else { throw SoundcoreAudioDecodeFailure.incompletePacket }
                        packet.withUnsafeBytes { bytes in
                            input.data.copyMemory(from: bytes.baseAddress!, byteCount: packetBytes)
                        }
                        input.byteLength = UInt32(packetBytes); input.packetCount = 1
                        input.packetDescriptions?[0] = AudioStreamPacketDescription(mStartOffset: 0,
                            mVariableFramesInPacket: framesPerPacket, mDataByteSize: UInt32(packetBytes))
                        consumed += Int64(packetBytes)
                        state.pointee = .haveData; return input
                    } catch {
                        readFailure = error; state.pointee = .endOfStream; return nil
                    }
                }
                if let readFailure { throw readFailure }
                guard conversionError == nil, status != .error else { throw SoundcoreAudioDecodeFailure.invalidPacket }
                if output.frameLength > 0 {
                    try writer.write(from: output)
                    written += AVAudioFramePosition(output.frameLength)
                }
                if status == .endOfStream { break }
                stalled = consumed == before && output.frameLength == 0 ? stalled + 1 : 0
                guard stalled < 3 else { throw SoundcoreAudioDecodeFailure.invalidPacket }
            }
        }
        let expectedFrames = AVAudioFramePosition(byteCount / Int64(packetBytes)) * AVAudioFramePosition(framesPerPacket)
        guard consumed == byteCount, written == expectedFrames - leadingTrimFrames else {
            throw SoundcoreAudioDecodeFailure.unexpectedTimeline
        }
        let after = try FileManager.default.attributesOfItem(atPath: url.path)
        guard (after[.size] as? NSNumber)?.int64Value == byteCount,
              (after[.modificationDate] as? Date) == (attributes[.modificationDate] as? Date) else {
            throw SoundcoreAudioDecodeFailure.incompletePacket
        }
        #if os(iOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
            ofItemAtPath: destination.path)
        #endif
        succeeded = true
        return destination
    }
}

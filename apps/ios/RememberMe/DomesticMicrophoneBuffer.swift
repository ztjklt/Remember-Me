import Foundation
@preconcurrency import VolcEngineRTC

/// Read-only SDK microphone frames. Never writes audio to disk or mixes remote
/// audio into the owner's reference. Long utterances are rejected, not truncated.
final class DomesticMicrophoneBuffer: NSObject, ByteRTCAudioFrameObserver, @unchecked Sendable {
    private let lock = NSLock()
    private var enabled = false
    private var bytes = Data()
    private var speechStarted = false
    private var overflow = false
    func setEnabled(_ value: Bool) {
        lock.lock(); defer { lock.unlock() }
        enabled = value; bytes.removeAll(); speechStarted = false; overflow = false
    }
    func append(_ data: Data) {
        guard !data.isEmpty, data.count % 2 == 0 else { return }
        let energy = data.withUnsafeBytes { raw -> Double in
            var sum = 0.0
            for offset in stride(from: 0, to: raw.count, by: 2) {
                let value = Double(raw.loadUnaligned(fromByteOffset: offset, as: Int16.self))
                sum += value * value
            }
            return sqrt(sum / Double(raw.count / 2))
        }
        lock.lock(); defer { lock.unlock() }
        guard enabled, !overflow else { return }
        if energy >= 180 { speechStarted = true }
        bytes.append(data)
        if !speechStarted, bytes.count > 9600 { bytes.removeFirst(bytes.count - 9600) }
        if speechStarted, bytes.count > 960000 { bytes.removeAll(); overflow = true }
    }
    func drain() -> Data? {
        lock.lock(); defer { lock.unlock() }
        defer { bytes.removeAll(); speechStarted = false; overflow = false }
        guard enabled, speechStarted, !overflow, bytes.count >= 16000 else { return nil }
        return bytes
    }
    nonisolated func onRecord(_ frame: ByteRTCAudioFrame) {
        guard frame.sampleRate.rawValue == 16000, frame.channel.rawValue == 1 else { return }
        let buffer = frame.buffer as Data
        buffer.withUnsafeBytes { append(Data($0)) }
    }
    nonisolated func onPlaybackAudioFrame(_ frame: ByteRTCAudioFrame) {}
    nonisolated func onRemoteUserAudioFrame(_ streamId: String, info: ByteRTCStreamInfo, audioFrame: ByteRTCAudioFrame) {}
    nonisolated func onMixedAudioFrame(_ frame: ByteRTCAudioFrame) {}
    nonisolated func onCaptureMixedAudioFrame(_ frame: ByteRTCAudioFrame) {}
    nonisolated static func wave(_ pcm: Data) -> Data {
        var result = Data("RIFF".utf8)
        func number<T: FixedWidthInteger>(_ value: T) {
            var little = value.littleEndian
            withUnsafeBytes(of: &little) { result.append(contentsOf: $0) }
        }
        number(UInt32(pcm.count + 36)); result.append(Data("WAVEfmt ".utf8))
        number(UInt32(16)); number(UInt16(1)); number(UInt16(1)); number(UInt32(16000))
        number(UInt32(32000)); number(UInt16(2)); number(UInt16(16))
        result.append(Data("data".utf8)); number(UInt32(pcm.count)); result.append(pcm)
        return result
    }
}

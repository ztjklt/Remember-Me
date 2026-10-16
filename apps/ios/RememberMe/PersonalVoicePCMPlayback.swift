import Foundation

/// Backend audio is signed 16-bit, little-endian mono PCM at 24 kHz.
/// Consume network bytes off the main actor; only complete SDK pushes hop to it.
enum PersonalVoicePCMPlayback {
    static let frameBytes = 480 // 10 ms
    static let initialBytes = 9600 // SDK-recommended 200 ms reserve
    static let maximumBytes = 4 * 1024 * 1024

    struct Statistics: Sendable {
        var pushes = 0
        var rebufferCount = 0
        var maximumLateness: Duration = .zero
    }

    static func play<S: AsyncSequence, C: Clock>(
        _ bytes: S, clock: C,
        push: @MainActor (Data) throws -> Void
    ) async throws -> Statistics where S.Element == UInt8, C.Duration == Duration {
        var pending = Data()
        pending.reserveCapacity(initialBytes)
        var total = 0
        var requiredBytes = initialBytes
        var deadline: C.Instant?
        var statistics = Statistics()

        for try await byte in bytes {
            try Task.checkCancellation()
            total += 1
            guard total <= maximumBytes else { throw APIError.invalidResponse }
            pending.append(byte)
            guard pending.count >= requiredBytes else { continue }

            if let next = deadline {
                let late = max(.zero, next.duration(to: clock.now))
                statistics.maximumLateness = max(statistics.maximumLateness, late)
                if late >= .milliseconds(200) {
                    // The SDK reserve has drained. Re-prime before resuming instead
                    // of sending a long burst or repeatedly starving every 10 ms.
                    requiredBytes = initialBytes
                    deadline = nil
                    statistics.rebufferCount += 1
                    if pending.count < requiredBytes { continue }
                }
            }
            if let next = deadline { try await clock.sleep(until: next, tolerance: .zero) }
            try Task.checkCancellation()
            try await push(pending)
            statistics.pushes += 1
            // Keep the sample clock anchored. Rebasing to "now + 10 ms" on every
            // wake accumulates scheduler/actor delays until the reserve runs out.
            deadline = (deadline ?? clock.now).advanced(by: .milliseconds(10))
            pending.removeAll(keepingCapacity: true)
            requiredBytes = frameBytes
        }

        guard total > 0, total.isMultiple(of: 2) else { throw APIError.invalidResponse }
        if !pending.isEmpty {
            if let next = deadline { try await clock.sleep(until: next, tolerance: .zero) }
            try Task.checkCancellation()
            // Preserve every source sample; pad only the final partial 10 ms frame.
            let remainder = pending.count % frameBytes
            if remainder != 0 { pending.append(Data(repeating: 0, count: frameBytes - remainder)) }
            try await push(pending)
            statistics.pushes += 1
        }
        // Let the SDK render its reserve before closing the player. This wait is
        // cancellable, so interruption, revocation and hangup still stop at once.
        try await clock.sleep(until: clock.now.advanced(by: .milliseconds(250)), tolerance: .zero)
        return statistics
    }
}

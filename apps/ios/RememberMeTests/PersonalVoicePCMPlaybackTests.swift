import XCTest
@testable import RememberMe

private final class PCMTestClock: Clock, @unchecked Sendable {
    struct Instant: InstantProtocol {
        var offset: Duration = .zero
        func advanced(by duration: Duration) -> Self { .init(offset: offset + duration) }
        func duration(to other: Self) -> Duration { other.offset - offset }
        static func < (lhs: Self, rhs: Self) -> Bool { lhs.offset < rhs.offset }
    }
    private let lock = NSLock()
    private var instant = Instant()
    var now: Instant { lock.lock(); defer { lock.unlock() }; return instant }
    var minimumResolution: Duration { .nanoseconds(1) }
    let wakeDelay: Duration
    init(wakeDelay: Duration = .zero) { self.wakeDelay = wakeDelay }
    func advance(_ duration: Duration) {
        lock.lock(); defer { lock.unlock() }
        instant = instant.advanced(by: duration)
    }
    private func wake(at deadline: Instant) {
        lock.lock(); defer { lock.unlock() }
        if deadline > instant { instant = deadline.advanced(by: wakeDelay) }
    }
    func sleep(until deadline: Instant, tolerance: Duration?) async throws {
        try Task.checkCancellation()
        wake(at: deadline)
    }
}

private struct PCMTestBytes: AsyncSequence, Sendable {
    typealias Element = UInt8
    let data: Data
    var clock: PCMTestClock? = nil
    var stallAt: Int? = nil
    var stall: Duration = .zero
    struct AsyncIterator: AsyncIteratorProtocol {
        let source: PCMTestBytes
        var offset = 0
        mutating func next() async throws -> UInt8? {
            try Task.checkCancellation()
            guard offset < source.data.count else { return nil }
            if offset == source.stallAt { source.clock?.advance(source.stall) }
            defer { offset += 1 }
            return source.data[offset]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(source: self) }
}

@MainActor
final class PersonalVoicePCMPlaybackTests: XCTestCase {
    func testEightSecondsOfSchedulerJitterDoNotDrainInitialReserve() async throws {
        let clock = PCMTestClock(wakeDelay: .milliseconds(1))
        let source = Data((0..<384000).map { UInt8($0 % 251) })
        var reconstructed = Data(), pushes = 0, lastPush = clock.now
        let statistics = try await PersonalVoicePCMPlayback.play(PCMTestBytes(data: source), clock: clock) { frame in
            XCTAssertEqual(frame.count, pushes == 0 ? 9600 : 480)
            reconstructed.append(frame); pushes += 1; lastPush = clock.now
        }
        XCTAssertEqual(reconstructed, source)
        XCTAssertEqual(pushes, 781)
        // The previous now+10ms loop takes 8580ms here, starving the SDK after
        // consuming its 200ms lead. Absolute sample deadlines take 7801ms.
        XCTAssertEqual(lastPush.offset, .milliseconds(7801))
        XCTAssertEqual(statistics.rebufferCount, 0)
    }

    func testNetworkStallReprimesWithoutDroppingOrReorderingSamples() async throws {
        let clock = PCMTestClock()
        let source = Data((0..<19680).map { UInt8($0 % 251) })
        var frames = [Data](), times = [Duration]()
        let statistics = try await PersonalVoicePCMPlayback.play(
            PCMTestBytes(data: source, clock: clock, stallAt: 9600, stall: .milliseconds(300)), clock: clock
        ) { frame in frames.append(frame); times.append(clock.now.offset) }
        XCTAssertEqual(frames.map(\.count), [9600, 9600, 480])
        XCTAssertEqual(frames.reduce(into: Data()) { $0.append($1) }, source)
        XCTAssertEqual(times, [.zero, .milliseconds(300), .milliseconds(310)])
        XCTAssertEqual(statistics.rebufferCount, 1)
        XCTAssertEqual(statistics.maximumLateness, .milliseconds(290))
    }

    func testSDKPushWorkDoesNotAccumulateIntoPlaybackClock() async throws {
        let clock = PCMTestClock()
        var lastPush = clock.now
        let statistics = try await PersonalVoicePCMPlayback.play(
            PCMTestBytes(data: Data(repeating: 0, count: 384000)), clock: clock
        ) { _ in
            lastPush = clock.now
            clock.advance(.milliseconds(1)) // SDK work or a hop back from MainActor.
        }
        XCTAssertEqual(lastPush.offset, .milliseconds(7801))
        XCTAssertEqual(statistics.rebufferCount, 0)
    }

    func testTailIsPacedAndOnlyFinalPartialFrameIsPadded() async throws {
        let clock = PCMTestClock()
        let source = Data((0..<10082).map { UInt8($0 % 251) })
        var frames = [Data](), times = [Duration]()
        _ = try await PersonalVoicePCMPlayback.play(PCMTestBytes(data: source), clock: clock) { frame in
            frames.append(frame); times.append(clock.now.offset)
        }
        XCTAssertEqual(frames.map(\.count), [9600, 480, 480])
        XCTAssertEqual(times, [.zero, .milliseconds(10), .milliseconds(20)])
        let result = frames.reduce(into: Data()) { $0.append($1) }
        XCTAssertEqual(Data(result.prefix(source.count)), source)
        XCTAssertEqual(result.suffix(478), Data(repeating: 0, count: 478))
    }

    func testShortStreamStillPlaysEverySample() async throws {
        let source = Data(repeating: 7, count: 242)
        var frames = [Data]()
        _ = try await PersonalVoicePCMPlayback.play(PCMTestBytes(data: source), clock: PCMTestClock()) { frames.append($0) }
        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frames.first?.count, 480)
        XCTAssertEqual(frames.first?.prefix(242), source)
    }

    func testEmptyAndIncompleteSampleAreRejectedBeforePlayback() async {
        for source in [Data(), Data([1, 2, 3])] {
            var pushes = 0
            do {
                _ = try await PersonalVoicePCMPlayback.play(PCMTestBytes(data: source), clock: PCMTestClock()) { _ in pushes += 1 }
                XCTFail("Invalid PCM accepted")
            } catch { XCTAssertEqual(pushes, 0) }
        }
    }

    func testPlayerFailureStopsWithoutSendingMoreFrames() async {
        var pushes = 0
        do {
            _ = try await PersonalVoicePCMPlayback.play(
                PCMTestBytes(data: Data(repeating: 0, count: 19200)), clock: PCMTestClock()
            ) { _ in pushes += 1; throw CancellationError() }
            XCTFail("Player failure was swallowed")
        } catch { XCTAssertEqual(pushes, 1) }
    }

    func testOversizedStreamStopsAtExistingFourMiBLimit() async {
        var pushedBytes = 0
        do {
            _ = try await PersonalVoicePCMPlayback.play(
                PCMTestBytes(data: Data(repeating: 0, count: 4 * 1024 * 1024 + 2)), clock: PCMTestClock()
            ) { pushedBytes += $0.count }
            XCTFail("Oversized PCM accepted")
        } catch {
            XCTAssertLessThanOrEqual(pushedBytes, 4 * 1024 * 1024)
        }
    }

    func testCancellationWhileWaitingForNetworkCannotPushAgain() async throws {
        let started = expectation(description: "Initial reserve sent")
        let stream = AsyncThrowingStream<UInt8, Error>.makeStream()
        for _ in 0..<9600 { stream.continuation.yield(0) }
        var pushes = 0
        let task = Task {
            try await PersonalVoicePCMPlayback.play(stream.stream, clock: ContinuousClock()) { _ in
                pushes += 1; started.fulfill()
            }
        }
        await fulfillment(of: [started], timeout: 3)
        task.cancel()
        do { _ = try await task.value; XCTFail("Cancellation was swallowed") }
        catch { XCTAssertTrue(error is CancellationError) }
        stream.continuation.finish()
        XCTAssertEqual(pushes, 1)
    }
}

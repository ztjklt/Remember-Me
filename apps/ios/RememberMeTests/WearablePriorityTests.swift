import XCTest
@testable import RememberMe

final class WearablePriorityTests: XCTestCase {
    func testTwoPressesProtectOnlyTheConversationBetweenThem() {
        let timeline = WearablePriorityTimeline(markersMS: [10_000, 35_000], isComplete: true)
        XCTAssertEqual(timeline.ranges(durationMS: 60_000), [.init(startMS: 10_000, endMS: 35_000)])
    }

    func testRepeatedCallbacksDoNotToggleTwiceAndUnclosedPriorityContinuesToEnd() {
        var timeline = WearablePriorityTimeline()
        timeline.observe([10_000], final: false)
        timeline.observe([10_000, 20_000, 40_000], final: false)
        timeline.observe([10_000, 20_000, 40_000], final: true)
        XCTAssertEqual(timeline.ranges(durationMS: 60_000), [
            .init(startMS: 10_000, endMS: 20_000), .init(startMS: 40_000, endMS: 60_000)])
    }

    func testPriorityAcrossUploadBoundaryPreservesBothSides() throws {
        let timeline = WearablePriorityTimeline(markersMS: [290_000, 320_000], isComplete: true)
        XCTAssertEqual(timeline.ranges(durationMS: 360_000, clippedToStart: 0, end: 300_000),
                       [.init(startMS: 290_000, endMS: 300_000)])
        XCTAssertEqual(timeline.ranges(durationMS: 360_000, clippedToStart: 300_000, end: 360_000),
                       [.init(startMS: 0, endMS: 20_000)])
        let metadata = try timeline.metadata(durationMS: 360_000, startMS: 300_000, endMS: 360_000)
        XCTAssertEqual(metadata["priority_ranges_ms"], "[[0,20000]]")
        XCTAssertEqual(metadata["priority_timeline_complete"], "true")
    }

    func testMissingDamagedOrOutOfRangeTimelineProtectsEverything() {
        for timeline in [WearablePriorityTimeline(),
                         WearablePriorityTimeline(markersMS: [-1], isComplete: true),
                         WearablePriorityTimeline(markersMS: [70_000], isComplete: true)] {
            XCTAssertEqual(timeline.ranges(durationMS: 60_000), [.init(startMS: 0, endMS: 60_000)])
        }
        XCTAssertTrue(WearablePriorityTimeline(markersMS: [], isComplete: true).ranges(durationMS: 60_000).isEmpty)
    }

    func testLivePacketsSealWhileRecordingAndDuplicatesDoNotCreateAudio() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let capture = SoundcoreLiveCapture(root: root, millisecondsPerChunk: 40)
        let first = Data(repeating: 1, count: 160), second = Data(repeating: 2, count: 160)
        XCTAssertTrue(try capture.append(fileID: 100, sequence: 0, isAppendPreAudio: false, data: first).isEmpty)
        XCTAssertTrue(try capture.append(fileID: 100, sequence: 0, isAppendPreAudio: false, data: first).isEmpty)
        let piece = try XCTUnwrap(capture.append(fileID: 100, sequence: 1, isAppendPreAudio: false, data: second).first)
        XCTAssertEqual(try Data(contentsOf: piece.url), first + second)
        XCTAssertEqual(piece.sourceStartMS, 0); XCTAssertEqual(piece.sourceEndMS, 40)
        XCTAssertTrue(piece.timelineComplete)
        XCTAssertNil(try capture.finish())
    }

    func testPacketGapKeepsBothOriginalPiecesAndMarksFollowingTimelineUnknown() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let capture = SoundcoreLiveCapture(root: root)
        let packet = Data(repeating: 1, count: 160)
        _ = try capture.append(fileID: 100, sequence: 0, isAppendPreAudio: false, data: packet)
        let before = try XCTUnwrap(capture.append(fileID: 100, sequence: 3, isAppendPreAudio: false, data: packet).first)
        let after = try XCTUnwrap(capture.finish())
        XCTAssertEqual(before.sourceEndMS, 20)
        XCTAssertEqual(after.sourceStartMS, 60); XCTAssertEqual(after.sourceEndMS, 80)
        XCTAssertFalse(after.timelineComplete)
        XCTAssertEqual(try Data(contentsOf: before.url), packet)
        XCTAssertEqual(try Data(contentsOf: after.url), packet)
    }

    func testSameDeviceFileIDWithDifferentPacketsCannotSuppressNewAudio() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let old = root.appendingPathComponent("old.opus"), new = root.appendingPathComponent("new.opus")
        try Data(repeating: 1, count: 320).write(to: old)
        try Data(repeating: 2, count: 320).write(to: new)
        let coverage = [DevicePacketCoverage(startMS: 0, endMS: 40, originalRef: "old.opus")]
        XCTAssertEqual(try DevicePacketCoverage.uncovered(input: new, startMS: 0, endMS: 40,
            previous: coverage, originals: root), [.init(startMS: 0, endMS: 40)])
        XCTAssertTrue(try DevicePacketCoverage.uncovered(input: old, startMS: 0, endMS: 40,
            previous: coverage, originals: root).isEmpty)
    }
}

import Foundation

struct WearablePriorityRange: Codable, Equatable, Sendable {
    let startMS: Int
    let endMS: Int
}

/// Hardware timestamps are toggle boundaries, not point-sized highlights.
/// Missing metadata protects the whole audio instead of silently compacting it.
struct WearablePriorityTimeline: Codable, Equatable, Sendable {
    private(set) var markersMS: [Int] = []
    private(set) var isComplete = false
    private(set) var hasInvalidMarkers = false

    init(markersMS: [Int] = [], isComplete: Bool = false) {
        observe(markersMS, final: isComplete)
    }

    mutating func observe(_ offsets: [Int], final: Bool) {
        if offsets.count > 20_000 || offsets.contains(where: { $0 < 0 || $0 > 86_400_000 }) {
            hasInvalidMarkers = true
            isComplete = false
            return
        }
        // Decode metadata is the authoritative full list. Progress / live
        // callbacks may repeat a timestamp already received by another route.
        if final {
            markersMS = Array(Set(offsets)).sorted()
            isComplete = !hasInvalidMarkers
        } else {
            markersMS = Array(Set(markersMS + offsets)).sorted()
        }
    }

    func ranges(durationMS: Int) -> [WearablePriorityRange] {
        guard durationMS > 0 else { return [] }
        guard isComplete, !hasInvalidMarkers,
              markersMS.allSatisfy({ $0 <= durationMS }) else {
            return [.init(startMS: 0, endMS: durationMS)]
        }
        let boundaries = markersMS
        return stride(from: 0, to: boundaries.count, by: 2).compactMap { index in
            let start = boundaries[index]
            let end = index + 1 < boundaries.count ? boundaries[index + 1] : durationMS
            return start < end ? .init(startMS: start, endMS: end) : nil
        }
    }

    func ranges(durationMS: Int, clippedToStart start: Int, end: Int) -> [WearablePriorityRange] {
        guard start >= 0, start < end, end <= durationMS else { return [] }
        return ranges(durationMS: durationMS).compactMap { interval in
            let left = max(start, interval.startMS), right = min(end, interval.endMS)
            return left < right ? .init(startMS: left - start, endMS: right - start) : nil
        }
    }

    func metadata(durationMS: Int, startMS: Int, endMS: Int) throws -> [String: String] {
        let ranges = ranges(durationMS: durationMS, clippedToStart: startMS, end: endMS)
        let serialized = try JSONEncoder().encode(ranges.map { [$0.startMS, $0.endMS] })
        let complete = isComplete && !hasInvalidMarkers && markersMS.allSatisfy { $0 <= durationMS }
        return ["wearable_policy_version": "wearable-priority-v1",
                "priority_ranges_ms": String(decoding: serialized, as: UTF8.self),
                "priority_timeline_complete": complete ? "true" : "false",
                "transcript_retention": "derived_only"]
    }
}

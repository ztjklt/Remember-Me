import ActivityKit
import Foundation

struct RecordingActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var phase: String
        var elapsedSeconds: Int
        var timerAnchor: Date
        var source: String
    }
    let recordingID: String
}

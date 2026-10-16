@preconcurrency import ActivityKit
import Foundation

@MainActor
protocol RecordingLiveActivityHandle: AnyObject {
    var id: String { get }
    func update(_ state: RecordingActivityAttributes.ContentState, staleDate: Date) async
    func end() async
}

@MainActor
protocol RecordingLiveActivityBackend {
    var available: Bool { get }
    var activities: [any RecordingLiveActivityHandle] { get }
    func request(id: String, state: RecordingActivityAttributes.ContentState, staleDate: Date) throws -> any RecordingLiveActivityHandle
}

@MainActor
private final class SystemRecordingActivity: RecordingLiveActivityHandle {
    let activity: Activity<RecordingActivityAttributes>
    init(_ activity: Activity<RecordingActivityAttributes>) { self.activity = activity }
    var id: String { activity.id }
    func update(_ state: RecordingActivityAttributes.ContentState, staleDate: Date) async {
        await activity.update(ActivityContent(state: state, staleDate: staleDate))
    }
    func end() async { await activity.end(nil, dismissalPolicy: .immediate) }
}

@MainActor
private struct SystemRecordingActivityBackend: RecordingLiveActivityBackend {
    var available: Bool { ActivityAuthorizationInfo().areActivitiesEnabled }
    var activities: [any RecordingLiveActivityHandle] {
        Activity<RecordingActivityAttributes>.activities.map(SystemRecordingActivity.init)
    }
    func request(id: String, state: RecordingActivityAttributes.ContentState, staleDate: Date) throws -> any RecordingLiveActivityHandle {
        SystemRecordingActivity(try Activity.request(attributes: RecordingActivityAttributes(recordingID: id),
            content: ActivityContent(state: state, staleDate: staleDate), pushType: nil))
    }
}

@MainActor
final class RecordingActivityController {
    private let backend: any RecordingLiveActivityBackend
    private let now: () -> Date
    private var activity: (any RecordingLiveActivityHandle)?
    private var lastUpdate = Date.distantPast
    private var desiredState: RecordingActivityAttributes.ContentState?
    private var generation = 0
    private var operations: Task<Void, Never>?
    var available: Bool { backend.available }

    init(backend: any RecordingLiveActivityBackend, now: @escaping () -> Date = Date.init) {
        self.backend = backend; self.now = now
    }
    convenience init() { self.init(backend: SystemRecordingActivityBackend()) }

    // ActivityKit updates/end are async. One queue keeps a late update from
    // overtaking end, and releases the previous system activity before request.
    private func enqueue(_ action: @escaping @MainActor () async -> Void) {
        let previous = operations
        operations = Task { await previous?.value; await action() }
    }

    func start(id: String, source: String) {
        finish()
        guard available else { return }
        let date = now(), generation = self.generation
        let state = RecordingActivityAttributes.ContentState(phase: "recording", elapsedSeconds: 0,
                                                            timerAnchor: date, source: source)
        desiredState = state; lastUpdate = date
        enqueue { [weak self] in
            guard let self, self.generation == generation, let state = self.desiredState else { return }
            self.activity = try? self.backend.request(id: id, state: state, staleDate: self.now().addingTimeInterval(90))
        }
    }
    func update(paused: Bool, seconds: Int, source: String) {
        guard let previous = desiredState else { return }
        let date = now()
        let phase = paused ? "paused" : "recording"
        guard phase != previous.phase || source != previous.source || date.timeIntervalSince(lastUpdate) >= 30 else { return }
        lastUpdate = date
        let state = RecordingActivityAttributes.ContentState(phase: phase, elapsedSeconds: max(0, seconds),
            timerAnchor: date.addingTimeInterval(-Double(max(0, seconds))), source: source)
        desiredState = state
        // A pending request reads the latest desired state when it executes.
        guard let activity else { return }
        let generation = self.generation
        enqueue { [weak self] in
            guard let self, self.generation == generation, self.activity?.id == activity.id else { return }
            // Paused recordings also expire when the process stops reporting.
            await activity.update(state, staleDate: date.addingTimeInterval(90))
        }
    }
    func finish() {
        generation += 1; desiredState = nil
        guard let previous = activity else { return }
        activity = nil
        enqueue { await previous.end() }
    }
    func clearOrphans() {
        let current = activity?.id
        let orphans = backend.activities.filter { $0.id != current }
        enqueue { for old in orphans { await old.end() } }
    }
    #if DEBUG
    private(set) var previewFailure = ""
    func previewForUITest() -> Bool {
        finish()
        let state = RecordingActivityAttributes.ContentState(phase: "preview", elapsedSeconds: 83,
                                                            timerAnchor: now().addingTimeInterval(-83), source: "界面测试预览")
        do {
            activity = try backend.request(id: "isolated-ui-preview", state: state, staleDate: now().addingTimeInterval(90))
        } catch { previewFailure = String(describing: error) }
        return activity != nil
    }
    #endif

}

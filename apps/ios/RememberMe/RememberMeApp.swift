import SwiftUI

@main
struct RememberMeApp: App {
    @StateObject private var model = makeModel()
    @Environment(\.scenePhase) private var scenePhase

    private static func makeModel() -> AppModel {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-offline") {
            let suite = "remember-ui-offline-" + UUID().uuidString
            let root = FileManager.default.temporaryDirectory.appendingPathComponent(suite)
            return AppModel(recordingStore: LocalRecordingStore(root: root),
                            defaults: UserDefaults(suiteName: suite)!, pairing: nil)
        }
        #endif
        return AppModel()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .onOpenURL { model.importPairingLink($0) }
                .task { await model.refresh() }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .background { model.finishRecording(); model.stopPlayback() }
                }
        }
    }
}

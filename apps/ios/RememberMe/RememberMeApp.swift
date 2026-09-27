import SwiftUI

@main
struct RememberMeApp: App {
    @StateObject private var model = AppModel()
    @Environment(\.scenePhase) private var scenePhase

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

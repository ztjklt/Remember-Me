import SwiftUI

@main
struct RememberMeApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .onOpenURL { model.importPairingLink($0) }
                .task { await model.refresh() }
        }
    }
}

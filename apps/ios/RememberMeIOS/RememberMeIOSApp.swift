import SwiftUI

@main
struct RememberMeIOSApp: App {
    @StateObject private var model = EpisodeFlow()
    @StateObject private var capture = AudioCapture()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .environmentObject(capture)
        }
    }
}

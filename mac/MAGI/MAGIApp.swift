import SwiftUI

@main
struct MAGIApp: App {
    @MainActor
    init() {
        // Offline render mode exits before any window is shown.
        _ = Preview.runIfRequested()
    }

    var body: some Scene {
        WindowGroup("MAGI") {
            ContentView()
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}

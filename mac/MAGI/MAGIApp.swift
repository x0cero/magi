import SwiftUI

@main
struct MAGIApp: App {
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

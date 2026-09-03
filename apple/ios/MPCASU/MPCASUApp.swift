import SwiftUI

@main
struct MPCASUApp: App {
    @StateObject private var model = PlayerModel()

    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(model)
                .onOpenURL { model.importURLs([$0]) }
        }
    }
}


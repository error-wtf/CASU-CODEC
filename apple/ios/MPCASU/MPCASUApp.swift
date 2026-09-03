import SwiftUI
import AVFoundation

@main
struct MPCASUApp: App {
    @StateObject private var model = PlayerModel()

    init() {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        try? AVAudioSession.sharedInstance().setActive(true)
    }

    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(model)
                .onOpenURL { model.importURLs([$0]) }
        }
    }
}

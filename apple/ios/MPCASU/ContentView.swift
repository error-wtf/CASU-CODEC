import AVKit
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var model: PlayerModel
    @State private var importing = false

    var body: some View {
        NavigationSplitView {
            List(selection: Binding(get: { model.queue.currentOccurrenceID }, set: { id in
                if let item = model.queue.occurrences.first(where: { $0.id == id }) { model.select(item) }
            })) {
                ForEach(model.queue.occurrences) { item in
                    Text(item.title).tag(item.id)
                        .accessibilityIdentifier("queue.occurrence.\(item.id)")
                        .swipeActions { Button(role: .destructive) { model.remove(item) } label: { Label("Remove", systemImage: "trash") } }
                }.onMove(perform: model.move)
            }
            .navigationTitle("Queue")
            .toolbar { Button { importing = true } label: { Label("Open", systemImage: "folder") }.accessibilityIdentifier("queue.open") }
        } detail: {
            VStack(spacing: 20) {
                VideoPlayer(player: model.player).accessibilityLabel("Video player")
                Text(model.current?.title ?? "Open media to begin").font(.headline).lineLimit(2)
                Button(action: model.togglePlayback) {
                    Label(model.isPlaying ? "Pause" : "Play", systemImage: model.isPlaying ? "pause.fill" : "play.fill")
                }.buttonStyle(.borderedProminent).disabled(model.current == nil).accessibilityIdentifier("playback.toggle")
            }.padding()
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.audio, .movie, .playlist, .data], allowsMultipleSelection: true) { result in
            switch result { case .success(let urls): model.importURLs(urls); case .failure: model.errorMessage = "The selected document could not be opened." }
        }
        .alert("MPCASU", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
            Button("OK") { model.errorMessage = nil }
        } message: { Text(model.errorMessage ?? "") }
    }
}


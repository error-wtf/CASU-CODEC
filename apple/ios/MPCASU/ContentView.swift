import AVKit
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var model: PlayerModel
    @State private var importing = false
    @StateObject private var library = MediaLibraryModel()
    @StateObject private var recording = RecordingController()

    var body: some View {
        TabView {
            playerView
                .tabItem { Label("Player", systemImage: "play.circle") }
            libraryView
                .tabItem { Label("Library", systemImage: "music.note.list") }
        }
    }

    private var playerView: some View {
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
                Picker("Recording split", selection: $recording.mode) {
                    ForEach(RecordingSplitMode.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("recording.split-mode")
                if recording.mode == .time {
                    Stepper("Every \(recording.intervalMinutes) minutes", value: $recording.intervalMinutes, in: 1...1440)
                }
                Button { recording.toggle(model.current) } label: {
                    Label(recording.isRecording ? "Stop recording" : "Record",
                          systemImage: recording.isRecording ? "stop.circle.fill" : "record.circle")
                }
                .disabled(model.current == nil)
                .accessibilityIdentifier("recording.toggle")
                if !recording.status.isEmpty { Text(recording.status).font(.caption) }
            }.padding()
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.audio, .movie, .playlist, .data], allowsMultipleSelection: true) { result in
            switch result { case .success(let urls): model.importURLs(urls); case .failure: model.errorMessage = "The selected document could not be opened." }
        }
        .alert("MPCASU", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
            Button("OK") { model.errorMessage = nil }
        } message: { Text(model.errorMessage ?? "") }
        .onChange(of: model.queue.currentOccurrenceID) {
            if let item = model.current { recording.sourceChanged(item) }
        }
    }

    private var libraryView: some View {
        NavigationStack {
            VStack(spacing: 8) {
                Picker("Library section", selection: $library.section) {
                    ForEach(LibrarySection.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("library.sections")
                TextField("Search library", text: $library.search)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("library.search")
                if library.authorizationDenied {
                    ContentUnavailableView("Media Library Access Required",
                                           systemImage: "music.note",
                                           description: Text("Allow media-library access in Settings."))
                } else if library.section != .songs && library.selectedGroup == nil {
                    List(library.groups, id: \.self) { group in
                        Button {
                            library.selectedGroup = group
                        } label: {
                            HStack {
                                Text(group)
                                Spacer()
                                Text("\(MediaLibraryModel.tracks(in: library.tracks, section: library.section, group: group).count)")
                                    .foregroundStyle(.secondary)
                                Image(systemName: "chevron.right").foregroundStyle(.secondary)
                            }
                        }
                        .accessibilityIdentifier("library.group.\(group)")
                    }
                } else {
                    List(library.visibleTracks) { track in
                        Button {
                            guard let url = track.assetURL else {
                                model.errorMessage = "This protected media item cannot be played."
                                return
                            }
                            model.importURLs([url])
                            if let item = model.queue.occurrences.last { model.select(item) }
                        } label: {
                            VStack(alignment: .leading) {
                                Text(track.title)
                                Text([track.artist, track.album, track.genre].joined(separator: " · "))
                                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                        .accessibilityIdentifier("library.track.\(track.id)")
                    }
                }
            }
            .padding(.horizontal)
            .navigationTitle(library.selectedGroup ?? "Library")
            .toolbar {
                if library.selectedGroup != nil {
                    Button("All \(library.section.rawValue)") { library.selectedGroup = nil }
                }
                Button { library.refresh() } label: { Image(systemName: "arrow.clockwise") }
            }
            .task { library.refresh() }
        }
    }
}

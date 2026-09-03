import AVFoundation
import MediaPlayer
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class PlayerModel: ObservableObject {
    @Published private(set) var queue = QueueSnapshot()
    @Published private(set) var isPlaying = false
    @Published var errorMessage: String?
    let player = AVPlayer()
    private let storageURL: URL

    init(storageURL: URL? = nil) {
        self.storageURL = storageURL ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MPCASU/queue-v1.json")
        restore()
        configureRemoteCommands()
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: nil, queue: .main) {
            [weak self] _ in Task { @MainActor in self?.advance() }
        }
    }

    func importURLs(_ urls: [URL]) {
        for url in urls {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            let canonical = url.standardizedFileURL.absoluteString
            let identity = MediaIdentity(kind: url.isFileURL ? .local : .network, canonicalKey: canonical)
            queue.occurrences.append(QueueOccurrence(media: identity, title: url.deletingPathExtension().lastPathComponent, url: url))
        }
        if queue.currentOccurrenceID == nil { queue.currentOccurrenceID = queue.occurrences.first?.id }
        persist()
    }

    func select(_ occurrence: QueueOccurrence) {
        queue.currentOccurrenceID = occurrence.id
        player.replaceCurrentItem(with: AVPlayerItem(url: occurrence.url))
        updateNowPlaying(occurrence)
        persist()
    }

    func togglePlayback() {
        guard let current = current else { return }
        if player.currentItem == nil { select(current) }
        if isPlaying { player.pause() } else { player.play() }
        isPlaying.toggle()
        MPNowPlayingInfoCenter.default().playbackState = isPlaying ? .playing : .paused
    }

    func remove(_ occurrence: QueueOccurrence) {
        let wasCurrent = occurrence.id == queue.currentOccurrenceID
        queue.occurrences.removeAll { $0.id == occurrence.id }
        if wasCurrent {
            player.pause(); player.replaceCurrentItem(with: nil); isPlaying = false
            queue.currentOccurrenceID = queue.occurrences.first?.id
        }
        persist()
    }

    func move(from source: IndexSet, to destination: Int) {
        queue.occurrences.move(fromOffsets: source, toOffset: destination)
        persist()
    }

    func advance() {
        guard let id = queue.currentOccurrenceID,
              let index = queue.occurrences.firstIndex(where: { $0.id == id }),
              index + 1 < queue.occurrences.count else {
            isPlaying = false; return
        }
        select(queue.occurrences[index + 1]); player.play(); isPlaying = true
    }

    var current: QueueOccurrence? {
        queue.occurrences.first { $0.id == queue.currentOccurrenceID }
    }

    private func persist() {
        do {
            let data = try QueuePersistence.encode(queue)
            try FileManager.default.createDirectory(at: storageURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: storageURL, options: .atomic)
        } catch { errorMessage = "Queue could not be saved." }
    }

    private func restore() {
        guard let data = try? Data(contentsOf: storageURL) else { return }
        do { queue = try QueuePersistence.decode(data) }
        catch { queue = QueueSnapshot(); errorMessage = "Saved queue was invalid and was not restored." }
    }

    private func updateNowPlaying(_ occurrence: QueueOccurrence) {
        MPNowPlayingInfoCenter.default().nowPlayingInfo = [
            MPMediaItemPropertyTitle: occurrence.title,
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? 1.0 : 0.0,
        ]
    }

    private func configureRemoteCommands() {
        let center = MPRemoteCommandCenter.shared()
        center.playCommand.addTarget { [weak self] _ in Task { @MainActor in self?.togglePlayback() }; return .success }
        center.pauseCommand.addTarget { [weak self] _ in Task { @MainActor in self?.togglePlayback() }; return .success }
        center.nextTrackCommand.addTarget { [weak self] _ in Task { @MainActor in self?.advance() }; return .success }
    }
}


import XCTest
@testable import MPCASU

final class QueueModelsTests: XCTestCase {
    func testDuplicateMediaRemainDistinctOccurrencesAndRoundTrip() throws {
        let url = URL(string: "https://example.test/media.mp3")!
        let media = MediaIdentity(mediaID: "med_0123456789abcdef", kind: .network, canonicalKey: url.absoluteString)
        let first = QueueOccurrence(media: media, title: "First", url: url)
        let second = QueueOccurrence(media: media, title: "Second", url: url)
        let state = QueueSnapshot(occurrences: [first, second], currentOccurrenceID: second.id)
        let restored = try QueuePersistence.decode(QueuePersistence.encode(state))
        XCTAssertEqual(restored, state)
        XCTAssertNotEqual(restored.occurrences[0].id, restored.occurrences[1].id)
        XCTAssertEqual(restored.currentOccurrenceID, second.id)
    }

    func testCorruptOrInconsistentStateIsRejected() throws {
        XCTAssertThrowsError(try QueuePersistence.decode(Data("{}".utf8)))
        let url = URL(string: "https://example.test/media.mp3")!
        let media = MediaIdentity(kind: .network, canonicalKey: url.absoluteString)
        let item = QueueOccurrence(media: media, title: "Item", url: url)
        let invalid = QueueSnapshot(occurrences: [item], currentOccurrenceID: UUID())
        XCTAssertThrowsError(try QueuePersistence.encode(invalid))
    }

    func testLibraryGroupsAreRealSortedSelections() {
        let tracks = [
            LibraryTrack(id: 1, title: "Zulu", artist: "Beta", album: "Second", genre: "Rock", assetURL: nil),
            LibraryTrack(id: 2, title: "Alpha", artist: "alpha", album: "First", genre: "Jazz", assetURL: nil),
            LibraryTrack(id: 3, title: "Bravo", artist: "Beta", album: "Second", genre: "Rock", assetURL: nil),
        ]
        XCTAssertEqual(MediaLibraryModel.groups(in: tracks, by: .artists), ["alpha", "Beta"])
        XCTAssertEqual(MediaLibraryModel.tracks(in: tracks, section: .artists, group: "Beta").map(\.title),
                       ["Bravo", "Zulu"])
        XCTAssertEqual(MediaLibraryModel.groups(in: tracks, by: .genres), ["Jazz", "Rock"])
    }
}

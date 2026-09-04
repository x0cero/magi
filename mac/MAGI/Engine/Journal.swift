import Foundation

/// The engine's append-only journal at ~/.config/magi/journal.jsonl. The app
/// only ever reads it: one entry for the RECORD card, and the count for the
/// title bar. Writing stays with the engine.
enum Journal {

    struct Entry {
        let date: Date
        let question: String
        let synthesis: String
        let outcome: String
        let userOutcome: String?
    }

    static var path: String {
        FileManager.default.homeDirectoryForCurrentUser.path + "/.config/magi/journal.jsonl"
    }

    /// Everything in the file, oldest first. Malformed lines are skipped.
    static func load() -> [Entry] {
        guard let data = FileManager.default.contents(atPath: path),
              let text = String(data: data, encoding: .utf8) else { return [] }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        return text.split(separator: "\n").compactMap { line in
            guard let raw = line.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: raw) as? [String: Any],
                  let question = object["question"] as? String else { return nil }
            let stamp = object["timestamp"] as? String ?? ""
            let date = iso.date(from: stamp) ?? plain.date(from: stamp) ?? .distantPast
            return Entry(date: date,
                         question: question,
                         synthesis: object["synthesis"] as? String ?? "",
                         outcome: object["outcome"] as? String ?? "",
                         userOutcome: object["user_outcome"] as? String)
        }
    }

    /// The card prefers an entry the user came back and closed out, because
    /// "they said no, you shipped anyway" is the whole point of a record.
    /// Otherwise the most recent question.
    static func featured(_ entries: [Entry]) -> Entry? {
        entries.last(where: { ($0.userOutcome ?? "").isEmpty == false }) ?? entries.last
    }
}

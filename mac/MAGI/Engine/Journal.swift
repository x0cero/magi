import Foundation

/// The engine's append-only journal at ~/.config/magi/journal.jsonl. The app
/// only ever reads it: the threads for the HISTORY list, and the count for
/// the title bar. Writing stays with the engine.
enum Journal {

    struct Entry: Identifiable, Equatable {
        let id: String
        let thread: String
        let turn: Int
        let date: Date
        let question: String
        let synthesis: String
        let outcome: String
        let mode: String
        let decision: String
        let userOutcome: String?
        /// Each member's final position on this turn, in the shape the
        /// transcript draws. Empty for entries written before threads existed.
        let positions: [String: Position]
    }

    /// One conversation: its turns in order.
    struct Thread: Identifiable, Equatable {
        let id: String
        let turns: [Entry]
        var first: Entry { turns[0] }
        var last: Entry { turns[turns.count - 1] }
        var date: Date { first.date }
        var question: String { first.question }
    }

    static var path: String {
        // Overridable so screenshots can be taken against a stand-in journal
        // rather than the owner's actual decisions.
        if let override = ProcessInfo.processInfo.environment["MAGI_JOURNAL_PATH"], !override.isEmpty {
            return override
        }
        return FileManager.default.homeDirectoryForCurrentUser.path + "/.config/magi/journal.jsonl"
    }

    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let plainISO = ISO8601DateFormatter()

    /// Everything in the file, oldest first. Malformed lines are skipped.
    static func load() -> [Entry] {
        guard let data = FileManager.default.contents(atPath: path),
              let text = String(data: data, encoding: .utf8) else { return [] }
        return text.split(separator: "\n").compactMap { line in
            guard let raw = line.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: raw) as? [String: Any]
            else { return nil }
            return parse(object)
        }
    }

    /// One journal line, as the file or the engine's `thread` event carries it.
    static func parse(_ object: [String: Any]) -> Entry? {
        guard let question = object["question"] as? String else { return nil }
        let id = object["id"] as? String ?? UUID().uuidString
        let stamp = object["timestamp"] as? String ?? ""
        let date = iso.date(from: stamp) ?? plainISO.date(from: stamp) ?? .distantPast
        var positions: [String: Position] = [:]
        for (member, value) in object["positions"] as? [String: [String: Any]] ?? [:] {
            positions[member] = position(member: member, value)
        }
        return Entry(id: id,
                     thread: object["thread"] as? String ?? id,
                     turn: object["turn"] as? Int ?? 1,
                     date: date,
                     question: question,
                     synthesis: object["synthesis"] as? String ?? "",
                     outcome: object["outcome"] as? String ?? "",
                     mode: object["mode"] as? String ?? "decision",
                     decision: object["decision"] as? String ?? "",
                     userOutcome: object["user_outcome"] as? String,
                     positions: positions)
    }

    /// The journal stores the engine's own response fields. The transcript
    /// wants the wire shape, so this is the one place the two are mapped.
    private static func position(member: String, _ raw: [String: Any]) -> Position {
        var p = Position()
        p.reasoning = raw["reasoning"] as? String ?? ""
        p.finding = raw["lens_finding"] as? String ?? ""
        p.confidence = raw["confidence"] as? Int
        if let verdict = raw["verdict"] as? String { p.verdictKey = Verdict(rawValue: verdict) }
        p.option = raw["chosen_option"] as? String
        p.recommendation = raw["recommendation"] as? String
        p.condition = raw["condition"] as? String
        switch member {
        case "MELCHIOR": p.lens = "MECHANISM"
        case "BALTHASAR": p.lens = "COST"
        case "CASPER": p.lens = "WANT"
        default: p.lens = ""
        }
        return p
    }

    /// Conversations, newest first. Entries written before threads existed
    /// each stand as a one-turn conversation.
    static func threads(_ entries: [Entry]) -> [Thread] {
        var order: [String] = []
        var grouped: [String: [Entry]] = [:]
        for entry in entries {
            if grouped[entry.thread] == nil { order.append(entry.thread) }
            grouped[entry.thread, default: []].append(entry)
        }
        return order
            .map { id in Thread(id: id, turns: grouped[id]!.sorted { $0.turn < $1.turn }) }
            .sorted { $0.last.date > $1.last.date }
    }
}

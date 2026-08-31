import Foundation

/// Every word a person reads, in one place.
///
/// The engine speaks its own vocabulary: ACCEPT, CONDITIONAL, MECHANISM, and
/// a tally like `(0A · 1C · 2R)`. That vocabulary is load-bearing inside the
/// prompts and must not change. It is also meaningless to anybody who did not
/// write it, so nothing from it reaches the screen untranslated.
///
/// The rule for this file: if a sentence needs the reader to already know
/// something about how this was built, it is wrong.
enum Plain {

    // MARK: - What each member is for

    /// The engine labels each member's angle MECHANISM, COST or WANT. On screen
    /// they get the question that angle actually answers.
    static func role(_ member: String) -> String {
        switch member {
        case "MELCHIOR": return "WILL IT WORK"
        case "BALTHASAR": return "WHAT IT COSTS"
        case "CASPER": return "WHAT YOU WANT"
        case "BANKER": return "THE MONEY"
        case "THERAPIST": return "WHAT'S UNDERNEATH"
        case "LAWYER": return "WHAT COULD BITE"
        case "COACH": return "WHERE IT LEADS"
        case "DOCTOR": return "YOUR HEALTH"
        default: return "ANOTHER ANGLE"
        }
    }

    /// Longer version, for the one-line explainer under a member's argument.
    static func roleLong(_ member: String) -> String {
        switch member {
        case "MELCHIOR": return "looks at whether the thing actually works"
        case "BALTHASAR": return "looks at what it costs you"
        case "CASPER": return "looks at what you actually want"
        default: return "brings another angle"
        }
    }

    /// The engine's lens tag, translated. Falls back to the tag itself so an
    /// invited specialist never shows a blank label.
    static func lens(_ tag: String, member: String) -> String {
        switch tag {
        case "MECHANISM": return "WILL IT WORK"
        case "COST": return "WHAT IT COSTS"
        case "WANT": return "WHAT YOU WANT"
        case "FINDING", "": return role(member)
        default: return tag
        }
    }

    // MARK: - Verdicts

    static func verdictWord(_ verdict: Verdict?) -> String {
        switch verdict {
        case .accept: return "YES"
        case .reject: return "NO"
        case .conditional: return "YES, IF"
        case .none: return ""
        }
    }

    // MARK: - The answer

    /// The headline, counted from the members themselves rather than parsed out
    /// of the engine's tally string. "MAJORITY — NO  (0A · 1C · 2R)" tells you
    /// nothing unless you already know what the letters mean.
    static func answer(units: [Council.Unit], outcome: String, fallback: String) -> String {
        // "hello" is not a question and the engine says so. It should read as
        // the machine shrugging, not as a failure.
        if outcome == "noise" { return "THAT WASN'T A QUESTION" }

        let stances = units.compactMap { unit -> String? in
            guard let position = unit.position, !position.failed else { return nil }
            if let verdict = position.verdictKey { return verdictWord(verdict) }
            if let option = position.option { return option.uppercased() }
            if let recommendation = position.recommendation { return recommendation.uppercased() }
            return nil
        }
        guard stances.count >= 2 else {
            return fallback.isEmpty ? "THE COUNCIL COULD NOT ANSWER" : fallback.uppercased()
        }

        let tally = Dictionary(grouping: stances, by: { $0 }).mapValues(\.count)
        guard let (winner, count) = tally.max(by: { $0.value < $1.value }) else { return fallback }
        let total = stances.count
        let picking = units.first?.position?.option != nil || units.first?.position?.recommendation != nil

        // Everybody landed somewhere different: there is no majority to report.
        if tally.count == total && total > 2 {
            return "ALL \(total) SAID SOMETHING DIFFERENT"
        }
        if count == total {
            return picking ? "ALL \(total) PICKED \(winner)" : "ALL \(total) SAY \(winner)"
        }
        switch outcome {
        case "conviction":
            return "THEY SPLIT. THE STRONGEST FEELING WON: \(winner)"
        case "tiebreak", "deadlock", "split":
            return "THEY SPLIT. CASPER BROKE THE TIE: \(winner)"
        default:
            return picking ? "\(count) OF \(total) PICKED \(winner)" : "\(count) OF \(total) SAY \(winner)"
        }
    }

    /// The small line under the answer, saying how they got there.
    static func howTheyDecided(_ outcome: String) -> String {
        switch outcome {
        case "consensus", "picks": return "they all agreed"
        case "majority": return "one of them disagreed"
        case "conviction": return "it was even, so the strongest conviction won"
        case "tiebreak", "deadlock", "split": return "it was even, so the one who reads what you want decided"
        case "incomplete": return "not enough of them answered"
        case "noise": return "ask me something you cannot decide"
        default: return ""
        }
    }

    // MARK: - Status

    static func status(_ phase: Council.Phase) -> (kanji: String, english: String) {
        switch phase {
        case .idle: return ("待機", "READY")
        case .warming: return ("起動中", "WAKING UP")
        case let .deliberating(round):
            return round > 1 ? ("討論中", "ARGUING") : ("審議中", "THINKING")
        case .resolved: return ("決議", "DECIDED")
        case .failed: return ("応答なし", "SOMETHING BROKE")
        }
    }

    /// What a single unit is doing, in a word.
    static func unitState(_ position: Position?) -> (kanji: String, english: String) {
        guard let position else { return ("待機", "WAITING") }
        if position.failed { return ("応答なし", "NO ANSWER") }
        if let verdict = position.verdictKey { return (verdict.plate, verdictWord(verdict)) }
        if let option = position.option { return ("選択", option.uppercased()) }
        if let recommendation = position.recommendation { return ("提案", recommendation.uppercased()) }
        return ("審議中", "THINKING")
    }

    // MARK: - Prompts and empty states

    static let tagline = "THREE MINDS · ONE ANSWER"

    static func emptyState(_ phase: Council.Phase) -> String {
        switch phase {
        case .warming: return "WAKING UP THE THREE MINDS"
        case .deliberating: return "THEY ARE READING YOUR QUESTION"
        default: return "ASK ANYTHING YOU CANNOT DECIDE. THEY ALWAYS GIVE YOU AN ANSWER."
        }
    }

    static let placeholder = "what can't you decide?"
    static let askButton = "ASK THEM"
    static let stopButton = "STOP"
    static let replayHint = "click to see it again"
    static let changedMind = "CHANGED THEIR MIND"
    static let onlyIf = "ONLY IF"

    /// How strongly a member holds their answer. The engine calls it
    /// confidence on a 1 to 5 scale; nobody needs the number.
    static func conviction(_ level: Int?) -> String {
        switch level ?? 0 {
        case 5: return "CERTAIN"
        case 4: return "PRETTY SURE"
        case 3: return "LEANING"
        case 2: return "NOT SURE"
        case 1: return "BARELY"
        default: return ""
        }
    }
}

import Foundation

/// One line of `magi stream`. Mirrors `magi/stream.py`; the protocol version is
/// asserted on both sides so a rename there fails loudly here instead of
/// silently rendering blank panels.
enum ProtocolVersion {
    static let expected = 1
}

enum Verdict: String, Codable {
    case accept = "ACCEPT"
    case reject = "REJECT"
    case conditional = "CONDITIONAL"

    /// The display speaks in plates, not words.
    var plate: String {
        switch self {
        case .accept: return "可決"
        case .reject: return "否決"
        case .conditional: return "条件付"
        }
    }

    var word: String {
        switch self {
        case .accept: return "YES"
        case .reject: return "NO"
        case .conditional: return "ONLY IF"
        }
    }
}

/// A member's stance at a point in the deliberation.
struct Position: Codable, Equatable {
    var reasoning: String = ""
    var finding: String = ""
    var lens: String = ""
    var confidence: Int?
    var verdictKey: Verdict?
    var option: String?
    var recommendation: String?
    var condition: String?
    var failed: Bool = false
    var error: String?
    var response: String = ""
    var changed: Bool = false

    enum CodingKeys: String, CodingKey {
        case reasoning, finding, lens, confidence, option, recommendation
        case condition, failed, error, response, changed
        case verdictKey = "verdict_key"
    }

    /// What the unit panel shows on its plate.
    var plate: String {
        if failed { return "応答なし" }
        if let verdictKey { return verdictKey.plate }
        if option != nil { return "選択" }
        if recommendation != nil { return "提案" }
        return "審議中"
    }

    /// The one line under the plate.
    var detail: String {
        if failed { return error ?? "ERROR" }
        if let verdictKey { return verdictKey.word }
        if let option { return option }
        if let recommendation { return recommendation }
        return ""
    }
}

/// Events arrive in the order the council produces them.
enum MagiEvent {
    case council(models: [String: String], version: String, protocolVersion: Int)
    case warming(member: String, state: String)
    case intake(mode: String, options: [String], decision: String)
    case round(Int)
    case vote(member: String, position: Position)
    case revote(member: String, position: Position)
    case rebuttal(member: String, round: Int, position: Position)
    case verdict(outcome: String, synthesis: String, positions: [String: Position])
    case failure(message: String)
    case end
    /// An event type this build does not know. Ignored on purpose: the stream
    /// is documented as gaining fields and types over time.
    case unknown(String)
}

enum EventDecoder {
    static func decode(line: String) -> MagiEvent? {
        guard let data = line.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let kind = object["event"] as? String
        else { return nil }

        switch kind {
        case "council":
            return .council(
                models: object["models"] as? [String: String] ?? [:],
                version: object["version"] as? String ?? "?",
                protocolVersion: object["protocol"] as? Int ?? 0
            )
        case "warming":
            return .warming(
                member: object["member"] as? String ?? "",
                state: object["state"] as? String ?? "loading"
            )
        case "intake":
            return .intake(
                mode: object["mode"] as? String ?? "decision",
                options: object["options"] as? [String] ?? [],
                decision: object["decision"] as? String ?? ""
            )
        case "round":
            return .round(object["round"] as? Int ?? 1)
        case "vote", "revote", "rebuttal":
            let member = object["member"] as? String ?? ""
            let position = decodePosition(object)
            if kind == "vote" { return .vote(member: member, position: position) }
            if kind == "revote" { return .revote(member: member, position: position) }
            return .rebuttal(member: member, round: object["round"] as? Int ?? 2, position: position)
        case "verdict":
            var positions: [String: Position] = [:]
            for (name, raw) in (object["positions"] as? [String: [String: Any]] ?? [:]) {
                positions[name] = decodePosition(raw)
            }
            return .verdict(
                outcome: object["outcome"] as? String ?? "incomplete",
                synthesis: object["synthesis"] as? String ?? "",
                positions: positions
            )
        case "error":
            return .failure(message: object["message"] as? String ?? "unknown error")
        case "end":
            return .end
        default:
            return .unknown(kind)
        }
    }

    /// Hand-decoded rather than via Codable because the position fields are
    /// inlined into the event object, and half of them are absent depending on
    /// the mode. A missing key is a normal state here, not a decoding failure.
    private static func decodePosition(_ object: [String: Any]) -> Position {
        var position = Position()
        position.reasoning = object["reasoning"] as? String ?? ""
        position.finding = object["finding"] as? String ?? ""
        position.lens = object["lens"] as? String ?? ""
        position.confidence = object["confidence"] as? Int
        if let key = object["verdict_key"] as? String { position.verdictKey = Verdict(rawValue: key) }
        position.option = object["option"] as? String
        position.recommendation = object["recommendation"] as? String
        position.condition = object["condition"] as? String
        position.failed = object["failed"] as? Bool ?? false
        position.error = object["error"] as? String
        position.response = object["response"] as? String ?? ""
        position.changed = object["changed"] as? Bool ?? false
        return position
    }
}

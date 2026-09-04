import Foundation
import SwiftUI

/// Drives `magi stream` and turns its output into the state the display draws.
///
/// The app owns no council logic. Everything about how the three members argue,
/// what they are allowed to say and how a tie breaks lives in the Python engine,
/// which is also what the eval harness measures. This class knows only how to
/// spawn that engine, read lines, and hold the result.
@MainActor
final class Council: ObservableObject {

    enum Phase: Equatable {
        case idle
        case warming
        case deliberating(round: Int)
        case resolved
        case failed(String)
    }

    struct Unit: Identifiable, Equatable {
        let id: String
        var model: String
        var position: Position?
        var reporting: Bool = false      // just landed; drives the flash
        var ready: Bool = false

        var name: String { id }
        var number: String {
            switch id {
            case "MELCHIOR": return "1"
            case "BALTHASAR": return "2"
            case "CASPER": return "3"
            default: return "•"
            }
        }
    }

    @Published private(set) var units: [Unit] = []
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var mode: String = "decision"
    @Published private(set) var options: [String] = []
    /// When the user typed a statement, the yes/no decision the engine read
    /// in it. Empty when they asked a question outright.
    @Published private(set) var decision: String = ""
    /// The journal thread this conversation belongs to, once the engine has
    /// named it. The HISTORY list highlights it.
    @Published private(set) var thread: String?
    @Published private(set) var turn: Int = 0
    @Published private(set) var question: String = ""
    @Published private(set) var synthesis: String = ""
    @Published private(set) var outcome: String = ""
    @Published private(set) var verdict: Verdict?
    @Published private(set) var engineVersion: String = ""
    @Published private(set) var transcript: [TranscriptLine] = []

    /// For the title bar: how long the last deliberation took and how many
    /// rounds it ran. Measured here rather than reported by the engine so the
    /// wire format stays untouched.
    @Published private(set) var startedAt: Date?
    @Published private(set) var finishedAt: Date?
    @Published private(set) var rounds: Int = 0

    struct TranscriptLine: Identifiable, Equatable {
        let id = UUID()
        let member: String
        let round: Int
        let text: String
        let finding: String
        let lens: String
        let position: Position
    }

    private var process: Process?
    private var input: FileHandle?
    private var task: Task<Void, Never>?

    /// A turn is in flight. The engine process itself outlives turns: it is
    /// one session that keeps the thread, so "running" cannot mean "alive".
    @Published private(set) var isRunning = false

    init() {
        loadRoster()
    }

    /// A council frozen in a given state, for the offline renderer. Not used by
    /// the running app; it exists so the interface can be looked at without
    /// spawning the engine or taking over somebody's screen.
    private init(preview: Void) {}

    static func preview(_ state: String) -> Council {
        let council = Council(preview: ())
        let models = ["MELCHIOR": "qwen3:4b", "BALTHASAR": "dolphin3:8b", "CASPER": "hermes3:8b"]
        council.units = ["MELCHIOR", "BALTHASAR", "CASPER"].map { Unit(id: $0, model: models[$0] ?? "") }

        func position(_ verdict: Verdict, _ confidence: Int, _ text: String, _ finding: String, _ lens: String) -> Position {
            var p = Position()
            p.verdictKey = verdict
            p.confidence = confidence
            p.reasoning = text
            p.finding = finding
            p.lens = lens
            return p
        }

        let melchior = position(.reject, 4,
            "There is no mechanism here. Dropping out removes the structure without putting anything in its place, and nothing in the question describes what replaces it.",
            "no path from leaving to shipping", "MECHANISM")
        let balthasar = position(.reject, 5,
            "The cost is the option itself. Leaving now closes a door that is cheap to hold open and expensive to reopen later.",
            "an option that is cheap to keep", "COST")
        let casper = position(.accept, 3,
            "You want to go. The question is phrased as permission, not as a decision, and that tells me you have already made it.",
            "you already decided", "WANT")

        switch state {
        case "idle":
            council.question = ""
            council.phase = .idle
        case "thinking":
            council.question = "should i drop out of school to build apps"
            council.phase = .deliberating(round: 1)
            council.units[0].position = melchior
            council.units[1].reporting = true
            council.transcript = [
                TranscriptLine(member: "MELCHIOR", round: 1, text: melchior.reasoning,
                               finding: melchior.finding, lens: melchior.lens, position: melchior),
            ]
        default:
            council.question = "should i drop out of school to build apps"
            council.phase = .resolved
            council.units[0].position = melchior
            council.units[1].position = balthasar
            council.units[2].position = casper
            council.outcome = "majority"
            council.synthesis = "MAJORITY — NO  (1A · 0C · 2R)"
            council.rounds = 2
            council.startedAt = Date(timeIntervalSinceNow: -31.4)
            council.finishedAt = Date()
            council.verdict = .reject
            council.transcript = [
                TranscriptLine(member: "MELCHIOR", round: 1, text: melchior.reasoning,
                               finding: melchior.finding, lens: melchior.lens, position: melchior),
                TranscriptLine(member: "BALTHASAR", round: 1, text: balthasar.reasoning,
                               finding: balthasar.finding, lens: balthasar.lens, position: balthasar),
                TranscriptLine(member: "CASPER", round: 1, text: casper.reasoning,
                               finding: casper.finding, lens: casper.lens, position: casper),
            ]
        }
        return council
    }

    /// Ask the engine who is seated so the display comes up populated rather
    /// than blank. Cheap and synchronous-ish: it is one process that prints a
    /// line and exits, and a failure just leaves the units to arrive with the
    /// first question.
    private func loadRoster() {
        guard let engine = Self.enginePath() else { return }
        Task.detached { [weak self] in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: engine)
            process.arguments = ["roster"]
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = Pipe()
            guard (try? process.run()) != nil else { return }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard let line = String(data: data, encoding: .utf8),
                  case let .council(models, _, _)? = EventDecoder.decode(line: line.trimmingCharacters(in: .whitespacesAndNewlines))
            else { return }
            await MainActor.run { self?.seat(models) }
        }
    }

    private func seat(_ models: [String: String]) {
        let order = ["MELCHIOR", "BALTHASAR", "CASPER"]
        let sorted = order.filter { models[$0] != nil } + models.keys.filter { !order.contains($0) }.sorted()
        // Keep any positions already on screen if the roster is unchanged.
        units = sorted.map { name in
            var unit = units.first(where: { $0.id == name }) ?? Unit(id: name, model: models[name] ?? "")
            unit.model = models[name] ?? unit.model
            return unit
        }
    }

    /// The engine binary. Prefers a pinned override, then the pipx install,
    /// then whatever is on PATH, so a dev checkout and a normal install both
    /// work without editing anything.
    static func enginePath() -> String? {
        if let override = UserDefaults.standard.string(forKey: "enginePath"),
           FileManager.default.isExecutableFile(atPath: override) {
            return override
        }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let candidates = [
            "\(home)/.local/bin/magi",
            "\(home)/Projects/Mac/magi/.venv/bin/magi",
            "/opt/homebrew/bin/magi",
            "/usr/local/bin/magi",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    func ask(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isRunning else { return }
        guard ensureSession() else { return }
        isRunning = true
        startedAt = Date()
        finishedAt = nil
        if thread == nil { reset(question: trimmed) } else { phase = .deliberating(round: 1) }
        send(trimmed)
    }

    /// Drop the thread. The next question starts a fresh conversation.
    func newThread() {
        guard !isRunning else { return }
        if process != nil { send("/new") }
        thread = nil
        turn = 0
        reset(question: "")
        phase = .idle
    }

    /// Reopen a past conversation: shown at once from the journal, and the
    /// engine rebuilds its memory of it so the next line continues it.
    func resume(_ conversation: Journal.Thread) {
        guard !isRunning else { return }
        show(conversation)
        guard ensureSession() else { return }
        send("/resume \(conversation.id)")
    }

    private func show(_ conversation: Journal.Thread) {
        let first = conversation.first
        let last = conversation.last
        reset(question: first.question)
        thread = conversation.id
        turn = conversation.turns.count
        mode = first.mode
        decision = first.decision
        for entry in conversation.turns {
            // The opening question is the YOU ASKED line; later turns are cards.
            if entry.turn > 1 {
                transcript.append(TranscriptLine(member: "YOU", round: entry.turn, text: entry.question,
                                                 finding: "", lens: "", position: Position()))
            }
            // Core members first, in seat order, then any specialist.
            let members = ["MELCHIOR", "BALTHASAR", "CASPER"]
                + entry.positions.keys.filter { !["MELCHIOR", "BALTHASAR", "CASPER"].contains($0) }.sorted()
            for member in members {
                guard let position = entry.positions[member] else { continue }
                transcript.append(TranscriptLine(member: member, round: 1, text: position.reasoning,
                                                 finding: position.finding, lens: position.lens,
                                                 position: position))
            }
        }
        for (name, position) in last.positions {
            if let index = units.firstIndex(where: { $0.id == name }) { units[index].position = position }
        }
        synthesis = last.synthesis
        outcome = last.outcome
        verdict = Self.decidedVerdict(synthesis: last.synthesis, positions: last.positions)
        rounds = 0
        startedAt = nil
        phase = .resolved
    }

    /// Start the engine session if it is not already up. One process for the
    /// life of the conversation; it reads a line per turn on stdin.
    private func ensureSession() -> Bool {
        if process != nil { return true }
        guard let engine = Self.enginePath() else {
            phase = .failed("magi engine not found. Install it with: pipx install magi-council")
            return false
        }
        phase = .warming

        let process = Process()
        process.executableURL = URL(fileURLWithPath: engine)
        process.arguments = ["stream"]
        // The engine's own console tones would double up with the app's.
        var env = ProcessInfo.processInfo.environment
        env["MAGI_SOUND"] = "0"
        env["PYTHONUNBUFFERED"] = "1"
        process.environment = env

        let pipe = Pipe()
        let stdin = Pipe()
        process.standardOutput = pipe
        process.standardInput = stdin
        process.standardError = Pipe()
        self.process = process
        self.input = stdin.fileHandleForWriting

        do {
            try process.run()
        } catch {
            finish(error: "could not start the engine: \(error.localizedDescription)")
            return false
        }

        task = Task.detached { [weak self] in
            // Line-buffered by hand: availableData arrives in arbitrary chunks
            // and a JSON event split across two reads must not be dropped.
            var buffer = Data()
            let handle = pipe.fileHandleForReading
            while true {
                let chunk = handle.availableData
                if chunk.isEmpty { break }
                buffer.append(chunk)
                while let newline = buffer.firstIndex(of: 0x0A) {
                    let lineData = buffer[buffer.startIndex..<newline]
                    buffer.removeSubrange(buffer.startIndex...newline)
                    guard let line = String(data: lineData, encoding: .utf8),
                          let event = EventDecoder.decode(line: line) else { continue }
                    await MainActor.run { self?.apply(event) }
                }
            }
            process.waitUntilExit()
            await MainActor.run { self?.processEnded(code: process.terminationStatus) }
        }
        return true
    }

    private func send(_ line: String) {
        guard let input, let data = (line.replacingOccurrences(of: "\n", with: " ") + "\n").data(using: .utf8) else { return }
        try? input.write(contentsOf: data)
    }

    func cancel() {
        process?.terminate()
        task?.cancel()
        process = nil
        input = nil
        task = nil
        isRunning = false
        if case .resolved = phase {} else { phase = .idle }
    }

    private func reset(question: String) {
        self.question = question
        synthesis = ""
        outcome = ""
        verdict = nil
        transcript = []
        options = []
        decision = ""
        rounds = 0
        finishedAt = nil
        for index in units.indices {
            units[index].position = nil
            units[index].reporting = false
        }
    }

    private func apply(_ event: MagiEvent) {
        switch event {
        case let .council(models, version, protocolVersion):
            engineVersion = version
            if protocolVersion != ProtocolVersion.expected {
                // Not fatal: unknown fields are ignored by design. Worth
                // surfacing, because a mismatch explains a half-empty display.
                synthesis = "engine protocol \(protocolVersion), app expects \(ProtocolVersion.expected)"
            }
            seat(models)

        case let .warming(member, state):
            if let index = units.firstIndex(where: { $0.id == member }) {
                units[index].ready = (state == "ready")
            }

        case let .turn(id, number, text):
            if number <= 1 || thread != id {
                reset(question: text)
            } else {
                // A follow-up: the argument continues under the same question.
                transcript.append(TranscriptLine(member: "YOU", round: number, text: text,
                                                 finding: "", lens: "", position: Position()))
                for index in units.indices { units[index].reporting = false }
            }
            thread = id
            turn = number
            rounds = 0
            verdict = nil
            phase = .deliberating(round: 1)

        case let .thread(id, _):
            thread = id

        case let .intake(mode, options, decision):
            self.mode = mode
            self.options = options
            if !decision.isEmpty { self.decision = decision }
            rounds = max(rounds, 1)
            phase = .deliberating(round: 1)

        case let .round(number):
            rounds = max(rounds, number)
            phase = .deliberating(round: number)

        case let .vote(member, position), let .revote(member, position):
            update(member: member, position: position, round: 1, body: position.reasoning)

        case let .rebuttal(member, round, position):
            update(member: member, position: position, round: round,
                   body: position.response.isEmpty ? position.reasoning : position.response)

        case let .verdict(outcome, synthesis, positions):
            self.outcome = outcome
            self.synthesis = synthesis
            for (name, position) in positions {
                if let index = units.firstIndex(where: { $0.id == name }) {
                    units[index].position = position
                }
            }
            verdict = Self.decidedVerdict(synthesis: synthesis, positions: positions)
            finishedAt = Date()
            isRunning = false
            phase = .resolved

        case let .failure(message):
            finish(error: message)

        case .end, .unknown:
            break
        }
    }

    private func update(member: String, position: Position, round: Int, body: String) {
        guard let index = units.firstIndex(where: { $0.id == member }) else { return }
        units[index].position = position
        units[index].reporting = true
        if !body.isEmpty {
            transcript.append(TranscriptLine(member: member, round: round, text: body,
                                             finding: position.finding, lens: position.lens,
                                             position: position))
        }
        // The flash is a moment, not a state.
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 700_000_000)
            await MainActor.run {
                guard let self, let index = self.units.firstIndex(where: { $0.id == member }) else { return }
                self.units[index].reporting = false
            }
        }
    }

    /// The outcome says how the council decided; the plate must say what it
    /// decided, so a unanimous NO is stamped 否決 rather than taking its plate
    /// from the word "consensus".
    static func decidedVerdict(synthesis: String, positions: [String: Position]) -> Verdict? {
        let upper = synthesis.uppercased()
        for (word, verdict) in [("ONLY IF", Verdict.conditional), ("YES", .accept), ("NO", .reject)] {
            for prefix in ["CONSENSUS", "MAJORITY", "CALL"] where upper.hasPrefix(prefix) {
                let body = upper.dropFirst(prefix.count).trimmingCharacters(in: CharacterSet(charactersIn: " —-·"))
                if body.hasPrefix(word) { return verdict }
            }
        }
        // Choice and open modes have no verdict word; fall back to the tally.
        let verdicts = positions.values.compactMap(\.verdictKey)
        guard !verdicts.isEmpty else { return nil }
        let counts = Dictionary(grouping: verdicts, by: { $0 }).mapValues(\.count)
        return counts.max { $0.value < $1.value }?.key
    }

    private func finish(error: String) {
        phase = .failed(error)
        isRunning = false
    }

    private func processEnded(code: Int32) {
        process = nil
        input = nil
        task = nil
        let wasRunning = isRunning
        isRunning = false
        if case .resolved = phase { return }
        if case .failed = phase { return }
        phase = (code == 0 && !wasRunning) ? .idle : .failed("the engine exited with code \(code)")
    }
}

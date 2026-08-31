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
    @Published private(set) var question: String = ""
    @Published private(set) var synthesis: String = ""
    @Published private(set) var outcome: String = ""
    @Published private(set) var verdict: Verdict?
    @Published private(set) var engineVersion: String = ""
    @Published private(set) var transcript: [TranscriptLine] = []

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
    private var task: Task<Void, Never>?

    /// Published, not computed off `process`.
    ///
    /// This was `process != nil`, which meant the input re-enabled only if
    /// something else published a change afterwards. It never did: the last
    /// published change is the verdict, which lands while the process is still
    /// alive, and clearing the process a moment later published nothing. So
    /// the field stayed disabled after the first question and the app could
    /// only be asked once per launch.
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

        guard let engine = Self.enginePath() else {
            phase = .failed("magi engine not found. Install it with: pipx install magi-council")
            return
        }

        reset(question: trimmed)
        phase = .warming

        let process = Process()
        process.executableURL = URL(fileURLWithPath: engine)
        process.arguments = ["stream", trimmed]
        // The engine's own console tones would double up with the app's.
        var env = ProcessInfo.processInfo.environment
        env["MAGI_SOUND"] = "0"
        env["PYTHONUNBUFFERED"] = "1"
        process.environment = env

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()
        self.process = process
        isRunning = true

        task = Task.detached { [weak self] in
            do {
                try process.run()
            } catch {
                await MainActor.run { self?.finish(error: "could not start the engine: \(error.localizedDescription)") }
                return
            }
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
    }

    func cancel() {
        process?.terminate()
        task?.cancel()
        process = nil
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

        case let .intake(mode, options):
            self.mode = mode
            self.options = options
            phase = .deliberating(round: 1)

        case let .round(number):
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
        process = nil
        task = nil
        isRunning = false
    }

    private func processEnded(code: Int32) {
        process = nil
        task = nil
        isRunning = false
        if case .resolved = phase { return }
        if case .failed = phase { return }
        phase = code == 0 ? .idle : .failed("the engine exited with code \(code)")
    }
}

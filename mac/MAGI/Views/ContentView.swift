import SwiftUI

/// The window from the "MAGI Mac - Nerv" design: a title bar, a sidebar with
/// the three seats and the record, and a main column with the question, the
/// answer banner, what each member said, and the argue-back line.
struct ContentView: View {
    @StateObject private var council: Council

    init(previewCouncil: Council? = nil) {
        _council = StateObject(wrappedValue: previewCouncil ?? Council())
    }

    @StateObject private var audio = Audio()
    @State private var draft = ""
    @State private var stampShowing = false
    @State private var journal: [Journal.Entry] = []
    @FocusState private var inputFocused: Bool

    /// How long the full-screen answer holds before it clears. Adjustable
    /// because the right answer is taste, and because a fixed two-second
    /// window is impossible to screenshot:
    ///   defaults write io.zeroarch.magi stampSeconds 8
    @AppStorage("stampSeconds") private var stampSeconds: Double = 2.6

    var body: some View {
        ZStack {
            Theme.void.ignoresSafeArea()

            VStack(spacing: 0) {
                TitleBar(council: council, journalCount: journal.count)

                HStack(spacing: 0) {
                    Sidebar(council: council, record: Journal.featured(journal))
                        .frame(width: 336)
                    Rectangle().fill(Theme.hairline).frame(width: 1)
                    MainColumn(council: council, draft: $draft, focused: $inputFocused,
                               replay: replayStamp)
                }
            }

            if stampShowing {
                VerdictStamp(verdict: council.verdict,
                             units: council.units,
                             synthesis: council.synthesis,
                             outcome: council.outcome)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Theme.void.opacity(0.94))
                    .contentShape(Rectangle())
                    .onTapGesture { withAnimation(.easeOut(duration: 0.28)) { stampShowing = false } }
                    .transition(.opacity)
                    .zIndex(10)
            }
        }
        .frame(minWidth: 1100, minHeight: 760)
        .preferredColorScheme(.dark)
        .onAppear {
            journal = Journal.load()
            // Focus set during the first layout pass lands on a field that is
            // still being built, and the first characters typed go nowhere.
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: 150_000_000)
                inputFocused = true
            }
        }
        .onChange(of: council.transcript.count) { _, count in
            if count > 0 { audio.play(.report) }
        }
        .onChange(of: council.phase) { _, phase in
            switch phase {
            case .warming:
                audio.play(.boot)
            case .resolved:
                audio.playOutcome(council.outcome)
                // The engine appends to the journal as it finishes; reread so
                // the count and the record keep up.
                journal = Journal.load()
                // Nothing was decided, so nothing gets stamped across the
                // screen. A full-screen verdict for "hello" reads as an error.
                guard council.outcome != "noise" else { break }
                withAnimation(.easeOut(duration: 0.2)) { stampShowing = true }
                scheduleStampDismiss()
            case .failed:
                audio.play(.error)
            default:
                break
            }
            switch phase {
            case .warming, .deliberating:
                break
            default:
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: 120_000_000)
                    inputFocused = true
                }
            }
        }
    }

    private func replayStamp() {
        withAnimation(.easeOut(duration: 0.2)) { stampShowing = true }
        scheduleStampDismiss()
    }

    private func scheduleStampDismiss() {
        let seconds = max(0.5, stampSeconds)
        Task {
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            withAnimation(.easeOut(duration: 0.45)) { stampShowing = false }
        }
    }
}

// MARK: - Title bar

/// Traffic lights, the wordmark, the council line, and the status pair on
/// the right: elapsed time and rounds in an outlined cell, the state in a
/// solid orange one.
private struct TitleBar: View {
    @ObservedObject var council: Council
    let journalCount: Int

    var body: some View {
        HStack(spacing: 14) {
            // The window's own traffic lights sit here; leave them room.
            Color.clear.frame(width: 58, height: 1)

            Rectangle().fill(Theme.rule).frame(width: 1, height: 18)

            Text("MAGI")
                .font(Theme.display(17))
                .tracking(6)
                .foregroundStyle(Theme.orange)

            Caption(text: councilLine, size: 10.5, tracking: 1.6)

            Spacer()

            HStack(spacing: 0) {
                if let timing {
                    Caption(text: timing, size: 10, tracking: 1.4)
                        .padding(.horizontal, 10)
                        .frame(height: 26)
                        .overlay {
                            Rectangle().stroke(Theme.rule, lineWidth: 1)
                                .padding(.trailing, -1)
                        }
                }
                let status = Plain.status(council.phase)
                Text("\(status.kanji) \(status.english)")
                    .font(Theme.display(13, weight: .semibold))
                    .tracking(2.4)
                    .foregroundStyle(Theme.void)
                    .padding(.horizontal, 12)
                    .frame(height: 26)
                    .background(Theme.orange)
            }
        }
        .padding(.horizontal, 14)
        .frame(height: 46)
        .background(Theme.bar)
        .overlay(alignment: .bottom) { Rectangle().fill(Theme.hairline).frame(height: 1) }
    }

    private var councilLine: String {
        let seat = council.units.contains { $0.model.hasSuffix(":cloud") } ? "CLOUD" : "LOCAL"
        return journalCount > 0 ? "COUNCIL \(journalCount) · \(seat)" : "COUNCIL · \(seat)"
    }

    private var timing: String? {
        guard let start = council.startedAt else { return nil }
        let end = council.finishedAt ?? Date()
        let seconds = end.timeIntervalSince(start)
        let rounds = council.rounds
        let roundsText = rounds == 1 ? "1 ROUND" : "\(rounds) ROUNDS"
        return String(format: "%.1fs · %@", seconds, roundsText)
    }
}

// MARK: - Sidebar

private struct Sidebar: View {
    @ObservedObject var council: Council
    let record: Journal.Entry?

    private var reported: Int {
        council.units.filter { unit in
            guard let position = unit.position else { return false }
            return position.verdictKey != nil || position.option != nil
                || position.recommendation != nil || position.failed
        }.count
    }

    private var reportLine: (text: String, color: Color) {
        let total = council.units.count
        switch council.phase {
        case .idle: return ("STANDING BY", Theme.steel)
        case .warming: return ("WAKING UP", Theme.orange)
        case .deliberating:
            return reported == total && total > 0
                ? ("ALL REPORTED", Theme.mint)
                : ("\(reported) OF \(total) REPORTED", Theme.orange)
        case .resolved: return ("ALL REPORTED", Theme.mint)
        case .failed: return ("NO ANSWER", Theme.red)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Caption(text: "THE THREE")
                Spacer()
                Caption(text: reportLine.text, color: reportLine.color, size: 10, tracking: 1.4)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 14)
            .overlay(alignment: .bottom) { Rectangle().fill(Theme.hairline).frame(height: 1) }

            VStack(spacing: 12) {
                ForEach(council.units) { unit in
                    UnitPanel(unit: unit)
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 16)

            if let record {
                VStack(alignment: .leading, spacing: 8) {
                    Caption(text: "RECORD")
                    RecordCard(entry: record)
                }
                .padding(.horizontal, 18)
                .padding(.top, 6)
                .padding(.bottom, 16)
            }

            Spacer(minLength: 0)

            Caption(text: "+ INVITE A SPECIALIST", size: 10, tracking: 1.6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 18)
                .padding(.vertical, 14)
                .overlay(alignment: .top) { Rectangle().fill(Theme.hairline).frame(height: 1) }
                .help("Run `magi ask --with <specialist>` from the terminal. Coming to the app.")
        }
        .background(Theme.panel)
    }
}

/// One past deliberation: when and what was asked, then what they said and
/// what the user actually did.
private struct RecordCard: View {
    let entry: Journal.Entry

    private static let day: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private var theySaid: String {
        let upper = entry.synthesis.uppercased()
        if upper.contains("ONLY IF") { return "they said only if" }
        if upper.hasPrefix("CONSENSUS") || upper.hasPrefix("MAJORITY") || upper.hasPrefix("CALL") {
            if upper.contains("NO") { return "they said no" }
            if upper.contains("YES") { return "they said yes" }
        }
        if entry.outcome == "picks" || entry.outcome == "choice" { return "they picked" }
        return "they answered"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("\(Self.day.string(from: entry.date)) · \(entry.question)")
                .font(Theme.mono(11))
                .foregroundStyle(Theme.record)
                .lineLimit(2)
            if let outcome = entry.userOutcome, !outcome.isEmpty {
                Text("\(theySaid) · \(outcome)")
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.steel)
                    .lineLimit(2)
            } else {
                Text("\(theySaid) · what did you do?")
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.steel)
                    .lineLimit(2)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(Rectangle().stroke(Theme.hairline, lineWidth: 1))
    }
}

// MARK: - Main column

private struct MainColumn: View {
    @ObservedObject var council: Council
    @Binding var draft: String
    @FocusState.Binding var focused: Bool
    let replay: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 14) {
                Caption(text: askedLine, size: 11, tracking: 1.4)
                    .lineLimit(1)
                    .truncationMode(.tail)

                if case .resolved = council.phase {
                    VerdictBanner(verdict: council.verdict,
                                  units: council.units,
                                  synthesis: council.synthesis,
                                  outcome: council.outcome)
                        .onTapGesture(perform: replay)
                }

                if case let .failed(message) = council.phase {
                    HStack(spacing: 12) {
                        Text("PROBLEM")
                            .font(Theme.display(13))
                            .tracking(2.4)
                            .foregroundStyle(Theme.void)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(Theme.red)
                        Text(message)
                            .font(Theme.mono(12))
                            .foregroundStyle(Theme.prose)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 26)
            .padding(.top, 22)

            TranscriptScroll(council: council)

            InputBar(draft: $draft, council: council, focused: $focused)
        }
        .background(Theme.void)
    }

    private var askedLine: String {
        council.question.isEmpty
            ? Plain.emptyState(council.phase)
            : "YOU ASKED — \(council.question.uppercased())"
    }
}

/// The answer: the word in a solid orange block, the count in condensed
/// caps beside it, and the kanji plate with the split on the right.
private struct VerdictBanner: View {
    let verdict: Verdict?
    let units: [Council.Unit]
    let synthesis: String
    let outcome: String

    private var color: Color { verdict == nil ? Theme.orange : Theme.orange }
    private var word: String {
        let w = Plain.verdictWord(verdict)
        return w.isEmpty ? "DECIDED" : w
    }

    private var split: String {
        let verdicts = units.compactMap { $0.position?.verdictKey }
        guard !verdicts.isEmpty else { return "" }
        let counts = Dictionary(grouping: verdicts, by: { $0 }).mapValues(\.count)
        return counts.sorted { $0.value > $1.value }
            .map { "\($0.value) \(Plain.verdictWord($0.key))" }
            .joined(separator: " · ")
    }

    var body: some View {
        HStack(spacing: 0) {
            Text(word)
                .font(Theme.display(word.count > 3 ? 44 : 74))
                .tracking(2)
                .foregroundStyle(Theme.void)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .padding(.horizontal, 28)
                .frame(maxHeight: .infinity)
                .background(color)

            VStack(alignment: .leading, spacing: 9) {
                Text(Plain.answer(units: units, outcome: outcome, fallback: synthesis))
                    .font(Theme.display(27, weight: .semibold))
                    .tracking(1.6)
                    .foregroundStyle(Theme.bone)
                    .lineLimit(2)
                    .minimumScaleFactor(0.7)
                let how = Plain.howTheyDecided(outcome)
                if !how.isEmpty {
                    Text(how)
                        .font(Theme.mono(12))
                        .foregroundStyle(Theme.steel)
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 18)
            .frame(maxWidth: .infinity, alignment: .leading)

            VStack(spacing: 6) {
                Text(verdict?.plate ?? "決議")
                    .font(Theme.plate(30))
                    .tracking(4)
                    .foregroundStyle(color)
                if !split.isEmpty {
                    Caption(text: split, size: 9.5, tracking: 1.4)
                }
            }
            .frame(width: 112)
            .frame(maxHeight: .infinity)
            .overlay(alignment: .leading) { Rectangle().fill(Theme.rule).frame(width: 1) }
        }
        .fixedSize(horizontal: false, vertical: true)
        .overlay(Rectangle().stroke(color, lineWidth: 1))
        .contentShape(Rectangle())
        .help(Plain.replayHint)
    }
}

/// What they said, following the newest argument.
private struct TranscriptScroll: View {
    @ObservedObject var council: Council

    private var cards: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(council.transcript) { line in
                TranscriptCard(line: line, tag: Tally.tag(for: line, among: council.units))
                    .id(line.id)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 26)
        .padding(.vertical, 20)
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                cards
            }
            // The offline renderer draws nothing inside a ScrollView, so the
            // screenshot path lays the cards out flat.
            .overlay(alignment: .top) { if Preview.rendering { cards.background(Theme.void) } }
            .onChange(of: council.transcript.count) { _, _ in
                guard let last = council.transcript.last else { return }
                withAnimation(.easeOut(duration: 0.35)) {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
    }
}

private struct InputBar: View {
    @Binding var draft: String
    @ObservedObject var council: Council
    @FocusState.Binding var focused: Bool

    private var placeholder: String {
        if case .resolved = council.phase { return "argue back — they reconsider with what you add" }
        return Plain.placeholder
    }

    var body: some View {
        HStack(spacing: 14) {
            Text("❯")
                .font(Theme.display(16))
                .foregroundStyle(Theme.orange)

            TextField("", text: $draft, prompt: Text(placeholder).foregroundStyle(Theme.placeholder))
                .textFieldStyle(.plain)
                .font(Theme.mono(13))
                .foregroundStyle(Theme.bone)
                .focused($focused)
                .onSubmit(submit)
                .disabled(council.isRunning)

            if council.isRunning {
                Button(Plain.stopButton, action: council.cancel)
                    .buttonStyle(SolidButton(color: Theme.red))
            } else {
                Button("SEND", action: submit)
                    .buttonStyle(SolidButton(color: Theme.orange))
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(.horizontal, 26)
        .padding(.top, 16)
        .padding(.bottom, 20)
        .overlay(alignment: .top) { Rectangle().fill(Theme.hairline).frame(height: 1) }
        // The text line itself is 17 points tall, which is a nearly impossible
        // click target. The whole bar takes the click and hands focus over.
        .contentShape(Rectangle())
        .onTapGesture { focused = true }
    }

    private func submit() {
        let question = draft
        guard !question.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        council.ask(question)
        draft = ""
    }
}

struct SolidButton: ButtonStyle {
    var color: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.display(13, weight: .semibold))
            .tracking(2.4)
            .foregroundStyle(Theme.void)
            .padding(.horizontal, 18)
            .padding(.vertical, 9)
            .background(color.opacity(configuration.isPressed ? 0.75 : 1))
    }
}

import SwiftUI

struct ContentView: View {
    @StateObject private var council: Council

    init(previewCouncil: Council? = nil) {
        _council = StateObject(wrappedValue: previewCouncil ?? Council())
    }

    @StateObject private var audio = Audio()
    @State private var draft = ""
    @State private var stampShowing = false
    @FocusState private var inputFocused: Bool

    /// How long the full-screen answer holds before it clears. Adjustable
    /// because the right answer is taste, and because a fixed two-second
    /// window is impossible to screenshot:
    ///   defaults write io.zeroarch.magi stampSeconds 8
    @AppStorage("stampSeconds") private var stampSeconds: Double = 2.6

    var body: some View {
        ZStack {
            Theme.void.ignoresSafeArea()
            Schematic().ignoresSafeArea()

            VStack(spacing: 0) {
                HeaderBar(council: council)

                // The console does not scroll. Watching the three fill in is
                // the reason this is an app and not a terminal, and the first
                // build scrolled it away exactly when it mattered.
                MagiDisplay(council: council)
                    .padding(.horizontal, 18)
                    .padding(.top, 14)
                    .padding(.bottom, 10)

                if case .resolved = council.phase, !stampShowing {
                    AnswerBar(verdict: council.verdict,
                              units: council.units,
                              synthesis: council.synthesis,
                              outcome: council.outcome)
                        .padding(.horizontal, 26)
                        .padding(.bottom, 14)
                        .onTapGesture { replayStamp() }
                }

                if case let .failed(message) = council.phase {
                    HStack(spacing: 10) {
                        Plate(text: "PROBLEM", color: Theme.red, size: 11, tracking: 2)
                        Text(message)
                            .font(Theme.mono(11))
                            .foregroundStyle(Theme.bone.opacity(0.85))
                    }
                    .padding(.horizontal, 26)
                    .padding(.bottom, 12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                Rectangle().fill(Theme.orangeDim.opacity(0.5)).frame(height: 1)

                TranscriptScroll(lines: council.transcript, phase: council.phase)

                InputBar(draft: $draft, council: council, focused: $inputFocused)
            }

            ScreenGlass()

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
        .frame(minWidth: 1000, minHeight: 840)
        .preferredColorScheme(.dark)
        .onAppear { inputFocused = true }
        .onChange(of: council.transcript.count) { _, count in
            if count > 0 { audio.play(.report) }
        }
        .onChange(of: council.phase) { _, phase in
            switch phase {
            case .warming:
                audio.play(.boot)
            case .resolved:
                audio.playOutcome(council.outcome)
                withAnimation(.easeOut(duration: 0.2)) { stampShowing = true }
                scheduleStampDismiss()
            case .failed:
                audio.play(.error)
            default:
                break
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

/// The masthead: a solid orange band, black text cut out of it.
private struct HeaderBar: View {
    @ObservedObject var council: Council

    var body: some View {
        HStack(spacing: 0) {
            Text("MAGI")
                .font(Theme.display(27))
                .tracking(11)
                .foregroundStyle(Theme.void)
                .padding(.leading, 22)
                .padding(.trailing, 18)

            Text(Plain.tagline)
                .font(Theme.mono(9.5))
                .tracking(2.6)
                .foregroundStyle(Theme.void.opacity(0.72))

            Spacer()

            if !council.question.isEmpty {
                Text(council.question.uppercased())
                    .font(Theme.mono(10))
                    .foregroundStyle(Theme.void.opacity(0.66))
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .padding(.trailing, 18)
            }

            StatusFlag(phase: council.phase)
        }
        .frame(height: 46)
        .background(Theme.orange)
        .glow(Theme.orange, radius: 14, intensity: 0.45)
    }
}

/// Status reads as a word first; the kanji rides along under it as texture.
private struct StatusFlag: View {
    let phase: Council.Phase

    var body: some View {
        let status = Plain.status(phase)
        VStack(alignment: .trailing, spacing: 0) {
            Text(status.english)
                .font(Theme.display(15))
                .tracking(3)
            Text(status.kanji)
                .font(Theme.plate(9))
                .tracking(2)
                .opacity(0.65)
        }
        .foregroundStyle(Theme.void)
        .padding(.horizontal, 18)
        .frame(height: 46)
        .background(Theme.void.opacity(0.14))
    }
}

/// The answer, kept on screen after the full-screen version clears.
private struct AnswerBar: View {
    let verdict: Verdict?
    let units: [Council.Unit]
    let synthesis: String
    let outcome: String

    private var color: Color { Theme.color(for: verdict) }

    var body: some View {
        HStack(spacing: 16) {
            Plate(text: Plain.verdictWord(verdict).isEmpty ? "DECIDED" : Plain.verdictWord(verdict),
                  color: color, size: 21, tracking: 3)

            VStack(alignment: .leading, spacing: 2) {
                Text(Plain.answer(units: units, outcome: outcome, fallback: synthesis))
                    .font(Theme.display(19))
                    .tracking(2.5)
                    .foregroundStyle(Theme.bone)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                let how = Plain.howTheyDecided(outcome)
                if !how.isEmpty {
                    Text(how)
                        .font(Theme.mono(10))
                        .foregroundStyle(Theme.steel)
                }
            }

            Spacer()

            Text(Plain.replayHint)
                .font(Theme.mono(9))
                .foregroundStyle(Theme.steel)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .overlay(Rectangle().stroke(color.opacity(0.5), lineWidth: 1))
        .overlay(CornerTicks(color: color))
        .glow(color, radius: 9, intensity: 0.3)
    }
}

/// What they said, scrolling on its own and following the newest argument.
private struct TranscriptScroll: View {
    let lines: [Council.TranscriptLine]
    let phase: Council.Phase

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 13) {
                    if lines.isEmpty {
                        Text(Plain.emptyState(phase))
                            .font(Theme.mono(11))
                            .tracking(2.2)
                            .foregroundStyle(Theme.steel)
                            .multilineTextAlignment(.center)
                            .padding(.top, 30)
                    }
                    ForEach(lines) { line in
                        TranscriptCard(line: line).id(line.id)
                    }
                }
                .padding(.horizontal, 26)
                .padding(.vertical, 16)
                .frame(maxWidth: 920)
                .frame(maxWidth: .infinity)
            }
            .onChange(of: lines.count) { _, _ in
                guard let last = lines.last else { return }
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

    var body: some View {
        HStack(spacing: 14) {
            Text("❯")
                .font(Theme.display(19))
                .foregroundStyle(Theme.orange)
                .glow(Theme.orange, radius: 8)

            TextField(Plain.placeholder, text: $draft)
                .textFieldStyle(.plain)
                .font(Theme.mono(14))
                .foregroundStyle(Theme.bone)
                .focused($focused)
                .onSubmit(submit)
                .disabled(council.isRunning)

            if council.isRunning {
                Button(Plain.stopButton, action: council.cancel)
                    .buttonStyle(ConsoleButton(color: Theme.red))
            } else {
                Button(Plain.askButton, action: submit)
                    .buttonStyle(ConsoleButton(color: Theme.orange))
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 15)
        .background(Theme.void.opacity(0.7))
        .overlay(alignment: .top) {
            Rectangle().fill(Theme.orangeDim.opacity(0.5)).frame(height: 1)
        }
    }

    private func submit() {
        let question = draft
        guard !question.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        council.ask(question)
        draft = ""
    }
}

struct ConsoleButton: ButtonStyle {
    var color: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.display(14))
            .tracking(3)
            .foregroundStyle(configuration.isPressed ? Theme.void : color)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(configuration.isPressed ? color : Color.clear)
            .overlay(Rectangle().stroke(color, lineWidth: 1))
            .glow(color, radius: 6, intensity: 0.5)
    }
}

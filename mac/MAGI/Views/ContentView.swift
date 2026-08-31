import SwiftUI

struct ContentView: View {
    @StateObject private var council = Council()
    @StateObject private var audio = Audio()
    @State private var draft = ""
    @State private var stampShowing = false
    @FocusState private var inputFocused: Bool

    /// How long the full-screen verdict holds before it clears. Adjustable
    /// because the right answer is a matter of taste, and because a fixed
    /// two-second window is impossible to screenshot:
    ///   defaults write io.zeroarch.magi stampSeconds 8
    @AppStorage("stampSeconds") private var stampSeconds: Double = 2.6

    var body: some View {
        ZStack {
            Theme.void.ignoresSafeArea()

            VStack(spacing: 0) {
                HeaderBar(council: council)
                Divider().overlay(Theme.orangeDim.opacity(0.5))

                // The console does not scroll. Watching the three units fill in
                // is the reason this is an app and not a terminal, and the
                // first build scrolled it off screen exactly when it mattered.
                MagiDisplay(council: council)
                    .padding(.vertical, 26)
                    .frame(maxWidth: .infinity)

                if case .resolved = council.phase, !stampShowing {
                    VerdictBar(verdict: council.verdict,
                               synthesis: council.synthesis,
                               outcome: council.outcome)
                        .padding(.horizontal, 30)
                        .padding(.bottom, 16)
                        .onTapGesture { replayStamp() }
                }

                if case let .failed(message) = council.phase {
                    Text(message)
                        .font(Theme.mono(12))
                        .foregroundStyle(Theme.red)
                        .padding(.horizontal, 30)
                        .padding(.bottom, 12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Divider().overlay(Theme.orangeDim.opacity(0.35))

                TranscriptScroll(lines: council.transcript, phase: council.phase)

                Divider().overlay(Theme.orangeDim.opacity(0.5))
                InputBar(draft: $draft, council: council, focused: $inputFocused)
            }

            ScreenGlass()

            // The decision takes the whole screen, the way it does on the
            // display, then gets out of the way so the arguments are readable.
            if stampShowing {
                VerdictStamp(verdict: council.verdict,
                             synthesis: council.synthesis,
                             outcome: council.outcome)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Theme.void.opacity(0.93))
                    .contentShape(Rectangle())
                    .onTapGesture { withAnimation(.easeOut(duration: 0.28)) { stampShowing = false } }
                    .transition(.opacity)
                    .zIndex(10)
            }
        }
        .frame(minWidth: 980, minHeight: 820)
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

/// The transcript, scrolling on its own and following the newest argument so
/// you are never reading a stale card while a member is still talking.
private struct TranscriptScroll: View {
    let lines: [Council.TranscriptLine]
    let phase: Council.Phase

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 14) {
                    if lines.isEmpty {
                        EmptyState(phase: phase)
                            .padding(.top, 34)
                    }
                    ForEach(lines) { line in
                        TranscriptCard(line: line).id(line.id)
                    }
                }
                .padding(.horizontal, 30)
                .padding(.vertical, 18)
                .frame(maxWidth: 900)
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

private struct EmptyState: View {
    let phase: Council.Phase

    private var text: String {
        switch phase {
        case .warming: return "SEATING THE COUNCIL"
        case .deliberating: return "THE COUNCIL IS READING YOUR QUESTION"
        default: return "BRING A QUESTION.  THE COUNCIL DECIDES, IT DOES NOT ABSTAIN."
        }
    }

    var body: some View {
        Text(text)
            .font(Theme.mono(11))
            .tracking(2.5)
            .foregroundStyle(Theme.steel)
    }
}

/// The resolved verdict, kept on screen after the full-screen stamp clears.
private struct VerdictBar: View {
    let verdict: Verdict?
    let synthesis: String
    let outcome: String

    private var color: Color { Theme.color(for: verdict) }

    var body: some View {
        HStack(spacing: 16) {
            Text(verdict?.plate ?? "決")
                .font(Theme.plate(26))
                .tracking(5)
                .foregroundStyle(Theme.void)
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(color)

            Text(synthesis.replacingOccurrences(of: " — ", with: "  ·  ").uppercased())
                .font(Theme.display(17))
                .tracking(2.5)
                .foregroundStyle(Theme.bone)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            Spacer()

            Text("REPLAY")
                .font(Theme.mono(9))
                .tracking(2)
                .foregroundStyle(Theme.steel)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .overlay(Rectangle().stroke(color.opacity(0.55), lineWidth: 1))
        .glow(color, radius: 8, intensity: 0.35)
    }
}

private struct HeaderBar: View {
    @ObservedObject var council: Council

    private var status: String {
        switch council.phase {
        case .idle: return "待機"
        case .warming: return "起動中"
        case let .deliberating(round): return round > 1 ? "第\(round)回" : "審議中"
        case .resolved: return council.verdict?.plate ?? "決議"
        case .failed: return "応答なし"
        }
    }

    var body: some View {
        HStack(spacing: 18) {
            Text("MAGI")
                .font(Theme.display(24))
                .tracking(9)
                .foregroundStyle(Theme.orange)
                .glow(Theme.orange, radius: 12)

            Text("決議 SYSTEM")
                .font(Theme.plate(12))
                .tracking(4)
                .foregroundStyle(Theme.orangeDim)

            if !council.question.isEmpty {
                Text(council.question.uppercased())
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.steel)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }

            Spacer()

            if council.mode != "decision" && !council.question.isEmpty {
                Text(council.mode.uppercased())
                    .font(Theme.mono(10))
                    .tracking(2)
                    .foregroundStyle(Theme.steel)
            }

            Text(status)
                .font(Theme.plate(15))
                .tracking(4)
                .foregroundStyle(Theme.bone)
                .glow(Theme.orange, radius: 6, intensity: 0.5)
        }
        .padding(.horizontal, 26)
        .padding(.vertical, 14)
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

            TextField("bring a question", text: $draft)
                .textFieldStyle(.plain)
                .font(Theme.mono(14))
                .foregroundStyle(Theme.bone)
                .focused($focused)
                .onSubmit(submit)
                .disabled(council.isRunning)

            if council.isRunning {
                Button("ABORT", action: council.cancel)
                    .buttonStyle(ConsoleButton(color: Theme.red))
            } else {
                Button("CONVENE", action: submit)
                    .buttonStyle(ConsoleButton(color: Theme.orange))
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(.horizontal, 26)
        .padding(.vertical, 16)
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
            .font(Theme.display(13))
            .tracking(3)
            .foregroundStyle(configuration.isPressed ? Theme.void : color)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(configuration.isPressed ? color : Color.clear)
            .overlay(Rectangle().stroke(color, lineWidth: 1))
            .glow(color, radius: 6, intensity: 0.5)
    }
}

import SwiftUI

/// The answer, at the scale the reference uses.
///
/// The kanji owns the screen because that is the shot everyone remembers, but
/// the sentence under it is the one that has to carry the meaning, so it is
/// plain English counted from the three members: "2 OF 3 SAY NO", never
/// "MAJORITY — NO (0A · 1C · 2R)".
struct VerdictStamp: View {
    let verdict: Verdict?
    let units: [Council.Unit]
    let synthesis: String
    let outcome: String

    @State private var landed = false

    private var color: Color { Theme.color(for: verdict) }
    private var answer: String { Plain.answer(units: units, outcome: outcome, fallback: synthesis) }
    private var how: String { Plain.howTheyDecided(outcome) }

    var body: some View {
        VStack(spacing: 0) {
            // The big word first, in English, at the size that reads as the
            // answer. The kanji sits behind it as the plate it is stamped on.
            ZStack {
                Text(verdict?.plate ?? "決")
                    .font(Theme.plate(210))
                    .tracking(24)
                    .foregroundStyle(color.opacity(0.17))
                    .glow(color, radius: 40, intensity: 0.5)

                Text(Plain.verdictWord(verdict).isEmpty ? "DECIDED" : Plain.verdictWord(verdict))
                    .font(Theme.display(112))
                    .tracking(6)
                    .foregroundStyle(color)
                    .glow(color, radius: 30, intensity: 1)
            }
            .scaleEffect(landed ? 1 : 2.2)
            .opacity(landed ? 1 : 0)
            .blur(radius: landed ? 0 : 16)

            Rectangle()
                .fill(color)
                .frame(height: 3)
                .frame(maxWidth: 560)
                .glow(color, radius: 12)
                .scaleEffect(x: landed ? 1 : 0)
                .padding(.top, 6)

            Text(answer)
                .font(Theme.display(31))
                .tracking(4)
                .foregroundStyle(Theme.bone)
                .multilineTextAlignment(.center)
                .padding(.top, 20)
                .padding(.horizontal, 40)
                .opacity(landed ? 1 : 0)

            if !how.isEmpty {
                Text(how)
                    .font(Theme.mono(12))
                    .foregroundStyle(Theme.steel)
                    .padding(.top, 9)
                    .opacity(landed ? 1 : 0)
            }
        }
        .frame(maxWidth: .infinity)
        .onAppear {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) { landed = true }
        }
    }
}

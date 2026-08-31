import SwiftUI

/// The decision, at the scale the reference uses: the kanji owns the screen,
/// slams in over everything, and the words are a caption underneath it.
struct VerdictStamp: View {
    let verdict: Verdict?
    let synthesis: String
    let outcome: String

    @State private var landed = false

    private var color: Color { Theme.color(for: verdict) }

    /// The synthesis line is "{OUTCOME} — {WORD}  ({tally})  ·  {clause}".
    /// The clause belongs under the plate, not clipped off the end of it.
    private var headline: String {
        synthesis.components(separatedBy: "  ·  ").first?
            .replacingOccurrences(of: " — ", with: "  ·  ")
            .uppercased() ?? synthesis.uppercased()
    }

    private var caption: String {
        let parts = synthesis.components(separatedBy: "  ·  ")
        return parts.count > 1 ? parts.dropFirst().joined(separator: "  ·  ") : ""
    }

    private var mannerPlate: String {
        switch outcome {
        case "consensus", "picks": return "全会一致"
        case "majority": return "多数決"
        case "conviction": return "確信度"
        case "tiebreak", "deadlock", "split": return "決選"
        default: return ""
        }
    }

    var body: some View {
        VStack(spacing: 14) {
            Text(verdict?.plate ?? "決")
                .font(Theme.plate(128))
                .tracking(18)
                .foregroundStyle(color)
                .glow(color, radius: 34, intensity: 1)
                .scaleEffect(landed ? 1 : 2.4)
                .opacity(landed ? 1 : 0)
                .blur(radius: landed ? 0 : 14)

            Rectangle()
                .fill(color)
                .frame(height: 3)
                .glow(color, radius: 12)
                .scaleEffect(x: landed ? 1 : 0, anchor: .center)

            Text(headline)
                .font(Theme.display(30))
                .tracking(5)
                .foregroundStyle(Theme.bone)
                .multilineTextAlignment(.center)
                .opacity(landed ? 1 : 0)

            if !mannerPlate.isEmpty {
                Text(mannerPlate)
                    .font(Theme.plate(17))
                    .tracking(7)
                    .foregroundStyle(color.opacity(0.85))
                    .opacity(landed ? 1 : 0)
            }

            if !caption.isEmpty {
                Text(caption)
                    .font(Theme.mono(12))
                    .foregroundStyle(Theme.steel)
                    .opacity(landed ? 1 : 0)
            }
        }
        .frame(maxWidth: .infinity)
        .onAppear {
            withAnimation(.spring(response: 0.42, dampingFraction: 0.62)) { landed = true }
        }
    }
}

import SwiftUI

/// The arguments. The display is the spectacle, but the reason to run this at
/// all is three independent reads you can disagree with, so the prose stays
/// readable: left-aligned, generous measure, no effects over the text itself.
struct TranscriptView: View {
    let lines: [Council.TranscriptLine]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(lines) { line in
                TranscriptCard(line: line)
            }
        }
    }
}

struct TranscriptCard: View {
    let line: Council.TranscriptLine

    private var accent: Color { Theme.color(for: line.position.verdictKey) }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 10) {
                Text(line.member)
                    .font(Theme.display(13))
                    .tracking(3)
                    .foregroundStyle(Theme.void)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(accent)

                if line.round > 1 {
                    Text("ROUND \(line.round)")
                        .font(Theme.mono(9))
                        .tracking(2)
                        .foregroundStyle(Theme.steel)
                }

                if line.position.changed {
                    Text("CHANGED POSITION")
                        .font(Theme.mono(9))
                        .tracking(2)
                        .foregroundStyle(Theme.orange)
                }

                Spacer()

                if let plate = line.position.verdictKey?.plate {
                    Text(plate)
                        .font(Theme.plate(14))
                        .tracking(3)
                        .foregroundStyle(accent)
                }
            }

            Text(line.text)
                .font(.system(size: 13.5))
                .foregroundStyle(Theme.bone.opacity(0.92))
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)

            if !line.finding.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Text(line.lens.isEmpty ? "FINDING" : line.lens)
                        .font(Theme.mono(9))
                        .tracking(1.5)
                        .foregroundStyle(accent)
                    Text(line.finding)
                        .font(Theme.mono(11))
                        .foregroundStyle(Theme.steel)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let condition = line.position.condition, !condition.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Text("ONLY IF")
                        .font(Theme.mono(9))
                        .tracking(1.5)
                        .foregroundStyle(Theme.orange)
                    Text(condition)
                        .font(Theme.mono(11))
                        .foregroundStyle(Theme.bone.opacity(0.8))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.02))
        .overlay(alignment: .leading) {
            Rectangle().fill(accent).frame(width: 2)
        }
        .overlay(Rectangle().stroke(accent.opacity(0.28), lineWidth: 1))
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

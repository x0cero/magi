import SwiftUI

/// What each of the three actually said.
///
/// The display is the spectacle, but the reason to run this at all is three
/// independent reads you can argue with, so the prose stays plain: no lens
/// tags, no confidence scores, no verdict enum names. Just who said it, what
/// they answered, and why.
struct TranscriptView: View {
    let lines: [Council.TranscriptLine]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(lines) { line in
                TranscriptCard(line: line)
            }
        }
    }
}

struct TranscriptCard: View {
    let line: Council.TranscriptLine

    private var accent: Color { Theme.color(for: line.position.verdictKey) }

    private var answer: String {
        if line.position.failed { return "NO ANSWER" }
        if let verdict = line.position.verdictKey { return Plain.verdictWord(verdict) }
        if let option = line.position.option { return option.uppercased() }
        if let recommendation = line.position.recommendation { return recommendation.uppercased() }
        return ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Plate(text: line.member, color: accent, size: 12, tracking: 2.5)

                Text(Plain.role(line.member))
                    .font(Theme.mono(8.5))
                    .tracking(1.6)
                    .foregroundStyle(Theme.steel)

                if line.round > 1 {
                    Text("ARGUING BACK")
                        .font(Theme.mono(8.5))
                        .tracking(1.6)
                        .foregroundStyle(Theme.steel)
                }

                if line.position.changed {
                    Text(Plain.changedMind)
                        .font(Theme.mono(8.5))
                        .tracking(1.6)
                        .foregroundStyle(Theme.orange)
                }

                Spacer()

                if !answer.isEmpty {
                    Text(answer)
                        .font(Theme.display(17))
                        .tracking(2)
                        .foregroundStyle(accent)
                }
                if let conviction = line.position.confidence {
                    Text(Plain.conviction(conviction))
                        .font(Theme.mono(8))
                        .tracking(1.4)
                        .foregroundStyle(Theme.steel)
                }
            }

            Text(line.text)
                .font(.system(size: 13.5))
                .foregroundStyle(Theme.bone.opacity(0.93))
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)

            if !line.finding.isEmpty {
                LabelledLine(label: Plain.lens(line.lens, member: line.member),
                             text: line.finding, color: accent)
            }

            if let condition = line.position.condition, !condition.isEmpty,
               condition.lowercased() != "none" {
                LabelledLine(label: Plain.onlyIf, text: condition, color: Theme.orange)
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.022))
        .overlay(alignment: .leading) {
            Rectangle().fill(accent).frame(width: 2)
        }
        .overlay(Rectangle().stroke(accent.opacity(0.25), lineWidth: 1))
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

private struct LabelledLine: View {
    let label: String
    let text: String
    let color: Color

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Text(label)
                .font(Theme.mono(8.5))
                .tracking(1.4)
                .foregroundStyle(color)
                .frame(width: 96, alignment: .leading)
            Text(text)
                .font(Theme.mono(11))
                .foregroundStyle(Theme.bone.opacity(0.78))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

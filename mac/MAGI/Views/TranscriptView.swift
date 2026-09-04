import SwiftUI

/// What each of the three actually said: a coloured rule down the left, the
/// name, the angle and how sure they are, then the argument in plain prose.
/// No lens tags, no confidence scores, no verdict enum names.
struct TranscriptView: View {
    let lines: [Council.TranscriptLine]
    let units: [Council.Unit]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(lines) { line in
                TranscriptCard(line: line, tag: Tally.tag(for: line, among: units))
            }
        }
    }
}

/// Who stood alone. Counted from the final positions, so the tag only appears
/// once the split is known.
enum Tally {
    static func tag(for line: Council.TranscriptLine, among units: [Council.Unit]) -> String? {
        let verdicts = units.compactMap { $0.position?.verdictKey }
        guard verdicts.count >= 3, let mine = line.position.verdictKey else { return nil }
        let same = verdicts.filter { $0 == mine }.count
        guard same == 1 else { return nil }
        switch mine {
        case .accept: return "THE LONE YES"
        case .reject: return "THE LONE NO"
        case .conditional: return "THE ONLY ONE WITH A CONDITION"
        }
    }
}

struct TranscriptCard: View {
    let line: Council.TranscriptLine
    var tag: String? = nil

    private var accent: Color { line.member == "YOU" ? Theme.orange : Theme.color(for: line.position.verdictKey) }

    private var subtitle: String {
        let conviction = Plain.conviction(line.position.confidence)
        let role = Plain.lens(line.lens, member: line.member)
        return conviction.isEmpty ? role : "\(role) · \(conviction)"
    }

    var body: some View {
        if line.member == "YOU" {
            you
        } else {
            member
        }
    }

    /// What the user said, when it is not the opening question: a short line
    /// under a YOU rule so the argument reads as a conversation.
    private var you: some View {
        VStack(alignment: .leading, spacing: 6) {
            Caption(text: line.round > 1 ? "YOU ARGUED BACK" : "YOU", color: Theme.orange, size: 10, tracking: 1.4)
            Text(line.text)
                .font(Theme.mono(13))
                .foregroundStyle(Theme.bone)
                .lineSpacing(5)
                .frame(maxWidth: 660, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
        .padding(.leading, 16)
        .overlay(alignment: .leading) { Rectangle().fill(Theme.orange).frame(width: 3) }
        .frame(maxWidth: .infinity, alignment: .leading)
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }

    private var member: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(line.member)
                    .font(Theme.display(17))
                    .tracking(1.4)
                    .foregroundStyle(Theme.bone)
                Caption(text: subtitle, size: 10, tracking: 1.2)
                if line.round > 1 {
                    Caption(text: "ARGUING BACK", size: 9.5, tracking: 1.4)
                }
                if line.position.changed {
                    Caption(text: Plain.changedMind, color: Theme.orange, size: 9.5, tracking: 1.4)
                }
                if let tag {
                    Caption(text: tag, color: accent, size: 9.5, tracking: 1.4)
                }
            }

            Text(line.text)
                .font(Theme.mono(13))
                .foregroundStyle(Theme.prose)
                .lineSpacing(5)
                .frame(maxWidth: 660, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)

            if !line.finding.isEmpty {
                LabelledLine(label: "ONLY IT SAID THIS", text: line.finding, color: Theme.orange)
            }

            if let condition = line.position.condition, !condition.isEmpty,
               condition.lowercased() != "none" {
                LabelledLine(label: Plain.onlyIf, text: condition, color: Theme.orange)
            }
        }
        .padding(.vertical, 2)
        .padding(.leading, 16)
        .overlay(alignment: .leading) {
            Rectangle().fill(accent).frame(width: 3)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

private struct LabelledLine: View {
    let label: String
    let text: String
    let color: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Caption(text: label, color: color, size: 9.5, tracking: 1.4)
            Text(text)
                .font(Theme.mono(12))
                .foregroundStyle(Theme.steel)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

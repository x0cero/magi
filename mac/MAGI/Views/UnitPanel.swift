import SwiftUI

/// One seat in the sidebar: a filled block with black text on it.
///
/// Name and answer on the first line, the question that seat answers and the
/// kanji plate on the second, and five bars for how strongly it holds the
/// answer. Red when it says no, mint otherwise, dim mint while it thinks.
struct UnitPanel: View {
    let unit: Council.Unit

    private var decided: Bool {
        guard let position = unit.position else { return false }
        return position.verdictKey != nil || position.option != nil
            || position.recommendation != nil || position.failed
    }

    private var fill: Color { Theme.unitFill(for: unit.position) }
    private var state: (kanji: String, english: String) { Plain.unitState(unit.position) }
    private var ink: Color { Theme.void }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(unit.name)
                    .font(Theme.display(22))
                    .tracking(0.6)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text("·0\(unit.number)")
                    .font(Theme.mono(10))
                    .opacity(0.62)
                Spacer(minLength: 6)
                Text(decided ? state.english : "")
                    .font(Theme.display(26))
                    .tracking(1)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
            }

            HStack(spacing: 8) {
                Caption(text: Plain.role(unit.name), color: ink.opacity(0.7), size: 10, tracking: 1.2)
                Spacer(minLength: 6)
                Text(state.kanji)
                    .font(Theme.plate(14))
                    .tracking(2)
                    .opacity(0.75)
            }

            ConvictionBars(level: decided ? (unit.position?.confidence ?? 0) : 0, ink: ink)
        }
        .foregroundStyle(ink)
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        // The moment a seat reports, the block flashes once. The flash sits
        // under the text, not over it, or the name greys out mid-flash.
        .background(ZStack {
            fill
            Color.white.opacity(unit.reporting ? 0.35 : 0)
        })
        .shadow(color: fill.opacity(decided ? 0.16 : 0), radius: 11)
        .animation(.easeOut(duration: 0.4), value: decided)
        .animation(.easeOut(duration: 0.6), value: unit.reporting)
    }
}

/// Five segments; the engine's confidence is 1 to 5 and nobody needs the number.
struct ConvictionBars: View {
    let level: Int
    let ink: Color

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<5, id: \.self) { index in
                Rectangle()
                    .fill(index < level ? ink : ink.opacity(0.22))
                    .frame(height: 4)
                    .frame(maxWidth: .infinity)
            }
        }
    }
}

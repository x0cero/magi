import SwiftUI

/// The MAGI display, drawn on one canvas.
///
/// Traced from the reference: 提訴 and 決議 across the top corners with a rule
/// under each, the code block down the left, a boxed 情報 on the right, the top
/// unit rising between the two headers, the other two along the bottom, and
/// MAGI in the black gap between them.
///
/// Everything scales off the panel width, so the proportions hold at any size.
/// The panel keeps the reference's own shape rather than stretching to the
/// window, because a letterboxed strip was most of why the earlier builds did
/// not read as this at all.
struct MagiDisplay: View {
    @ObservedObject var council: Council

    private var seated: [Council.Unit] {
        let byName = Dictionary(uniqueKeysWithValues: council.units.map { ($0.id, $0) })
        return Seats.order.compactMap { byName[$0] }
    }

    private var extras: [Council.Unit] { council.units.filter { !Seats.order.contains($0.id) } }
    private var answered: Int { council.units.filter { $0.position != nil }.count }

    var body: some View {
        GeometryReader { geometry in
            let w = geometry.size.width
            let h = geometry.size.height

            ZStack(alignment: .topLeading) {
                Color.clear

                ForEach(seated) { unit in UnitPanel(unit: unit) }

                ForEach(Array(Seats.bars.enumerated()), id: \.offset) { _, bar in
                    UnitShape(points: bar).fill(Theme.orange)
                }

                header("提訴", at: Seats.headerLeft, w: w, h: h)
                header("決議", at: Seats.headerRight, w: w, h: h)

                CodeBlock(mode: council.mode, answered: answered,
                          total: max(council.units.count, 1), scale: w)
                    .position(x: w * Seats.codeBlock.x + w * 0.15,
                              y: h * Seats.codeBlock.y)

                InfoBox(phase: council.phase, scale: w)
                    .position(x: w * Seats.infoBox.x, y: h * Seats.infoBox.y)

                // MAGI is set in a serif here, the one place the display breaks
                // from its condensed sans.
                Text("MAGI")
                    .font(.custom("Georgia-Bold", fixedSize: w * 0.055))
                    .tracking(w * 0.003)
                    .foregroundStyle(Theme.orange)
                    .position(x: w * Seats.hub.x, y: h * Seats.hub.y)
            }
        }
        .aspectRatio(1.34, contentMode: .fit)
        .background(Theme.void)
        .overlay(Rectangle().stroke(Theme.orange, lineWidth: 2))
        .overlay(alignment: .bottom) {
            if !extras.isEmpty {
                HStack(spacing: 10) {
                    ForEach(extras) { unit in SpecialistChip(unit: unit) }
                }
                .padding(.bottom, 8)
            }
        }
    }

    private func header(_ text: String, at point: CGPoint, w: CGFloat, h: CGFloat) -> some View {
        VStack(spacing: w * 0.008) {
            Text(text)
                .font(Theme.plate(w * 0.072))
                .tracking(w * 0.022)
                .foregroundStyle(Theme.orange)
            Rectangle()
                .fill(Theme.unit)
                .frame(width: w * 0.235, height: max(1.5, w * 0.0026))
        }
        .position(x: w * point.x, y: h * point.y)
    }
}

/// The block down the left: one large line, the fields under it.
private struct CodeBlock: View {
    let mode: String
    let answered: Int
    let total: Int
    let scale: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: scale * 0.006) {
            Text("CODE:601")
                .font(Theme.display(scale * 0.048))
                .foregroundStyle(Theme.orange)
            VStack(alignment: .leading, spacing: scale * 0.003) {
                Text("FILE:MAGI_SYS")
                Text("EXT:\(answered)/\(total)")
                Text("EX_MODE:\(mode.uppercased())")
                Text("PRIORITY:AAA")
            }
            .font(Theme.display(scale * 0.021))
            .foregroundStyle(Theme.orange)
        }
        .frame(width: scale * 0.30, alignment: .leading)
    }
}

/// The boxed readout on the right, with the state word under it.
private struct InfoBox: View {
    let phase: Council.Phase
    let scale: CGFloat

    var body: some View {
        let status = Plain.status(phase)
        let alarm: Bool = { if case .failed = phase { return true }; return false }()
        let tint = alarm ? Theme.red : Theme.unit
        VStack(spacing: scale * 0.008) {
            Text("情 報")
                .font(Theme.plate(scale * 0.040))
                .tracking(scale * 0.010)
                .foregroundStyle(tint)
                .padding(.horizontal, scale * 0.024)
                .padding(.vertical, scale * 0.012)
                .overlay(Rectangle().stroke(tint, lineWidth: 2).padding(scale * 0.005))
                .overlay(Rectangle().stroke(tint, lineWidth: 1))
            Text(status.english)
                .font(Theme.display(scale * 0.024))
                .tracking(scale * 0.002)
                .foregroundStyle(alarm ? Theme.red : Theme.orange)
        }
    }
}

/// An invited specialist. Not one of the three, which is canon, so they queue
/// underneath as strips.
private struct SpecialistChip: View {
    let unit: Council.Unit

    private var decided: Bool { unit.position != nil }
    private var fill: Color { Theme.unitFill(for: unit.position?.verdictKey, decided: decided) }

    var body: some View {
        let state = Plain.unitState(unit.position)
        HStack(spacing: 8) {
            Text(unit.name).font(Theme.display(13)).tracking(1.4)
            Text(state.english).font(Theme.display(15))
        }
        .foregroundStyle(Theme.void.opacity(decided ? 1 : 0.6))
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(fill)
        .overlay(Rectangle().stroke(Theme.orange, lineWidth: 1))
    }
}

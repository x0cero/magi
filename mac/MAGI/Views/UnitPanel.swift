import SwiftUI

/// The hexagon the three units are drawn in. Flat top and bottom, chamfered
/// sides: this is the shape on the display, and it is why the terminal version
/// never looked right, since a character grid cannot cut a diagonal.
struct UnitHexagon: Shape {
    var chamfer: CGFloat = 26

    func path(in rect: CGRect) -> Path {
        let c = min(chamfer, rect.width / 3, rect.height / 2)
        var path = Path()
        path.move(to: CGPoint(x: rect.minX + c, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX - c, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.maxX - c, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX + c, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.midY))
        path.closeSubpath()
        return path
    }
}

/// One MAGI unit. Dark and outlined while it thinks, filled and lit the moment
/// it reports, because the thing worth watching is the council filling in.
struct UnitPanel: View {
    let unit: Council.Unit
    var compact: Bool = false

    private var accent: Color {
        if unit.position?.failed == true { return Theme.red }
        return Theme.color(for: unit.position?.verdictKey)
    }

    private var decided: Bool {
        guard let position = unit.position else { return false }
        return position.verdictKey != nil || position.option != nil
            || position.recommendation != nil || position.failed
    }

    var body: some View {
        ZStack {
            UnitHexagon()
                .fill(decided ? accent.opacity(0.14) : Color.black.opacity(0.55))
            UnitHexagon()
                .stroke(decided ? accent : Theme.orangeDim, lineWidth: decided ? 2 : 1)
                .glow(decided ? accent : Theme.orangeDim,
                      radius: decided ? 14 : 5,
                      intensity: decided ? 0.85 : 0.35)

            VStack(spacing: compact ? 2 : 6) {
                Text("\(unit.name) · \(unit.number)")
                    .font(Theme.display(compact ? 13 : 16))
                    .tracking(2.5)
                    .foregroundStyle(decided ? accent : Theme.orangeDim)

                Text(unit.position?.plate ?? "待機")
                    .font(Theme.plate(compact ? 26 : 38))
                    .tracking(compact ? 3 : 6)
                    .foregroundStyle(decided ? accent : Theme.orangeDim.opacity(0.75))
                    .glow(accent, radius: decided ? 16 : 0, intensity: decided ? 0.8 : 0)
                    .contentTransition(.numericText())

                if let detail = unit.position?.detail, !detail.isEmpty {
                    Text(detail.uppercased())
                        .font(Theme.mono(compact ? 9 : 11))
                        .tracking(1.6)
                        .foregroundStyle(Theme.bone.opacity(0.8))
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .padding(.horizontal, 14)
                }

                if !compact {
                    ConvictionBar(level: unit.position?.confidence, color: accent)
                        .opacity(decided ? 1 : 0.25)
                }

                Text(unit.model)
                    .font(Theme.mono(compact ? 8 : 9))
                    .foregroundStyle(Theme.steel)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .padding(.horizontal, 16)
            }
            .padding(.vertical, compact ? 8 : 14)

            // The report flash: one bright pulse as the unit lands, then gone.
            UnitHexagon()
                .fill(accent)
                .opacity(unit.reporting ? 0.5 : 0)
                .blendMode(.plusLighter)
                .allowsHitTesting(false)
        }
        .animation(.easeOut(duration: 0.45), value: decided)
        .animation(.easeOut(duration: 0.6), value: unit.reporting)
    }
}

/// Conviction, as filled cells. Five is "would defend this"; one is "would not
/// argue if you overruled it".
struct ConvictionBar: View {
    let level: Int?
    let color: Color

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<5, id: \.self) { index in
                Rectangle()
                    .fill(index < (level ?? 0) ? color : color.opacity(0.16))
                    .frame(width: 12, height: 3)
            }
        }
    }
}

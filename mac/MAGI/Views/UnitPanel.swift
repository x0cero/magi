import SwiftUI

/// A polygon given in normalised coordinates, so the slabs keep interlocking
/// at any window size.
struct UnitShape: Shape {
    let points: [CGPoint]

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard let first = points.first else { return path }
        func place(_ p: CGPoint) -> CGPoint {
            CGPoint(x: rect.minX + p.x * rect.width, y: rect.minY + p.y * rect.height)
        }
        path.move(to: place(first))
        for point in points.dropFirst() { path.addLine(to: place(point)) }
        path.closeSubpath()
        return path
    }
}

/// One seat: a solid slab with black text punched out of it.
///
/// Solid, always. The first build made an undecided seat a translucent grey,
/// which let the seams show through the middle of it and turned three shapes
/// into one smear. On the reference the panels are green at rest and go red
/// when they refuse, so "waiting" is a dimmer green, never a grey wash.
struct UnitPanel: View {
    let unit: Council.Unit
    let seat: String

    private var decided: Bool {
        guard let position = unit.position else { return false }
        return position.verdictKey != nil || position.option != nil
            || position.recommendation != nil || position.failed
    }

    private var fill: Color {
        if unit.position?.failed == true { return Theme.unitReject }
        guard decided else { return Theme.unitResting }
        return unit.position?.verdictKey == .reject ? Theme.unitReject : Theme.unit
    }

    private var ink: Color { Theme.void.opacity(decided ? 1 : 0.62) }
    private var state: (kanji: String, english: String) { Plain.unitState(unit.position) }

    var body: some View {
        GeometryReader { geometry in
            let points = Seats.polygon(seat)
            let anchor = Seats.labelAnchor(seat)

            ZStack {
                // No bloom on the fill. A glow on a shape this large spreads
                // its colour straight across the seam, and two red slabs then
                // read as one. The reference has hard edges; the light comes
                // from the outline, not the field.
                UnitShape(points: points)
                    .fill(fill)

                // Amber edge on every slab. This is the only thing separating
                // two neighbours that happen to have voted the same way.
                UnitShape(points: points)
                    .stroke(Theme.orange, lineWidth: 2)

                UnitShape(points: points)
                    .fill(.white)
                    .opacity(unit.reporting ? 0.55 : 0)
                    .blendMode(.plusLighter)

                VStack(spacing: 1) {
                    Text("\(unit.name) · \(unit.number)")
                        .font(Theme.display(min(30, geometry.size.width * 0.043)))
                        .tracking(1.4)
                        .foregroundStyle(ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.5)

                    Text(Plain.role(unit.name))
                        .font(Theme.mono(min(9, geometry.size.width * 0.0125)))
                        .tracking(1.2)
                        .foregroundStyle(ink.opacity(0.66))

                    if decided {
                        Text(state.english)
                            .font(Theme.display(min(34, geometry.size.width * 0.05)))
                            .foregroundStyle(ink)
                            .lineLimit(1)
                            .minimumScaleFactor(0.4)
                            .padding(.top, 2)

                        HStack(spacing: 6) {
                            Text(state.kanji).font(Theme.plate(min(13, geometry.size.width * 0.018)))
                            if let conviction = unit.position?.confidence {
                                Text(Plain.conviction(conviction))
                                    .font(Theme.mono(min(8, geometry.size.width * 0.011)))
                                    .tracking(1)
                            }
                        }
                        .foregroundStyle(ink.opacity(0.6))
                    }
                }
                .frame(width: geometry.size.width * 0.34)
                .position(x: geometry.size.width * anchor.x,
                          y: geometry.size.height * anchor.y)
                .allowsHitTesting(false)
            }
        }
        .animation(.easeOut(duration: 0.4), value: decided)
        .animation(.easeOut(duration: 0.6), value: unit.reporting)
    }
}

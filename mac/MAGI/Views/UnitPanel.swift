import SwiftUI

/// A polygon in normalised coordinates, so the shapes hold their proportions
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

/// One unit: a solid block with black text on it, the way the display draws it.
///
/// Green at rest, red when it refuses. Nothing translucent, no bloom on the
/// fill, and the name is the largest thing on the block.
struct UnitPanel: View {
    let unit: Council.Unit

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

    private var state: (kanji: String, english: String) { Plain.unitState(unit.position) }

    var body: some View {
        GeometryReader { geometry in
            let points = Seats.shapes[unit.id] ?? []
            let anchor = Seats.labels[unit.id] ?? CGPoint(x: 0.5, y: 0.5)
            let width = geometry.size.width
            let allowed = (Seats.labelWidths[unit.id] ?? 0.32) * width

            ZStack {
                UnitShape(points: points).fill(fill)
                UnitShape(points: points).stroke(Theme.orange, lineWidth: 2)

                UnitShape(points: points)
                    .fill(.white)
                    .opacity(unit.reporting ? 0.55 : 0)
                    .blendMode(.plusLighter)

                VStack(spacing: 2) {
                    Text("\(unit.name) · \(unit.number)")
                        .font(Theme.display(width * 0.030))
                        .tracking(0.5)
                        .foregroundStyle(Theme.void)
                        .lineLimit(1)
                        .minimumScaleFactor(0.4)

                    Text(Plain.role(unit.name))
                        .font(Theme.mono(width * 0.0105))
                        .tracking(1.1)
                        .foregroundStyle(Theme.void.opacity(0.62))

                    if decided {
                        Text(state.english)
                            .font(Theme.display(width * 0.040))
                            .foregroundStyle(Theme.void)
                            .lineLimit(1)
                            .minimumScaleFactor(0.4)
                            .padding(.top, 2)

                        HStack(spacing: 6) {
                            Text(state.kanji).font(Theme.plate(width * 0.016))
                            if let conviction = unit.position?.confidence {
                                Text(Plain.conviction(conviction))
                                    .font(Theme.mono(width * 0.0098))
                                    .tracking(1)
                            }
                        }
                        .foregroundStyle(Theme.void.opacity(0.6))
                    }
                }
                .frame(width: allowed)
                .position(x: width * anchor.x, y: geometry.size.height * anchor.y)
                .allowsHitTesting(false)
            }
        }
        .animation(.easeOut(duration: 0.4), value: decided)
        .animation(.easeOut(duration: 0.6), value: unit.reporting)
    }
}

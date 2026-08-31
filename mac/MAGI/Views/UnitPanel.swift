import SwiftUI

/// A polygon given in normalised coordinates, so the three units can be cut
/// from one rectangle and keep interlocking at any window size.
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

/// The three seats, as the reference cuts them: one big slab on the left and
/// two stacked on the right, interlocking around a gap in the middle where the
/// word MAGI sits. Nothing here is a rectangle and nothing is symmetric, which
/// is most of why it does not read as a dashboard.
enum Seat {
    static let shapes: [String: [CGPoint]] = [
        // CASPER, the big one on the left.
        "left": [
            CGPoint(x: 0.015, y: 0.20), CGPoint(x: 0.40, y: 0.10),
            CGPoint(x: 0.545, y: 0.455), CGPoint(x: 0.435, y: 0.845),
            CGPoint(x: 0.015, y: 0.80),
        ],
        // BALTHASAR, top right.
        "top": [
            CGPoint(x: 0.445, y: 0.075), CGPoint(x: 0.985, y: 0.045),
            CGPoint(x: 0.985, y: 0.415), CGPoint(x: 0.70, y: 0.475),
            CGPoint(x: 0.585, y: 0.44),
        ],
        // MELCHIOR, bottom right.
        "bottom": [
            CGPoint(x: 0.615, y: 0.565), CGPoint(x: 0.985, y: 0.50),
            CGPoint(x: 0.985, y: 0.87), CGPoint(x: 0.505, y: 0.925),
        ],
    ]

    /// Where each seat's label sits inside its own shape.
    static let anchors: [String: UnitPoint] = [
        "left": UnitPoint(x: 0.225, y: 0.47),
        "top": UnitPoint(x: 0.755, y: 0.24),
        "bottom": UnitPoint(x: 0.755, y: 0.725),
    ]
}

/// One seat: a filled slab with black text punched out of it.
///
/// Mint while it is fine, red when it says no, dim while it is still thinking.
/// The name is the biggest thing in the shape because that is what the
/// reference does; the answer sits directly under it at a size you read next.
struct UnitPanel: View {
    let unit: Council.Unit
    let seat: String
    var scale: CGFloat = 1

    private var decided: Bool {
        guard let position = unit.position else { return false }
        return position.verdictKey != nil || position.option != nil
            || position.recommendation != nil || position.failed
    }

    private var fill: Color {
        if unit.position?.failed == true { return Theme.unitReject }
        return Theme.unitFill(for: unit.position?.verdictKey, decided: decided)
    }

    private var ink: Color { decided ? Theme.void : Theme.bone.opacity(0.5) }
    private var state: (kanji: String, english: String) { Plain.unitState(unit.position) }

    var body: some View {
        ZStack {
            UnitShape(points: Seat.shapes[seat] ?? [])
                .fill(fill)
                .glow(fill, radius: decided ? 22 : 5, intensity: decided ? 0.7 : 0.18)

            UnitShape(points: Seat.shapes[seat] ?? [])
                .fill(.white)
                .opacity(unit.reporting ? 0.55 : 0)
                .blendMode(.plusLighter)
                .allowsHitTesting(false)
        }
        .overlay(alignment: .topLeading) {
            GeometryReader { geometry in
                let anchor = Seat.anchors[seat] ?? .center
                VStack(spacing: 2 * scale) {
                    Text("\(unit.name) · \(unit.number)")
                        .font(Theme.display(25 * scale))
                        .tracking(1.5 * scale)
                        .foregroundStyle(ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.5)

                    Text(Plain.role(unit.name))
                        .font(Theme.mono(7.5 * scale))
                        .tracking(1.3)
                        .foregroundStyle(ink.opacity(0.6))

                    if decided {
                        Text(state.english)
                            .font(Theme.display(29 * scale))
                            .tracking(1)
                            .foregroundStyle(ink)
                            .lineLimit(1)
                            .minimumScaleFactor(0.45)
                            .padding(.top, 3 * scale)

                        HStack(spacing: 7 * scale) {
                            Text(state.kanji)
                                .font(Theme.plate(11 * scale))
                                .tracking(1.5)
                            if let conviction = unit.position?.confidence {
                                Text(Plain.conviction(conviction))
                                    .font(Theme.mono(7 * scale))
                                    .tracking(1.2)
                            }
                        }
                        .foregroundStyle(ink.opacity(0.62))
                    }
                }
                .frame(width: geometry.size.width * 0.40)
                .position(x: geometry.size.width * anchor.x,
                          y: geometry.size.height * anchor.y)
            }
            .allowsHitTesting(false)
        }
        .animation(.easeOut(duration: 0.4), value: decided)
        .animation(.easeOut(duration: 0.6), value: unit.reporting)
    }
}

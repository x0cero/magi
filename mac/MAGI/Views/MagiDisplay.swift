import SwiftUI

/// The triangle, wired to a bus. Two units above, one below, connected through
/// a junction that lights as the council resolves.
struct MagiDisplay: View {
    @ObservedObject var council: Council

    // Panel geometry is stated once: the bus has to land on the unit centres,
    // and deriving that from padding guesses is how it ended up spanning wider
    // than the panels it connects.
    private static let panelWidth: CGFloat = 250
    private static let panelHeight: CGFloat = 170
    private static let columnGap: CGFloat = 34

    private var top: [Council.Unit] { Array(council.units.prefix(2)) }
    private var bottom: Council.Unit? { council.units.count > 2 ? council.units[2] : nil }
    private var extras: [Council.Unit] { Array(council.units.dropFirst(3)) }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: Self.columnGap) {
                ForEach(top) { unit in
                    UnitPanel(unit: unit)
                        .frame(width: Self.panelWidth, height: Self.panelHeight)
                }
            }

            if bottom != nil {
                BusLines(active: council.phase == .resolved)
                    .frame(width: Self.panelWidth + Self.columnGap, height: 62)
            }

            if let bottom {
                UnitPanel(unit: bottom)
                    .frame(width: Self.panelWidth, height: Self.panelHeight)
            }

            if !extras.isEmpty {
                HStack(spacing: 18) {
                    ForEach(extras) { unit in
                        UnitPanel(unit: unit, compact: true).frame(width: 190, height: 120)
                    }
                }
                .padding(.top, 26)
            }
        }
    }
}

/// The bus. Drawn as a path rather than assembled from rules so the corners
/// actually meet, and animated so current visibly runs down it on resolution.
struct BusLines: View {
    var active: Bool
    @State private var pulse: CGFloat = 0

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let height = geometry.size.height
            let midY = height * 0.55

            let path = Path { path in
                path.move(to: CGPoint(x: 0, y: 0))
                path.addLine(to: CGPoint(x: 0, y: midY))
                path.addLine(to: CGPoint(x: width, y: midY))
                path.addLine(to: CGPoint(x: width, y: 0))
                path.move(to: CGPoint(x: width / 2, y: midY))
                path.addLine(to: CGPoint(x: width / 2, y: height))
            }

            ZStack {
                path.stroke(Theme.orangeDim, lineWidth: 1)
                path.trim(from: max(0, pulse - 0.18), to: pulse)
                    .stroke(Theme.orange, lineWidth: 2)
                    .glow(Theme.orange, radius: 10)

                Circle()
                    .fill(active ? Theme.orange : Theme.orangeDim)
                    .frame(width: 7, height: 7)
                    .glow(Theme.orange, radius: active ? 12 : 3, intensity: active ? 1 : 0.3)
                    .position(x: width / 2, y: midY)
            }
        }
        .onAppear {
            withAnimation(.linear(duration: 2.4).repeatForever(autoreverses: false)) {
                pulse = 1.18
            }
        }
    }
}

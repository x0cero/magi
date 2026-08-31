import SwiftUI

/// The MAGI display: one rectangle cut into three interlocking slabs, with the
/// readout in a band above them rather than printed across them.
///
/// Three things were wrong before and all three are geometry, not taste. The
/// telemetry was overlaid on the slabs, so orange text sat on a green fill and
/// neither could be read. The seams were thin enough to disappear, so the three
/// slabs merged into two blobs of colour. And the panel occupied a small box in
/// the middle of a large black window, which is the opposite of the reference,
/// where the display is the screen.
struct MagiDisplay: View {
    @ObservedObject var council: Council

    private var seated: [(seat: String, unit: Council.Unit)] {
        let byName = Dictionary(uniqueKeysWithValues: council.units.map { ($0.id, $0) })
        return ["CASPER", "BALTHASAR", "MELCHIOR"]
            .compactMap { name in byName[name].map { (Seats.seat(for: name), $0) } }
    }

    private var extras: [Council.Unit] {
        council.units.filter { !["MELCHIOR", "BALTHASAR", "CASPER"].contains($0.id) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // The readout band. Its own strip, so nothing is ever printed on
            // top of a slab.
            HStack(alignment: .top) {
                Telemetry(council: council)
                Spacer(minLength: 20)
                StatePlate(phase: council.phase)
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 10)

            Rectangle()
                .fill(Theme.orange.opacity(0.45))
                .frame(height: 1)
                .padding(.horizontal, 12)

            ZStack {
                ForEach(seated, id: \.seat) { entry in
                    UnitPanel(unit: entry.unit, seat: entry.seat)
                }

                // The hub, on its own black plate so it is never lost against
                // whatever colour the slabs happen to be.
                GeometryReader { geometry in
                    Text("MAGI")
                        .font(Theme.display(min(26, geometry.size.width * 0.032)))
                        .tracking(3)
                        .foregroundStyle(Theme.orange)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Theme.void)
                        .glow(Theme.orange, radius: 9, intensity: 0.8)
                        .position(x: geometry.size.width * Seats.centre.x,
                                  y: geometry.size.height * Seats.centre.y)
                }
                .allowsHitTesting(false)
            }
            // A fixed height rather than an aspect ratio: aspectRatio(.fit)
            // let the slab area shrink away from the frame edges and float in
            // the middle of its own panel, which is the opposite of the point.
            .frame(maxWidth: .infinity, minHeight: 300, idealHeight: 360, maxHeight: 420)
            .padding(.horizontal, 12)
            .padding(.vertical, 12)

            if !extras.isEmpty {
                HStack(spacing: 10) {
                    ForEach(extras) { unit in
                        SpecialistChip(unit: unit)
                    }
                }
                .padding(.bottom, 12)
            }
        }
        .background(Theme.void.opacity(0.5))
        .overlay(Rectangle().stroke(Theme.orange, lineWidth: 2))
        .overlay(Rectangle().stroke(Theme.orange.opacity(0.3), lineWidth: 1).padding(5))
        .glow(Theme.orange, radius: 14, intensity: 0.3)
    }
}

/// An invited specialist. They are not seated in the triangle, which is canon,
/// so they queue underneath it as strips.
private struct SpecialistChip: View {
    let unit: Council.Unit

    private var decided: Bool { unit.position != nil }
    private var fill: Color {
        Theme.unitFill(for: unit.position?.verdictKey, decided: decided)
    }

    var body: some View {
        let state = Plain.unitState(unit.position)
        HStack(spacing: 8) {
            Text(unit.name).font(Theme.display(12)).tracking(1.6)
            Text(state.english).font(Theme.display(14))
        }
        .foregroundStyle(Theme.void.opacity(decided ? 1 : 0.6))
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(fill)
        .overlay(Rectangle().stroke(Theme.orange, lineWidth: 1))
    }
}

/// The readout. Real values only: invented ones would be set dressing on a
/// tool that is otherwise honest about what it knows.
private struct Telemetry: View {
    @ObservedObject var council: Council

    private var answered: Int { council.units.filter { $0.position != nil }.count }

    private var rows: [(String, String)] {
        [
            ("CODE", "601"),
            ("FILE", "MAGI_SYS"),
            ("EX_MODE", council.mode.uppercased()),
            ("REPORTED", "\(answered) / \(max(council.units.count, 1))"),
            ("PRIORITY", "A—"),
        ]
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            PlateOutline(text: "提訴")
            VStack(alignment: .leading, spacing: 1) {
                ForEach(rows, id: \.0) { row in
                    HStack(spacing: 4) {
                        Text(row.0)
                            .foregroundStyle(Theme.orange.opacity(0.85))
                            .frame(width: 58, alignment: .leading)
                        Text(":").foregroundStyle(Theme.orange.opacity(0.45))
                        Text(row.1).foregroundStyle(Theme.orange.opacity(0.6))
                    }
                }
            }
            .font(Theme.mono(8))
        }
    }
}

/// What the machine is doing, on the right of the readout band.
private struct StatePlate: View {
    let phase: Council.Phase

    var body: some View {
        let status = Plain.status(phase)
        let alarm: Bool = { if case .failed = phase { return true }; return false }()
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .trailing, spacing: 2) {
                Text(status.english)
                    .font(Theme.display(16))
                    .tracking(2.5)
                    .foregroundStyle(alarm ? Theme.red : Theme.orange)
                    .glow(alarm ? Theme.red : Theme.orange, radius: 7, intensity: 0.6)
                Text(status.kanji)
                    .font(Theme.plate(10))
                    .tracking(2)
                    .foregroundStyle(Theme.orange.opacity(0.6))
            }
            PlateOutline(text: "決議")
        }
    }
}

/// Kanji in an amber box, the way the corners of the display are labelled.
private struct PlateOutline: View {
    let text: String

    var body: some View {
        Text(text)
            .font(Theme.plate(15))
            .tracking(2)
            .foregroundStyle(Theme.orange)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .overlay(Rectangle().stroke(Theme.orange, lineWidth: 1.5))
            .glow(Theme.orange, radius: 6, intensity: 0.45)
    }
}

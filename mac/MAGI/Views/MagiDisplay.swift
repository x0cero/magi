import SwiftUI

/// The MAGI display, laid out the way the reference lays it out.
///
/// One rectangle cut into three interlocking slabs: the big one on the left,
/// two stacked on the right, with a gap between them where the word MAGI sits.
/// Amber rules run through the gaps. Kanji plates pin the top corners and a
/// block of small fixed-width data runs down the left, because on the
/// reference there is always more data on screen than anyone could read.
///
/// The earlier build had three tidy hexagons in a row. Tidy and separated is
/// exactly what this is not.
struct MagiDisplay: View {
    @ObservedObject var council: Council

    /// Reading order is CASPER left, BALTHASAR top right, MELCHIOR bottom
    /// right, matching the reference rather than the engine's seat order.
    private var seated: [(seat: String, unit: Council.Unit)] {
        let byName = Dictionary(uniqueKeysWithValues: council.units.map { ($0.id, $0) })
        return ["CASPER", "BALTHASAR", "MELCHIOR"]
            .compactMap { name in byName[name].map { (Seats.seat(for: name), $0) } }
    }

    private var extras: [Council.Unit] {
        council.units.filter { !["MELCHIOR", "BALTHASAR", "CASPER"].contains($0.id) }
    }

    var body: some View {
        VStack(spacing: 10) {
            ZStack {
                ForEach(seated, id: \.seat) { entry in
                    UnitPanel(unit: entry.unit, seat: entry.seat)
                }

                // The hub sits in the gap the three slabs leave open around
                // the centre they were cut from.
                GeometryReader { geometry in
                    Text("MAGI")
                        .font(Theme.display(min(24, geometry.size.width * 0.034)))
                        .tracking(4)
                        .foregroundStyle(Theme.orange)
                        .glow(Theme.orange, radius: 10)
                        .position(x: geometry.size.width * Seats.centre.x,
                                  y: geometry.size.height * Seats.centre.y)
                }
                .allowsHitTesting(false)
            }
            .aspectRatio(1.62, contentMode: .fit)
            .padding(.horizontal, 26)
            .padding(.top, 58)
            .padding(.bottom, 18)

            if !extras.isEmpty {
                HStack(spacing: 10) {
                    ForEach(extras) { unit in
                        SpecialistChip(unit: unit)
                    }
                }
                .padding(.bottom, 12)
            }
        }
        .background(Theme.void.opacity(0.4))
        .overlay(alignment: .topLeading) { Telemetry(council: council) }
        .overlay(alignment: .topTrailing) { StatePlate(phase: council.phase) }
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
            Text(unit.name)
                .font(Theme.display(12))
                .tracking(1.6)
            Text(state.english)
                .font(Theme.display(14))
        }
        .foregroundStyle(decided ? Theme.void : Theme.bone.opacity(0.5))
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(fill)
    }
}

/// The readout pinned to the frame. Real values where there are any, because
/// invented ones would be set dressing on a tool that is otherwise honest.
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
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 5) {
                PlateOutline(text: "提訴")
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(rows, id: \.0) { row in
                        HStack(spacing: 4) {
                            Text(row.0)
                                .foregroundStyle(Theme.orange.opacity(0.8))
                                .frame(width: 56, alignment: .leading)
                            Text(":").foregroundStyle(Theme.orange.opacity(0.4))
                            Text(row.1).foregroundStyle(Theme.orange.opacity(0.55))
                        }
                    }
                }
                .font(Theme.mono(7.5))
            }
        }
        .padding(.leading, 14)
        .padding(.top, 12)
    }
}

/// Top-right: what the machine is doing.
private struct StatePlate: View {
    let phase: Council.Phase

    var body: some View {
        let status = Plain.status(phase)
        let alarm: Bool = { if case .failed = phase { return true }; return false }()
        HStack(alignment: .top, spacing: 9) {
            VStack(alignment: .trailing, spacing: 3) {
                Text(status.kanji)
                    .font(Theme.plate(15))
                    .tracking(2)
                    .foregroundStyle(alarm ? Theme.red : Theme.orange)
                    .glow(alarm ? Theme.red : Theme.orange, radius: 7, intensity: 0.6)
                Text(status.english)
                    .font(Theme.mono(7.5))
                    .tracking(1.4)
                    .foregroundStyle(Theme.orange.opacity(0.6))
            }
            PlateOutline(text: "決議")
        }
        .padding(.trailing, 14)
        .padding(.top, 12)
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

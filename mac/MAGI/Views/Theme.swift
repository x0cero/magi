import SwiftUI

/// Orange on black, filled unit panels, kanji plates. Taken from the
/// "MAGI Mac - Nerv" design: every value here is a hex from that file.
enum Theme {
    static let void = Color(hex: 0x08080A)        // window ground
    static let panel = Color(hex: 0x0B0B0D)       // sidebar
    static let bar = Color(hex: 0x0E0E10)         // title bar
    static let hairline = Color(hex: 0x1E1E22)
    static let rule = Color(hex: 0x26262B)

    static let orange = Color(hex: 0xFF6B00)
    static let red = Color(hex: 0xFA4F42)
    static let mint = Color(hex: 0x8FEDB5)

    static let bone = Color(hex: 0xEFECE4)        // headings
    static let prose = Color(hex: 0xD8D4C9)       // reasoning
    static let record = Color(hex: 0xB9B5AA)
    static let steel = Color(hex: 0x8A8A92)       // labels
    static let placeholder = Color(hex: 0x6E6E78)

    /// Kept for the full-screen stamp, which still speaks in these.
    static let green = mint
    static let orangeDim = Color(hex: 0xA34400)

    /// A unit panel is a filled block. Red when it says no, mint otherwise,
    /// and the resting panel is a dim mint so the sidebar reads as three
    /// seats and not three holes.
    static let unitResting = Color(red: 0.22, green: 0.42, blue: 0.33)

    static func unitFill(for position: Position?) -> Color {
        guard let position else { return unitResting }
        if position.failed { return red }
        if position.verdictKey == .reject { return red }
        if position.verdictKey != nil || position.option != nil || position.recommendation != nil {
            return mint
        }
        return unitResting
    }

    static func color(for verdict: Verdict?) -> Color {
        switch verdict {
        case .accept: return mint
        case .reject: return red
        case .conditional, .none: return orange
        }
    }

    /// Avenir Next Condensed ships with macOS and is the closest face to the
    /// design's Oswald fallback stack, so nothing has to be bundled.
    static func display(_ size: CGFloat, weight: Font.Weight = .bold) -> Font {
        weight == .bold
            ? .custom("AvenirNextCondensed-Bold", fixedSize: size)
            : .custom("AvenirNextCondensed-DemiBold", fixedSize: size)
    }

    static func mono(_ size: CGFloat) -> Font {
        .system(size: size, weight: .medium, design: .monospaced)
    }

    /// Kanji need a face that actually has the glyphs; the condensed Latin one
    /// does not, and substituting mid-string changes the metrics.
    static func plate(_ size: CGFloat) -> Font {
        .custom("HiraginoSans-W7", fixedSize: size)
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255)
    }
}

/// Only the full-screen stamp glows now. The panels in the design are flat
/// blocks with a soft spill of their own colour behind them, nothing more.
struct Glow: ViewModifier {
    var color: Color
    var radius: CGFloat = 8
    var intensity: Double = 0.9

    func body(content: Content) -> some View {
        content
            .shadow(color: color.opacity(intensity), radius: radius * 0.35)
            .shadow(color: color.opacity(intensity * 0.55), radius: radius)
            .shadow(color: color.opacity(intensity * 0.28), radius: radius * 2.2)
    }
}

extension View {
    func glow(_ color: Color, radius: CGFloat = 8, intensity: Double = 0.9) -> some View {
        modifier(Glow(color: color, radius: radius, intensity: intensity))
    }
}

/// A small mono label with wide tracking. Every caption in the design is one.
struct Caption: View {
    var text: String
    var color: Color = Theme.steel
    var size: CGFloat = 10
    var tracking: CGFloat = 2

    var body: some View {
        Text(text)
            .font(Theme.mono(size))
            .tracking(tracking)
            .foregroundStyle(color)
            .lineLimit(1)
    }
}

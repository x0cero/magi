import SwiftUI

/// The palette is four colours and no gradients. Black void, one orange doing
/// nearly all the work, red for the states you are meant to feel, and a bone
/// white for data. Anything else on screen is a mistake.
enum Theme {
    static let void = Color(red: 0.02, green: 0.02, blue: 0.025)
    static let orange = Color(red: 1.0, green: 0.42, blue: 0.0)
    static let orangeDim = Color(red: 0.64, green: 0.27, blue: 0.0)
    static let red = Color(red: 1.0, green: 0.18, blue: 0.09)
    static let green = Color(red: 0.33, green: 0.84, blue: 0.35)
    static let bone = Color(red: 0.91, green: 0.89, blue: 0.83)
    static let steel = Color(red: 0.35, green: 0.40, blue: 0.45)

    static func color(for verdict: Verdict?) -> Color {
        switch verdict {
        case .accept: return green
        case .reject: return red
        case .conditional, .none: return orange
        }
    }

    /// The show's type is a heavy condensed gothic. Avenir Next Condensed is
    /// the closest face that ships with macOS, so nothing has to be bundled and
    /// the app cannot fall back to a proportional system font mid-render.
    static func display(_ size: CGFloat, weight: Font.Weight = .bold) -> Font {
        .custom("AvenirNextCondensed-Bold", fixedSize: size)
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

/// Everything on this display glows. A flat orange rectangle reads as a web
/// page; the same rectangle with its own light spilling past the edge reads as
/// a CRT, and that difference is most of the look.
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

/// Scanlines, drawn rather than shaded, so they survive on any GPU and stay
/// crisp at any window size.
struct Scanlines: View {
    var spacing: CGFloat = 3
    var opacity: Double = 0.32

    var body: some View {
        GeometryReader { geometry in
            Canvas { context, size in
                var y: CGFloat = 0
                while y < size.height {
                    context.fill(
                        Path(CGRect(x: 0, y: y, width: size.width, height: 1)),
                        with: .color(.black.opacity(opacity))
                    )
                    y += spacing
                }
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
        .allowsHitTesting(false)
        .blendMode(.multiply)
    }
}

/// The vignette and the faint bloom wash that sit over the whole screen.
struct ScreenGlass: View {
    var body: some View {
        ZStack {
            RadialGradient(
                colors: [.clear, .black.opacity(0.55)],
                center: .center,
                startRadius: 220,
                endRadius: 900
            )
            Scanlines()
        }
        .allowsHitTesting(false)
    }
}

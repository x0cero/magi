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

    /// The units themselves are filled panels of pale mint with black text.
    /// This is the single most identifying colour of the display and the thing
    /// the first build got wrong: outlined orange hexagons read as a dark-mode
    /// dashboard, filled mint quadrilaterals read as the MAGI.
    static let unit = Color(red: 0.56, green: 0.93, blue: 0.71)
    static let unitReject = Color(red: 0.98, green: 0.31, blue: 0.26)

    /// Waiting is a dimmer green, never a grey wash. The reference reads "ALL
    /// GREEN" at rest, and a translucent grey slab let the seams show through
    /// the middle of it and turned three shapes into one smear.
    static let unitResting = Color(red: 0.22, green: 0.42, blue: 0.33)

    /// Fill for a unit that has answered. Red when it says no, mint otherwise.
    static func unitFill(for verdict: Verdict?, decided: Bool) -> Color {
        guard decided else { return unitResting }
        return verdict == .reject ? unitReject : unit
    }

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
        // Order matters: a blend mode composites the view into its own layer,
        // and that layer takes hit testing back. Applying the pass-through
        // last is the difference between a CRT overlay and a sheet of glass
        // that eats every click in the window.
        .blendMode(.multiply)
        .allowsHitTesting(false)
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
        .compositingGroup()
        .allowsHitTesting(false)
    }
}

/// The schematic the display sits on. The reference is never a clean surface:
/// there is always a wireframe under everything, dim enough to read as texture
/// rather than content. Without it the panels float on flat black and the whole
/// thing reads as a website with an orange accent colour.
struct Schematic: View {
    var body: some View {
        Canvas { context, size in
            let centre = CGPoint(x: size.width / 2, y: size.height * 0.46)
            let line = GraphicsContext.Shading.color(Theme.orange.opacity(0.085))
            let faint = GraphicsContext.Shading.color(Theme.orange.opacity(0.045))

            // Concentric rings around the junction the three units feed.
            for radius in stride(from: 90.0, through: max(size.width, size.height), by: 118) {
                context.stroke(
                    Path(ellipseIn: CGRect(x: centre.x - radius, y: centre.y - radius,
                                           width: radius * 2, height: radius * 2)),
                    with: faint, lineWidth: 1
                )
            }

            // Grid.
            var x: CGFloat = 0
            while x < size.width {
                context.stroke(Path { $0.move(to: CGPoint(x: x, y: 0))
                                      $0.addLine(to: CGPoint(x: x, y: size.height)) },
                               with: faint, lineWidth: 0.5)
                x += 68
            }
            var y: CGFloat = 0
            while y < size.height {
                context.stroke(Path { $0.move(to: CGPoint(x: 0, y: y))
                                      $0.addLine(to: CGPoint(x: size.width, y: y)) },
                               with: faint, lineWidth: 0.5)
                y += 68
            }

            // Sight lines out of the junction, at the angles the units sit on.
            for angle in [212.0, 328.0, 90.0] {
                let radians = angle * .pi / 180
                context.stroke(
                    Path { path in
                        path.move(to: centre)
                        path.addLine(to: CGPoint(x: centre.x + cos(radians) * size.width,
                                                 y: centre.y + sin(radians) * size.width))
                    },
                    with: line, lineWidth: 1
                )
            }
        }
        .allowsHitTesting(false)
    }
}

/// A solid plate of colour with the text cut out of it. The single most
/// recognisable element of the reference, and the reason a heading here never
/// looks like a heading on a web page.
struct Plate: View {
    var text: String
    var color: Color = Theme.orange
    var size: CGFloat = 13
    var tracking: CGFloat = 3

    var body: some View {
        Text(text)
            .font(Theme.display(size))
            .tracking(tracking)
            .foregroundStyle(Theme.void)
            .padding(.horizontal, 9)
            .padding(.vertical, 3)
            .background(color)
    }
}

/// Corner ticks. Every framed region on the reference is registered with them.
struct CornerTicks: View {
    var color: Color = Theme.orangeDim
    var length: CGFloat = 13

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let height = geometry.size.height
            Path { path in
                for corner in [CGPoint(x: 0, y: 0), CGPoint(x: width, y: 0),
                               CGPoint(x: 0, y: height), CGPoint(x: width, y: height)] {
                    let dx: CGFloat = corner.x == 0 ? length : -length
                    let dy: CGFloat = corner.y == 0 ? length : -length
                    path.move(to: CGPoint(x: corner.x + dx, y: corner.y))
                    path.addLine(to: corner)
                    path.addLine(to: CGPoint(x: corner.x, y: corner.y + dy))
                }
            }
            .stroke(color, lineWidth: 1)
        }
        .allowsHitTesting(false)
    }
}

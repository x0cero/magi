import CoreGraphics
import Foundation

/// Every element of the display, positioned on one canvas.
///
/// The reference is not a stack of rows. The two kanji headers sit at the top
/// corners with the top unit rising between them, the code block runs down the
/// left under its header, the boxed readout sits on the right under its own,
/// and the two lower units sit along the bottom with MAGI in the gap. Laying
/// it out as a vertical stack, as the previous build did, squeezed the three
/// units into a small cluster in the middle of an empty frame.
///
/// All coordinates are fractions of the whole panel.
enum Seats {

    static let shapes: [String: [CGPoint]] = [
        // Top centre, rising between the two headers. Lower corners cut in.
        "BALTHASAR": [
            CGPoint(x: 0.335, y: 0.030), CGPoint(x: 0.665, y: 0.030),
            CGPoint(x: 0.665, y: 0.487), CGPoint(x: 0.628, y: 0.560),
            CGPoint(x: 0.372, y: 0.560), CGPoint(x: 0.335, y: 0.487),
        ],
        // Bottom left, inner top corner cut away toward the centre.
        "CASPER": [
            CGPoint(x: 0.030, y: 0.618), CGPoint(x: 0.300, y: 0.618),
            CGPoint(x: 0.400, y: 0.694), CGPoint(x: 0.400, y: 0.872),
            CGPoint(x: 0.030, y: 0.872),
        ],
        // Bottom right, mirrored.
        "MELCHIOR": [
            CGPoint(x: 0.700, y: 0.618), CGPoint(x: 0.970, y: 0.618),
            CGPoint(x: 0.970, y: 0.872), CGPoint(x: 0.600, y: 0.872),
            CGPoint(x: 0.600, y: 0.694),
        ],
    ]

    /// Amber bars bridging the gaps: two short diagonals down from the top
    /// unit, and one bar joining the bottom pair under MAGI.
    static let bars: [[CGPoint]] = [
        [CGPoint(x: 0.372, y: 0.560), CGPoint(x: 0.300, y: 0.618),
         CGPoint(x: 0.328, y: 0.646), CGPoint(x: 0.400, y: 0.588)],
        [CGPoint(x: 0.628, y: 0.560), CGPoint(x: 0.700, y: 0.618),
         CGPoint(x: 0.672, y: 0.646), CGPoint(x: 0.600, y: 0.588)],
        [CGPoint(x: 0.400, y: 0.788), CGPoint(x: 0.600, y: 0.788),
         CGPoint(x: 0.600, y: 0.838), CGPoint(x: 0.400, y: 0.838)],
    ]

    static let hub = CGPoint(x: 0.500, y: 0.700)

    static let labels: [String: CGPoint] = [
        "BALTHASAR": CGPoint(x: 0.500, y: 0.300),
        "CASPER": CGPoint(x: 0.205, y: 0.748),
        "MELCHIOR": CGPoint(x: 0.795, y: 0.748),
    ]

    static let labelWidths: [String: CGFloat] = [
        "BALTHASAR": 0.30, "CASPER": 0.33, "MELCHIOR": 0.33,
    ]

    // Chrome around the units.
    static let headerLeft = CGPoint(x: 0.150, y: 0.098)
    static let headerRight = CGPoint(x: 0.850, y: 0.098)
    static let codeBlock = CGPoint(x: 0.040, y: 0.330)   // centre of the block
    static let infoBox = CGPoint(x: 0.845, y: 0.360)

    static let order = ["BALTHASAR", "CASPER", "MELCHIOR"]
}

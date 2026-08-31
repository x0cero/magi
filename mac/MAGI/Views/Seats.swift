import CoreGraphics
import Foundation

/// Cuts one rectangle into three interlocking slabs.
///
/// The first attempt placed the corners of each slab by hand. They overlapped,
/// the seams drawn under them showed through, and the whole thing rendered as a
/// grey smear. This computes the partition instead: three rays out of a shared
/// centre, each slab is the wedge between two consecutive rays plus whatever
/// rectangle corners fall inside it, then every slab is pulled in from its own
/// centroid so the gaps between them are real gaps rather than drawn lines.
///
/// Guarantees, which is the point of doing it this way: the slabs tile the
/// rectangle, they never overlap, and the seams are the same width everywhere.
enum Seats {

    /// Screen angles in degrees, 0 pointing right and positive going down.
    /// These place CASPER across the left, BALTHASAR top right and MELCHIOR
    /// bottom right, which is the arrangement on the reference.
    private static let cuts: [CGFloat] = [-78, 6, 116]

    static let centre = CGPoint(x: 0.50, y: 0.50)

    /// Seat order matches `cuts`: the wedge after each cut, going clockwise.
    static let order = ["top", "bottom", "left"]

    static func polygon(_ seat: String, gap: CGFloat = 0.013) -> [CGPoint] {
        guard let index = order.firstIndex(of: seat) else { return [] }
        let from = cuts[index]
        let to = cuts[(index + 1) % cuts.count]
        return inset(wedge(from: from, to: to), by: gap)
    }

    /// The wedge between two rays: centre, out along the first ray, around the
    /// rectangle picking up any corners in between, back in along the second.
    private static func wedge(from: CGFloat, to: CGFloat) -> [CGPoint] {
        var points = [centre, edgePoint(at: from)]
        for corner in cornersBetween(from: from, to: to) { points.append(corner) }
        points.append(edgePoint(at: to))
        return points
    }

    /// Where a ray from the centre leaves the unit square.
    private static func edgePoint(at degrees: CGFloat) -> CGPoint {
        let radians = degrees * .pi / 180
        let dx = cos(radians), dy = sin(radians)
        // Distance to each of the four edges; the nearest positive one wins.
        var best = CGFloat.greatestFiniteMagnitude
        if dx > 0 { best = min(best, (1 - centre.x) / dx) }
        if dx < 0 { best = min(best, (0 - centre.x) / dx) }
        if dy > 0 { best = min(best, (1 - centre.y) / dy) }
        if dy < 0 { best = min(best, (0 - centre.y) / dy) }
        return CGPoint(x: centre.x + dx * best, y: centre.y + dy * best)
    }

    private static let corners = [
        CGPoint(x: 1, y: 0), CGPoint(x: 1, y: 1),
        CGPoint(x: 0, y: 1), CGPoint(x: 0, y: 0),
    ]

    /// Rectangle corners lying inside the wedge, in clockwise order.
    private static func cornersBetween(from: CGFloat, to: CGFloat) -> [CGPoint] {
        let start = normalise(from)
        let sweep = normalise(to - from)
        return corners
            .map { corner -> (CGPoint, CGFloat) in
                let angle = atan2(corner.y - centre.y, corner.x - centre.x) * 180 / .pi
                return (corner, normalise(angle - start))
            }
            .filter { $0.1 > 0.0001 && $0.1 < sweep - 0.0001 }
            .sorted { $0.1 < $1.1 }
            .map(\.0)
    }

    private static func normalise(_ degrees: CGFloat) -> CGFloat {
        var value = degrees.truncatingRemainder(dividingBy: 360)
        if value < 0 { value += 360 }
        return value
    }

    /// Pull every corner toward the polygon's own centroid. Uniform in
    /// normalised space, which is what makes every seam the same width.
    private static func inset(_ points: [CGPoint], by amount: CGFloat) -> [CGPoint] {
        guard !points.isEmpty else { return points }
        let centroid = CGPoint(
            x: points.map(\.x).reduce(0, +) / CGFloat(points.count),
            y: points.map(\.y).reduce(0, +) / CGFloat(points.count)
        )
        let scale = 1 - amount * 2
        return points.map { point in
            CGPoint(x: centroid.x + (point.x - centroid.x) * scale,
                    y: centroid.y + (point.y - centroid.y) * scale)
        }
    }

    /// Where a seat's label sits: the centroid of its own slab, nudged away
    /// from the centre so it never collides with the MAGI hub.
    static func labelAnchor(_ seat: String) -> CGPoint {
        let points = polygon(seat)
        guard !points.isEmpty else { return centre }
        let centroid = CGPoint(
            x: points.map(\.x).reduce(0, +) / CGFloat(points.count),
            y: points.map(\.y).reduce(0, +) / CGFloat(points.count)
        )
        let dx = centroid.x - centre.x, dy = centroid.y - centre.y
        return CGPoint(x: centre.x + dx * 1.28, y: centre.y + dy * 1.28)
    }

    static func seat(for member: String) -> String {
        switch member {
        case "BALTHASAR": return "top"
        case "MELCHIOR": return "bottom"
        default: return "left"
        }
    }
}

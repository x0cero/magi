import AppKit
import SwiftUI

/// Renders the interface to a PNG and exits.
///
/// Exists because the only way to judge this thing is to look at it, and the
/// alternative was taking over the user's screen to do it. Run:
///
///     MAGI.app/Contents/MacOS/MAGI --render /tmp/shot.png --state answered
///
/// The states are the ones worth checking: `idle` before anything is asked,
/// `thinking` with one seat still out, and `answered` with a split decision,
/// which is the case where the colours have to work hardest.
enum Preview {

    /// True only in the offline render path.
    static var rendering = false

    @MainActor
    static func runIfRequested() -> Bool {
        let args = CommandLine.arguments
        guard let flag = args.firstIndex(of: "--render"), args.count > flag + 1 else { return false }
        let path = args[flag + 1]
        var state = "answered"
        if let s = args.firstIndex(of: "--state"), args.count > s + 1 { state = args[s + 1] }
        let width = Double(value(of: "--width", in: args) ?? "1180") ?? 1180
        let height = Double(value(of: "--height", in: args) ?? "900") ?? 900

        rendering = true
        let council = Council.preview(state)
        let view = ContentView(previewCouncil: council)
            .frame(width: width, height: height)

        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        guard let image = renderer.nsImage,
              let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:])
        else {
            FileHandle.standardError.write("render failed\n".data(using: .utf8)!)
            exit(1)
        }
        try? png.write(to: URL(fileURLWithPath: path))
        print("wrote \(path)")
        exit(0)
    }

    private static func value(of flag: String, in args: [String]) -> String? {
        guard let index = args.firstIndex(of: flag), args.count > index + 1 else { return nil }
        return args[index + 1]
    }
}

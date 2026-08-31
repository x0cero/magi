import AVFoundation
import SwiftUI

/// Console tones, synthesised in the app rather than shipped as files.
///
/// Nothing here is sampled from the show: that audio is Khara's. These are
/// built from arithmetic for the same reason the Python side builds its own,
/// and kept deliberately dry and short, because a cue that plays three times a
/// round becomes irritating long before it becomes atmospheric.
@MainActor
final class Audio: ObservableObject {

    enum Cue {
        case boot, report, consensus, majority, tiebreak, error
    }

    @AppStorage("soundEnabled") var enabled: Bool = true

    /// Drop your own audio here and it is used instead of the synthesised
    /// tone. One file per cue, named for it: boot, report, consensus,
    /// majority, tiebreak, error. Any format AVAudioFile reads (wav, aiff,
    /// m4a, mp3) works.
    ///
    /// Its own folder, which nothing else writes to. The CLI generates its
    /// tones into `sounds/`, so putting user audio there would collide with a
    /// file the CLI may overwrite.
    ///
    /// Nothing is shipped here and nothing is fetched. The audio from the show
    /// belongs to Khara, so supplying it is the user's own business on their
    /// own machine; this is only the hook that plays what is already there.
    static var soundsDirectory: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/magi/sounds/custom", isDirectory: true)
    }

    private static let extensions = ["wav", "aiff", "aif", "m4a", "mp3", "caf"]

    private let engine = AVAudioEngine()
    private var players: [Cue: AVAudioPlayerNode] = [:]
    private var buffers: [Cue: AVAudioPCMBuffer] = [:]
    private var started = false

    private let sampleRate: Double = 44_100

    init() {
        prepare()
    }

    private func prepare() {
        let synthesised = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
        for cue in [Cue.boot, .report, .consensus, .majority, .tiebreak, .error] {
            // A file you supplied wins over the built-in tone.
            let loaded = loadFile(for: cue)
            let buffer = loaded ?? render(cue, format: synthesised)
            guard let buffer else { continue }
            let player = AVAudioPlayerNode()
            engine.attach(player)
            engine.connect(player, to: engine.mainMixerNode, format: buffer.format)
            players[cue] = player
            buffers[cue] = buffer
        }
        engine.mainMixerNode.outputVolume = 0.5
    }

    /// Read a cue from disk if the user put one there. Any failure falls back
    /// to the synthesised tone rather than going silent.
    private func loadFile(for cue: Cue) -> AVAudioPCMBuffer? {
        let base = Self.soundsDirectory.appendingPathComponent(name(of: cue))
        for ext in Self.extensions {
            let url = base.appendingPathExtension(ext)
            guard FileManager.default.fileExists(atPath: url.path) else { continue }
            guard let file = try? AVAudioFile(forReading: url) else { continue }
            let frames = AVAudioFrameCount(file.length)
            guard frames > 0,
                  let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat,
                                                frameCapacity: frames),
                  (try? file.read(into: buffer)) != nil
            else { continue }
            return buffer
        }
        return nil
    }

    private func name(of cue: Cue) -> String {
        switch cue {
        case .boot: return "boot"
        case .report: return "report"
        case .consensus: return "consensus"
        case .majority: return "majority"
        case .tiebreak: return "tiebreak"
        case .error: return "error"
        }
    }

    /// Which cues are currently coming from a file rather than from arithmetic.
    var suppliedCues: [String] {
        [Cue.boot, .report, .consensus, .majority, .tiebreak, .error]
            .filter { loadFile(for: $0) != nil }
            .map { name(of: $0) }
    }

    private func start() {
        guard !started else { return }
        do {
            try engine.start()
            players.values.forEach { $0.play() }
            started = true
        } catch {
            // No audio device, or the engine refused to start. Silence is the
            // correct outcome; a decision tool must not fail over a beep.
            started = false
        }
    }

    func play(_ cue: Cue) {
        guard enabled, let player = players[cue], let buffer = buffers[cue] else { return }
        start()
        guard started else { return }
        player.scheduleBuffer(buffer, at: nil, options: .interrupts)
    }

    func playOutcome(_ outcome: String) {
        switch outcome {
        case "consensus", "picks": play(.consensus)
        case "majority": play(.majority)
        case "conviction", "tiebreak", "deadlock", "split": play(.tiebreak)
        case "incomplete", "noise": play(.error)
        default: play(.majority)
        }
    }

    // MARK: - Synthesis

    private func render(_ cue: Cue, format: AVAudioFormat) -> AVAudioPCMBuffer? {
        let samples = samples(for: cue)
        guard !samples.isEmpty,
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count))
        else { return nil }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        guard let channel = buffer.floatChannelData?[0] else { return nil }
        for (index, value) in samples.enumerated() { channel[index] = Float(value) }
        return buffer
    }

    /// A tone chopped rapidly by an amplitude gate.
    ///
    /// This is the character the whole set is built on, chosen by ear over
    /// three alternatives. The console does not beep, it buzzes: a held tone
    /// gated around thirty times a second reads as a machine working, where a
    /// clean pip reads as an app notification. Pitch and length carry the
    /// meaning; the chopping stays constant so the cues are one machine.
    ///
    /// Kept in step with the CLI's set in magi/sound.py.
    private func tremolo(_ freq: Double, _ seconds: Double, rate: Double,
                         volume: Double = 0.15, wave: Wave = .square) -> [Double] {
        let base = tone(from: freq, to: freq, seconds: seconds, wave: wave, volume: volume)
        return base.enumerated().map { index, sample in
            let gate = (Double(index) * rate / sampleRate).truncatingRemainder(dividingBy: 1) < 0.5
            return gate ? sample : 0
        }
    }

    private func silence(_ seconds: Double) -> [Double] {
        [Double](repeating: 0, count: Int(sampleRate * seconds))
    }

    private func samples(for cue: Cue) -> [Double] {
        switch cue {
        case .boot:
            return tremolo(196, 0.42, rate: 24)
                + silence(0.03)
                + tremolo(392, 0.30, rate: 30)
        case .report:
            // Fires three times a round, so it has no tail.
            return tremolo(440, 0.13, rate: 28)
        case .consensus:
            return tremolo(523, 0.20, rate: 30)
                + tremolo(659, 0.20, rate: 30)
                + tone(from: 784, to: 784, seconds: 0.34, wave: .square, volume: 0.12)
        case .majority:
            // Lands flat: nothing climbs, because somebody lost.
            return tremolo(440, 0.22, rate: 28)
                + tone(from: 440, to: 440, seconds: 0.26, wave: .square, volume: 0.12)
        case .tiebreak:
            // Steps down and stops without resolving.
            return tremolo(415, 0.20, rate: 26)
                + tremolo(311, 0.24, rate: 22, volume: 0.14)
        case .error:
            return tremolo(147, 0.40, rate: 16, volume: 0.19, wave: .saw)
        }
    }

    private enum Wave { case sine, square, saw }

    /// Linear attack, exponential release. A tone that starts and stops at full
    /// amplitude clicks audibly, and three clicks a round is a rattle.
    private func envelope(_ index: Int, _ total: Int) -> Double {
        let t = Double(index) / Double(total)
        let attack = 0.01, release = 0.25
        if t < attack { return t / attack }
        if t > 1 - release { return pow(max(0, (1 - t) / release), 1.5) }
        return 1
    }

    private func tone(from: Double, to: Double, seconds: Double, wave: Wave, volume: Double) -> [Double] {
        let count = Int(sampleRate * seconds)
        var phase = 0.0
        var out: [Double] = []
        out.reserveCapacity(count)
        for index in 0..<count {
            let frequency = from + (to - from) * (Double(index) / Double(count))
            phase += frequency / sampleRate
            let sample: Double
            switch wave {
            case .sine: sample = sin(2 * .pi * phase)
            case .square: sample = phase.truncatingRemainder(dividingBy: 1) < 0.35 ? 1 : -1
            case .saw: sample = 2 * phase.truncatingRemainder(dividingBy: 1) - 1
            }
            out.append(sample * volume * envelope(index, count))
        }
        return out
    }

    private func mix(_ layers: [Double]...) -> [Double] {
        let length = layers.map(\.count).max() ?? 0
        var out = [Double](repeating: 0, count: length)
        for layer in layers {
            for (index, sample) in layer.enumerated() { out[index] += sample }
        }
        return out.map { max(-1, min(1, $0)) }
    }
}

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

    /// Short, high, and doubled. A held tone reads as a notification; a burst
    /// of very short pips reads as a machine reporting. Kept in step with the
    /// CLI's cues in magi/sound.py so both halves sound the same.
    private func pip(_ freq: Double, _ seconds: Double = 0.032,
                     _ volume: Double = 0.20, _ wave: Wave = .sine) -> [Double] {
        tone(from: freq, to: freq, seconds: seconds, wave: wave, volume: volume)
    }

    private func burst(_ freqs: [Double], gap: Double = 0.028,
                       seconds: Double = 0.032, volume: Double = 0.20) -> [Double] {
        var out: [Double] = []
        for (index, freq) in freqs.enumerated() {
            if index > 0 { out += [Double](repeating: 0, count: Int(sampleRate * gap)) }
            out += pip(freq, seconds, volume)
        }
        return out
    }

    private func silence(_ seconds: Double) -> [Double] {
        [Double](repeating: 0, count: Int(sampleRate * seconds))
    }

    private func samples(for cue: Cue) -> [Double] {
        switch cue {
        case .boot:
            return mix(tone(from: 120, to: 520, seconds: 0.62, wave: .saw, volume: 0.13),
                       silence(0.30) + burst([1568, 1568, 2093], gap: 0.045,
                                             seconds: 0.045, volume: 0.17))
        case .report:
            return burst([1760, 2093], gap: 0.030, seconds: 0.030, volume: 0.15)
        case .consensus:
            return burst([1046, 1319, 1568], gap: 0.038, seconds: 0.042, volume: 0.17)
                + silence(0.02)
                + mix(tone(from: 1568, to: 1568, seconds: 0.30, wave: .sine, volume: 0.16),
                      tone(from: 2093, to: 2093, seconds: 0.30, wave: .sine, volume: 0.08))
        case .majority:
            return burst([1319, 1319], gap: 0.045, seconds: 0.045, volume: 0.17)
                + silence(0.02)
                + tone(from: 1319, to: 1319, seconds: 0.24, wave: .sine, volume: 0.15)
        case .tiebreak:
            // Steps down and stops: they split, so nothing resolves.
            return burst([1175, 988], gap: 0.055, seconds: 0.055, volume: 0.16)
                + silence(0.03)
                + tone(from: 880, to: 880, seconds: 0.26, wave: .square, volume: 0.11)
        case .error:
            return mix(tone(from: 220, to: 98, seconds: 0.34, wave: .saw, volume: 0.20),
                       tone(from: 233, to: 104, seconds: 0.34, wave: .saw, volume: 0.12))
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

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

    private let engine = AVAudioEngine()
    private var players: [Cue: AVAudioPlayerNode] = [:]
    private var buffers: [Cue: AVAudioPCMBuffer] = [:]
    private var started = false

    private let sampleRate: Double = 44_100

    init() {
        prepare()
    }

    private func prepare() {
        let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
        for cue in [Cue.boot, .report, .consensus, .majority, .tiebreak, .error] {
            guard let buffer = render(cue, format: format) else { continue }
            let player = AVAudioPlayerNode()
            engine.attach(player)
            engine.connect(player, to: engine.mainMixerNode, format: format)
            players[cue] = player
            buffers[cue] = buffer
        }
        engine.mainMixerNode.outputVolume = 0.5
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

    private func samples(for cue: Cue) -> [Double] {
        switch cue {
        case .boot:
            return tone(from: 180, to: 760, seconds: 0.5, wave: .saw, volume: 0.22)
                + tone(from: 784, to: 784, seconds: 0.18, wave: .sine, volume: 0.26)
        case .report:
            return tone(from: 1046, to: 1046, seconds: 0.05, wave: .square, volume: 0.15)
        case .consensus:
            return mix(tone(from: 523, to: 659, seconds: 0.42, wave: .sine, volume: 0.24),
                       tone(from: 784, to: 988, seconds: 0.42, wave: .sine, volume: 0.14))
        case .majority:
            return mix(tone(from: 523, to: 523, seconds: 0.32, wave: .sine, volume: 0.22),
                       tone(from: 698, to: 698, seconds: 0.32, wave: .sine, volume: 0.12))
        case .tiebreak:
            // Deliberately does not resolve: the council split.
            return tone(from: 415, to: 415, seconds: 0.28, wave: .square, volume: 0.15)
                + tone(from: 392, to: 392, seconds: 0.32, wave: .square, volume: 0.15)
        case .error:
            return tone(from: 330, to: 110, seconds: 0.3, wave: .saw, volume: 0.22)
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

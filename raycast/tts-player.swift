import AVFoundation
import MediaPlayer
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 24000, channels: 1, interleaved: true)!

    private var pendingBuffers = 0
    private var reachedEOF = false
    private var startedPlayback = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)

        do {
            try engine.start()
        } catch {
            exit(1)
        }

        configureRemoteCommands()
        readFromStdin()
    }

    private func configureRemoteCommands() {
        let center = MPNowPlayingInfoCenter.default()
        center.nowPlayingInfo = [
            MPMediaItemPropertyTitle: "TTS",
            MPMediaItemPropertyArtist: "Raycast TTS",
            MPNowPlayingInfoPropertyPlaybackRate: 0.0
        ]

        let cc = MPRemoteCommandCenter.shared()
        cc.playCommand.addTarget { [weak self] _ in
            self?.player.play()
            self?.updateNowPlaying(isPlaying: true)
            return .success
        }
        cc.pauseCommand.addTarget { [weak self] _ in
            self?.player.pause()
            self?.updateNowPlaying(isPlaying: false)
            return .success
        }
        cc.togglePlayPauseCommand.addTarget { [weak self] _ in
            guard let self else { return .commandFailed }
            if self.player.isPlaying {
                self.player.pause()
                self.updateNowPlaying(isPlaying: false)
            } else {
                self.player.play()
                self.updateNowPlaying(isPlaying: true)
            }
            return .success
        }
    }

    private func updateNowPlaying(isPlaying: Bool) {
        let center = MPNowPlayingInfoCenter.default()
        var info = center.nowPlayingInfo ?? [String: Any]()
        info[MPNowPlayingInfoPropertyPlaybackRate] = isPlaying ? 1.0 : 0.0
        center.nowPlayingInfo = info
    }

    private func readFromStdin() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let stdin = FileHandle.standardInput
            var tail = Data()

            while true {
                let data = stdin.availableData
                if data.isEmpty { break }

                var chunk = Data()
                if !tail.isEmpty {
                    chunk.append(tail)
                    tail.removeAll(keepingCapacity: true)
                }
                chunk.append(data)

                // Keep frame boundaries aligned for Int16 PCM samples.
                if chunk.count % 2 != 0 {
                    tail = chunk.suffix(1)
                    chunk.removeLast()
                }
                if chunk.isEmpty { continue }

                DispatchQueue.main.async {
                    self.enqueue(chunk)
                }
            }

            DispatchQueue.main.async {
                self.reachedEOF = true
                self.checkForExit()
            }
        }
    }

    private func enqueue(_ data: Data) {
        let frameCount = data.count / 2
        guard frameCount > 0 else { return }
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frameCount)) else { return }
        buffer.frameLength = AVAudioFrameCount(frameCount)

        data.withUnsafeBytes { raw in
            guard let src = raw.baseAddress, let dst = buffer.int16ChannelData?[0] else { return }
            memcpy(dst, src, data.count)
        }

        pendingBuffers += 1
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            DispatchQueue.main.async {
                guard let self else { return }
                self.pendingBuffers = max(0, self.pendingBuffers - 1)
                self.checkForExit()
            }
        }

        if !startedPlayback {
            startedPlayback = true
            player.play()
            updateNowPlaying(isPlaying: true)
        }
    }

    private func checkForExit() {
        if reachedEOF && pendingBuffers == 0 {
            NSApp.terminate(nil)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()

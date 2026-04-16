#!/Users/marshtupa/.venvs/raycast/bin/python3

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Speak with Gemini
# @raycast.mode compact
# @raycast.packageName Audio
# @raycast.description Speak text using Gemini 3.1 Flash TTS

# Optional parameters:
# @raycast.icon 🗣️
# @raycast.argument1 { "type": "text", "placeholder": "Text to read", "optional": true }

import asyncio
import os
import sys
import base64
import tempfile
import subprocess
from typing import Optional

# --- Configuration ---
MODEL_NAME = "gemini-3.1-flash-live-preview"
VOICE_NAME = "Puck"
RECEIVE_TIMEOUT_SECONDS = 8
# ---------------------


def get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    try:
        # Launch an interactive shell to source .zshrc and get the key
        res = subprocess.run(
            ["zsh", "-i", "-c", "printenv GEMINI_API_KEY"],
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [line.strip() for line in res.stdout.split("\n") if line.strip()]
        if lines:
            return lines[-1]
    except Exception:
        pass

    return ""


def get_input_text() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()

    try:
        return subprocess.check_output(["pbpaste"], text=True).strip()
    except Exception:
        return ""


def start_streaming_player() -> subprocess.Popen:
    swift_code = """
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
            MPMediaItemPropertyTitle: "Gemini TTS",
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
"""

    swift_path = os.path.join(tempfile.gettempdir(), "raycast_tts_stream_player.swift")
    with open(swift_path, "w") as f:
        f.write(swift_code)

    return subprocess.Popen(
        ["swift", swift_path],
        stdin=subprocess.PIPE,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def stream_with_live_api(api_key: str, input_text: str, player_proc: subprocess.Popen) -> None:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency `google-genai`. Install it with: pip3 install --user google-genai"
        ) from exc

    client = genai.Client(api_key=api_key)
    config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {
                    "voice_name": VOICE_NAME,
                }
            }
        },
    }

    prompt = (
        "Read the following text aloud exactly as written. "
        "Do not add any extra words.\n\n"
        f"{input_text}"
    )

    got_audio = False
    async with client.aio.live.connect(model=MODEL_NAME, config=config) as session:
        await session.send_realtime_input(text=prompt)

        stream = session.receive()
        while True:
            try:
                response = await asyncio.wait_for(anext(stream), timeout=RECEIVE_TIMEOUT_SECONDS)
            except TimeoutError:
                break
            except StopAsyncIteration:
                break

            server_content = getattr(response, "server_content", None)
            if not server_content:
                continue

            model_turn = getattr(server_content, "model_turn", None)
            if model_turn and model_turn.parts:
                for part in model_turn.parts:
                    inline_data = getattr(part, "inline_data", None)
                    if not inline_data or not inline_data.data:
                        continue

                    audio_chunk = inline_data.data
                    if isinstance(audio_chunk, str):
                        audio_chunk = base64.b64decode(audio_chunk)
                    if player_proc.stdin is None:
                        raise RuntimeError("Audio player stdin is not available.")
                    player_proc.stdin.write(audio_chunk)
                    player_proc.stdin.flush()
                    got_audio = True

            if getattr(server_content, "turn_complete", False):
                break

    if not got_audio:
        raise RuntimeError("No audio returned from Gemini Live API.")


def main() -> None:
    api_key = get_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found.")
        sys.exit(1)

    input_text = get_input_text()
    if not input_text:
        print("No text provided or selected.")
        sys.exit(1)

    player_proc: Optional[subprocess.Popen] = None
    try:
        # Start player process early so first audio chunk plays with minimal extra delay.
        player_proc = start_streaming_player()
        asyncio.run(stream_with_live_api(api_key=api_key, input_text=input_text, player_proc=player_proc))
        if player_proc.stdin is not None:
            player_proc.stdin.close()
    except Exception as e:
        if player_proc and player_proc.stdin is not None:
            try:
                player_proc.stdin.close()
            except Exception:
                pass
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

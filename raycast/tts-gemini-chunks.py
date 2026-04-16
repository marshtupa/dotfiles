#!/usr/bin/env python3

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Speak with Gemini
# @raycast.mode compact
# @raycast.packageName Audio
# @raycast.description Speak text using Gemini 3.1 Flash TTS

# Optional parameters:
# @raycast.icon 🗣️
# @raycast.argument1 { "type": "text", "placeholder": "Text to read", "optional": true }

import base64
import concurrent.futures
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import Dict, List, Tuple

# --- Configuration ---
MODEL_NAME = "gemini-3.1-flash-tts-preview"
VOICE_NAME = "Puck"
MAX_WORKERS = 3
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 0.8
FIRST_CHUNK_TARGET_CHARS = 220
CHUNK_TARGET_CHARS = 700
CHUNK_MAX_CHARS = 1000
# ---------------------


def get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    try:
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


def split_text_into_chunks(
    text: str,
    first_target: int = FIRST_CHUNK_TARGET_CHARS,
    target: int = CHUNK_TARGET_CHARS,
    max_len: int = CHUNK_MAX_CHARS,
) -> List[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    sentences = re.split(r"(?<=[.!?…])\s+|(?<=\n)\s*", normalized)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [normalized]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    chunk_idx = 0

    def current_target() -> int:
        return first_target if chunk_idx == 0 else target

    def flush() -> None:
        nonlocal current, current_len, chunk_idx
        if current:
            chunks.append(" ".join(current).strip())
            current = []
            current_len = 0
            chunk_idx += 1

    for sentence in sentences:
        sentence_len = len(sentence)
        if sentence_len > max_len:
            flush()
            start = 0
            while start < sentence_len:
                end = min(start + max_len, sentence_len)
                part = sentence[start:end].strip()
                if part:
                    chunks.append(part)
                    chunk_idx += 1
                start = end
            continue

        target_len = current_target()
        would_be = current_len + (1 if current else 0) + sentence_len
        if current and (would_be > target_len or would_be > max_len):
            flush()
            target_len = current_target()
            would_be = sentence_len

        if would_be > max_len and not current:
            chunks.append(sentence)
            chunk_idx += 1
            continue

        current.append(sentence)
        current_len = would_be

        # Keep first chunk small for faster time-to-first-audio.
        if chunk_idx == 0 and current_len >= first_target:
            flush()

    flush()
    return chunks if chunks else [normalized]


def create_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
        return ctx
    except ImportError:
        pass

    for path in [
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/ca-certificates/cert.pem",
        "/usr/local/etc/openssl/cert.pem",
    ]:
        if os.path.exists(path):
            ctx.load_verify_locations(path)
            break
    return ctx


def request_chunk_audio(
    idx: int, chunk_text: str, api_key: str, ctx: ssl.SSLContext
) -> Tuple[int, bytes]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL_NAME}:generateContent?key={api_key}"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": chunk_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": VOICE_NAME}
                }
            },
        },
    }
    body = json.dumps(payload).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, context=ctx) as response:
                data = json.loads(response.read().decode())

            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            for part in parts:
                inline_data = part.get("inlineData")
                if not inline_data:
                    continue
                mime = inline_data.get("mimeType", "")
                if mime.startswith("audio/l16"):
                    pcm = base64.b64decode(inline_data.get("data", ""))
                    if pcm:
                        return idx, pcm
            raise RuntimeError(f"No audio returned for chunk {idx + 1}.")
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY_SECONDS * (2**attempt)
                time.sleep(delay)
                continue

    if last_error is None:
        raise RuntimeError(f"Failed to generate chunk {idx + 1}.")
    raise RuntimeError(f"Chunk {idx + 1} failed: {last_error}")


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

    swift_path = os.path.join(tempfile.gettempdir(), "raycast_tts_chunked_player.swift")
    with open(swift_path, "w") as f:
        f.write(swift_code)

    return subprocess.Popen(
        ["swift", swift_path],
        stdin=subprocess.PIPE,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stream_chunked_tts(api_key: str, input_text: str) -> None:
    chunks = split_text_into_chunks(input_text)
    if not chunks:
        raise RuntimeError("No text after chunking.")

    ssl_ctx = create_ssl_context()
    player_proc = start_streaming_player()
    if player_proc.stdin is None:
        raise RuntimeError("Audio player stdin is unavailable.")

    ready_audio: Dict[int, bytes] = {}
    next_to_play = 0
    total = len(chunks)

    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(MAX_WORKERS, total)
        ) as executor:
            futures = [
                executor.submit(request_chunk_audio, idx, chunk, api_key, ssl_ctx)
                for idx, chunk in enumerate(chunks)
            ]

            for future in concurrent.futures.as_completed(futures):
                idx, audio = future.result()
                ready_audio[idx] = audio

                while next_to_play in ready_audio:
                    pcm = ready_audio.pop(next_to_play)
                    player_proc.stdin.write(pcm)
                    player_proc.stdin.flush()
                    next_to_play += 1

        if next_to_play != total:
            raise RuntimeError("Not all chunks were played.")
    finally:
        try:
            if player_proc.stdin is not None:
                player_proc.stdin.close()
        except Exception:
            pass


def main() -> None:
    api_key = get_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found.")
        sys.exit(1)

    input_text = get_input_text()
    if not input_text:
        print("No text provided or selected.")
        sys.exit(1)

    try:
        stream_chunked_tts(api_key=api_key, input_text=input_text)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

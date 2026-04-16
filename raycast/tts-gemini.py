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

import os
import sys
import json
import base64
import wave
import tempfile
import subprocess
import urllib.request
import ssl
import time

# --- Configuration ---
MODEL_NAME = "gemini-3.1-flash-tts-preview"
# ---------------------

# Extract API key
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    try:
        # Launch an interactive shell to source .zshrc and get the key
        res = subprocess.run(
            ['zsh', '-i', '-c', 'printenv GEMINI_API_KEY'], 
            capture_output=True, text=True
        )
        lines = [l.strip() for l in res.stdout.split('\n') if l.strip()]
        if lines:
            # printenv will print the key on the last line
            API_KEY = lines[-1]
    except Exception:
        pass

if not API_KEY:
    print("Error: GEMINI_API_KEY not found.")
    sys.exit(1)

# Get input text
input_text = ""
if len(sys.argv) > 1 and sys.argv[1].strip():
    input_text = sys.argv[1].strip()
else:
    try:
        input_text = subprocess.check_output(['pbpaste'], text=True).strip()
    except Exception:
        pass

if not input_text:
    print("No text provided or selected.")
    sys.exit(1)

# Endpoint for Gemini TTS
url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"

payload = {
    "contents": [{"role": "user", "parts": [{"text": input_text}]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {
                    "voiceName": "Puck"
                }
            }
        }
    }
}

try:
    ctx = ssl.create_default_context()
    
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        for path in ["/etc/ssl/cert.pem", "/opt/homebrew/etc/ca-certificates/cert.pem", "/usr/local/etc/openssl/cert.pem"]:
            if os.path.exists(path):
                ctx.load_verify_locations(path)
                break

    req = urllib.request.Request(url, json.dumps(payload).encode('utf-8'), {'Content-Type': 'application/json'})
    
    max_retries = 1
    data = None
    last_error = None
    
    for attempt in range(max_retries):
        try:
            response = urllib.request.urlopen(req, context=ctx)
            data = json.loads(response.read().decode())
            break
        except Exception as e:
            last_error = e
            if "EOF occurred in violation of protocol" in str(e):
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            raise e
            
    if not data:
        raise last_error
    
    parts = data.get('candidates', [{}])[0].get('content', {}).get('parts', [])
    audio_data = None
    for part in parts:
        if 'inlineData' in part and part['inlineData'].get('mimeType', '').startswith('audio/l16'):
            audio_data = base64.b64decode(part['inlineData']['data'])
            break
            
    if not audio_data:
        print("No audio returned from Gemini.")
        sys.exit(1)
        
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        # Gemini outputs 16-bit PCM at 24000 Hz, 1 channel
        with wave.open(tmp, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16 bits = 2 bytes
            wav_file.setframerate(24000)
            wav_file.writeframes(audio_data)

    swift_code = """
import AVFoundation
import MediaPlayer
import AppKit

guard CommandLine.arguments.count > 1 else { exit(1) }
let url = URL(fileURLWithPath: CommandLine.arguments[1])

class AppDelegate: NSObject, NSApplicationDelegate, AVAudioPlayerDelegate {
    var player: AVAudioPlayer!
    
    func updateNowPlaying() {
        let center = MPNowPlayingInfoCenter.default()
        var info = center.nowPlayingInfo ?? [String: Any]()
        info[MPNowPlayingInfoPropertyPlaybackRate] = player.isPlaying ? 1.0 : 0.0
        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = player.currentTime
        info[MPMediaItemPropertyPlaybackDuration] = player.duration
        center.nowPlayingInfo = info
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            player = try AVAudioPlayer(contentsOf: url)
            player.delegate = self
            player.play()
            
            let center = MPNowPlayingInfoCenter.default()
            center.nowPlayingInfo = [
                MPMediaItemPropertyTitle: "Gemini TTS",
                MPMediaItemPropertyArtist: "Raycast TTS",
                MPMediaItemPropertyPlaybackDuration: player.duration,
                MPNowPlayingInfoPropertyElapsedPlaybackTime: player.currentTime,
                MPNowPlayingInfoPropertyPlaybackRate: 1.0
            ]
            
            let cc = MPRemoteCommandCenter.shared()
            cc.playCommand.addTarget { [weak self] _ in
                self?.player.play()
                self?.updateNowPlaying()
                return .success
            }
            cc.pauseCommand.addTarget { [weak self] _ in
                self?.player.pause()
                self?.updateNowPlaying()
                return .success
            }
            cc.togglePlayPauseCommand.addTarget { [weak self] _ in
                guard let self = self else { return .commandFailed }
                if self.player.isPlaying { self.player.pause() } else { self.player.play() }
                self.updateNowPlaying()
                return .success
            }
            
            cc.skipForwardCommand.preferredIntervals = [15]
            cc.skipForwardCommand.addTarget { [weak self] event in
                guard let self = self, let e = event as? MPSkipIntervalCommandEvent else { return .commandFailed }
                self.player.currentTime = min(self.player.currentTime + e.interval, self.player.duration)
                self.updateNowPlaying()
                return .success
            }
            
            cc.skipBackwardCommand.preferredIntervals = [15]
            cc.skipBackwardCommand.addTarget { [weak self] event in
                guard let self = self, let e = event as? MPSkipIntervalCommandEvent else { return .commandFailed }
                self.player.currentTime = max(self.player.currentTime - e.interval, 0)
                self.updateNowPlaying()
                return .success
            }
            
            cc.changePlaybackPositionCommand.addTarget { [weak self] event in
                guard let self = self, let e = event as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
                self.player.currentTime = e.positionTime
                self.updateNowPlaying()
                return .success
            }
            
        } catch { exit(1) }
    }
    
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        exit(0)
    }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
"""
    swift_path = os.path.join(tempfile.gettempdir(), "raycast_tts_player.swift")
    with open(swift_path, "w") as f:
        f.write(swift_code)
        
    # Play using macOS AVFoundation Swift script for media keys.
    # Keep generated audio file after playback.
    cmd = f"swift '{swift_path}' '{tmp_path}'"
    subprocess.Popen(["sh", "-c", cmd], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
except Exception as e:
    if hasattr(e, 'read'):
        err_msg = e.read().decode()
        try:
            parsed = json.loads(err_msg)
            print(f"API Error: {parsed.get('error', {}).get('message', err_msg)}")
        except Exception:
            print(f"API Error: {err_msg}")
    else:
        print(f"Error: {e}")

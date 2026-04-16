import os
import sys
import json
import base64
import urllib.request
import ssl
import wave
import time
import subprocess
import tempfile
import pathlib

# Get API key for Gemini
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    try:
        res = subprocess.run(['zsh', '-i', '-c', 'printenv GEMINI_API_KEY'], capture_output=True, text=True)
        lines = [l.strip() for l in res.stdout.split('\n') if l.strip()]
        if lines:
            API_KEY = lines[-1]
    except Exception:
        pass

SERVICE_ACCOUNT_PATH = os.path.expanduser("~/dotfiles/symlinks/.zshrc.d/.local.gen-lang-client-0857982502-b644762a850f.json")

text = "Я сегодня дебажил фичу в Xcode, но получил странный Exception. Мой PR уже апрувнули. Это стоило мне $4M, LMAO. Как же я устал."

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 1. Legacy TTS (Russian model)
try:
    with open(SERVICE_ACCOUNT_PATH, 'r') as f:
        sa = json.load(f)
    
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claim = {
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "aud": "https://oauth2.googleapis.com/token",
        "exp": now + 3600,
        "iat": now
    }
    
    def b64url(s):
        if isinstance(s, str): s = s.encode()
        return base64.urlsafe_b64encode(s).replace(b'=', b'')
    
    msg = b64url(json.dumps(header)) + b"." + b64url(json.dumps(claim))
    with tempfile.NamedTemporaryFile('w', delete=False) as kf:
        kf.write(sa["private_key"])
        kpath = kf.name
    try:
        p = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', kpath], input=msg, capture_output=True, check=True)
        sig = b64url(p.stdout)
    finally:
        os.unlink(kpath)
    
    jwt = msg + b"." + sig
    data_str = f"grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion={jwt.decode()}".encode()
    req_token = urllib.request.Request("https://oauth2.googleapis.com/token", data=data_str)
    with urllib.request.urlopen(req_token, context=ctx) as resp:
        token = json.loads(resp.read())["access_token"]
        
    url_legacy = "https://texttospeech.googleapis.com/v1/text:synthesize"
    headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {token}"}
    payload_legacy = {
        "input": {"text": text},
        "voice": {"languageCode": "ru-RU", "name": "ru-RU-Wavenet-D"},
        "audioConfig": {"audioEncoding": "MP3"}
    }

    req = urllib.request.Request(url_legacy, json.dumps(payload_legacy).encode('utf-8'), headers)
    resp = urllib.request.urlopen(req, context=ctx)
    data = json.loads(resp.read().decode())
    with open("/tmp/legacy_ru.mp3", "wb") as f:
        f.write(base64.b64decode(data['audioContent']))
    print("Legacy TTS saved to /tmp/legacy_ru.mp3")
except Exception as e:
    print("Error Legacy:", e.read().decode() if hasattr(e, 'read') else str(e))

# 2. Gemini TTS
url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={API_KEY}"
payload_gemini = {
    "contents": [{"role": "user", "parts": [{"text": text}]}],
    "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}}}
}
req = urllib.request.Request(url_gemini, json.dumps(payload_gemini).encode('utf-8'), {'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req, context=ctx)
    data = json.loads(resp.read().decode())
    parts = data.get('candidates', [{}])[0].get('content', {}).get('parts', [])
    audio_data = None
    for part in parts:
        if 'inlineData' in part:
            audio_data = base64.b64decode(part['inlineData']['data'])
            break
    if audio_data:
        with wave.open("/tmp/gemini_ru.wav", 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(audio_data)
        print("Gemini TTS saved to /tmp/gemini_ru.wav")
except Exception as e:
    print("Error Gemini:", e.read().decode() if hasattr(e, 'read') else str(e))

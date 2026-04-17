#!/usr/bin/env python3

import argparse
import asyncio
import base64
import os
import pathlib
import subprocess
import sys
import wave
from typing import Iterable

MODEL_NAME = "gemini-3.1-flash-live-preview"
SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2
CHANNELS = 1
RECEIVE_TIMEOUT_SECONDS = 12

# Official prebuilt voices listed in Gemini TTS docs.
VOICE_NAMES = [
    "Zephyr",
    "Puck",
    "Charon",
    "Kore",
    "Fenrir",
    "Leda",
    "Orus",
    "Aoede",
    "Callirrhoe",
    "Autonoe",
    "Enceladus",
    "Iapetus",
    "Umbriel",
    "Algieba",
    "Despina",
    "Erinome",
    "Algenib",
    "Rasalgethi",
    "Laomedeia",
    "Achernar",
    "Alnilam",
    "Schedar",
    "Gacrux",
    "Pulcherrima",
    "Achird",
    "Zubenelgenubi",
    "Vindemiatrix",
    "Sadachbia",
    "Sadaltager",
    "Sulafat",
]

DEFAULT_TEXT = (
    "Я сегодня дебажил фичу в Xcode, но получил странный Exception. "
    "Мой PR уже апрувнули. Это стоило мне $4M, LMAO. Как же я устал."
)


def get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
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


def write_wav_file(path: pathlib.Path, pcm_data: bytes) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)


async def generate_voice_demo(client, text: str, voice_name: str) -> bytes:
    config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {
                    "voice_name": voice_name,
                }
            }
        },
    }

    prompt = (
        "Read the following text aloud exactly as written. "
        "Do not add extra words.\n\n"
        f"{text}"
    )

    audio_chunks: list[bytes] = []

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

                    chunk = inline_data.data
                    if isinstance(chunk, str):
                        chunk = base64.b64decode(chunk)
                    audio_chunks.append(chunk)

            if getattr(server_content, "turn_complete", False):
                break

    if not audio_chunks:
        raise RuntimeError(f"No audio returned for voice '{voice_name}'.")

    return b"".join(audio_chunks)


async def run(text: str, output_dir: pathlib.Path, voices: Iterable[str]) -> int:
    try:
        from google import genai
    except ImportError:
        print("Error: missing dependency 'google-genai'. Install: pip3 install --user google-genai")
        return 1

    api_key = get_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found.")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=api_key)
    voices = list(voices)

    failures: list[tuple[str, str]] = []
    generated = 0

    for idx, voice_name in enumerate(voices, start=1):
        print(f"[{idx}/{len(voices)}] Generating voice: {voice_name}")
        try:
            pcm = await generate_voice_demo(client=client, text=text, voice_name=voice_name)
            out_path = output_dir / f"{idx:02d}_{voice_name.lower()}.wav"
            write_wav_file(out_path, pcm)
            generated += 1
            print(f"  Saved: {out_path}")
        except Exception as exc:
            failures.append((voice_name, str(exc)))
            print(f"  Failed: {voice_name} -> {exc}")

    print("\nDone.")
    print(f"Model: {MODEL_NAME}")
    print(f"Generated: {generated}")
    print(f"Failed: {len(failures)}")
    print(f"Output dir: {output_dir}")

    if failures:
        print("\nFailures:")
        for voice_name, message in failures:
            print(f"- {voice_name}: {message}")

    return 0 if not failures else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate demo TTS files for all Gemini 3.1 Flash Live voices"
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help="Text to synthesize for every voice",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/gemini_3_1_flash_live_tts_demos",
        help="Directory where WAV files will be written",
    )
    parser.add_argument(
        "--voices",
        nargs="*",
        default=None,
        help="Optional custom subset of voices (default: all known voices)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    voices = args.voices if args.voices else VOICE_NAMES
    output_dir = pathlib.Path(args.output_dir)
    rc = asyncio.run(run(text=args.text, output_dir=output_dir, voices=voices))
    sys.exit(rc)


if __name__ == "__main__":
    main()

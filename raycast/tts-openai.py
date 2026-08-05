#!/Users/marshtupa/.venvs/raycast/bin/python3

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Speak with OpenAI
# @raycast.mode compact
# @raycast.packageName Audio
# @raycast.description Speak text using OpenAI gpt-4o-mini-tts (streaming)

# Optional parameters:
# @raycast.icon 🔊
# @raycast.argument1 { "type": "text", "placeholder": "Text to read", "optional": true }

import hashlib
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from logging.handlers import RotatingFileHandler
from typing import Optional

# --- Configuration ---
MODEL_NAME = "gpt-4o-mini-tts"
VOICE_NAME = "marin"
API_URL = "https://api.openai.com/v1/audio/speech"
REQUEST_TIMEOUT_SECONDS = 60
STREAM_READ_CHUNK_BYTES = 4096
PLAYER_SWIFT_FILENAME = "tts-player.swift"
PLAYER_BINARY_CACHE_DIRNAME = "raycast_tts_openai_player"
LOG_PATH_ENV_VAR = "RAYCAST_TTS_LOG_PATH"
LOG_LEVEL_ENV_VAR = "RAYCAST_TTS_LOG_LEVEL"
DEFAULT_LOG_FILENAME = "raycast_tts_openai.log"
LOG_MAX_BYTES = 2_000_000
LOG_BACKUP_COUNT = 3
RUN_ID = uuid.uuid4().hex[:8]
# ---------------------

LOGGER = logging.getLogger("raycast_tts_openai")


def elapsed_ms(start_time: float) -> int:
    return int((time.perf_counter() - start_time) * 1000)


def setup_logging() -> str:
    log_path = os.environ.get(
        LOG_PATH_ENV_VAR,
        os.path.join(tempfile.gettempdir(), DEFAULT_LOG_FILENAME),
    )
    log_level_name = os.environ.get(LOG_LEVEL_ENV_VAR, "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    LOGGER.handlers.clear()
    LOGGER.setLevel(log_level)
    LOGGER.propagate = False

    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            f"%(asctime)s.%(msecs)03d %(levelname)s run={RUN_ID} %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    LOGGER.addHandler(file_handler)

    LOGGER.info(
        "logging initialized path=%s level=%s pid=%s argv=%s",
        log_path,
        logging.getLevelName(LOGGER.level),
        os.getpid(),
        sys.argv[1:],
    )
    return log_path


def get_api_key() -> str:
    started = time.perf_counter()
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        LOGGER.info("api key source=env elapsed_ms=%d", elapsed_ms(started))
        return api_key

    try:
        LOGGER.info("api key source=interactive_shell lookup started")
        lookup_started = time.perf_counter()
        res = subprocess.run(
            ["zsh", "-i", "-c", "printenv OPENAI_API_KEY"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        lines = [line.strip() for line in res.stdout.split("\n") if line.strip()]
        if lines:
            LOGGER.info(
                "api key source=interactive_shell elapsed_ms=%d shell_elapsed_ms=%d returncode=%s",
                elapsed_ms(started),
                elapsed_ms(lookup_started),
                res.returncode,
            )
            return lines[-1]
        LOGGER.warning(
            "api key lookup via interactive shell returned empty value returncode=%s elapsed_ms=%d",
            res.returncode,
            elapsed_ms(lookup_started),
        )
    except Exception:
        LOGGER.exception("api key lookup via interactive shell failed elapsed_ms=%d", elapsed_ms(started))

    LOGGER.error("api key not found total_elapsed_ms=%d", elapsed_ms(started))
    return ""


def get_input_text() -> str:
    started = time.perf_counter()
    if len(sys.argv) > 1 and sys.argv[1].strip():
        text = sys.argv[1].strip()
        LOGGER.info(
            "input text source=argv chars=%d elapsed_ms=%d",
            len(text),
            elapsed_ms(started),
        )
        return text

    try:
        paste_started = time.perf_counter()
        text = subprocess.check_output(["pbpaste"], text=True).strip()
        LOGGER.info(
            "input text source=clipboard chars=%d elapsed_ms=%d pbpaste_elapsed_ms=%d",
            len(text),
            elapsed_ms(started),
            elapsed_ms(paste_started),
        )
        return text
    except Exception:
        LOGGER.exception("input text source=clipboard failed elapsed_ms=%d", elapsed_ms(started))
        return ""


def _start_player_process(cmd: list[str]) -> subprocess.Popen:
    started = time.perf_counter()
    LOGGER.info("starting player process cmd=%s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    LOGGER.info("player process started pid=%s elapsed_ms=%d", proc.pid, elapsed_ms(started))
    return proc


def _get_cached_player_binary(swift_path: str) -> Optional[str]:
    started = time.perf_counter()
    try:
        with open(swift_path, "rb") as source_file:
            source_digest = hashlib.sha256(source_file.read()).hexdigest()[:16]
    except Exception:
        LOGGER.exception("failed to read swift source for cache key path=%s", swift_path)
        return None

    try:
        swiftc_version = subprocess.check_output(
            ["swiftc", "-version"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        LOGGER.exception("failed to get swiftc version for cache key")
        return None

    version_digest = hashlib.sha256(swiftc_version.encode("utf-8")).hexdigest()[:10]
    arch = platform.machine() or "unknown"
    cache_dir = os.path.join(tempfile.gettempdir(), PLAYER_BINARY_CACHE_DIRNAME)
    binary_path = os.path.join(
        cache_dir,
        f"tts-openai-player-{source_digest}-{arch}-{version_digest}",
    )
    tmp_binary_path = f"{binary_path}.tmp.{os.getpid()}"

    if os.path.isfile(binary_path) and os.access(binary_path, os.X_OK):
        LOGGER.info("player binary cache hit path=%s elapsed_ms=%d", binary_path, elapsed_ms(started))
        return binary_path

    LOGGER.info("player binary cache miss path=%s", binary_path)

    try:
        os.makedirs(cache_dir, exist_ok=True)
        compile_started = time.perf_counter()
        build_result = subprocess.run(
            ["swiftc", "-O", swift_path, "-o", tmp_binary_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if build_result.returncode != 0 or not os.path.isfile(tmp_binary_path):
            LOGGER.warning(
                "player binary build failed returncode=%s compile_elapsed_ms=%d",
                build_result.returncode,
                elapsed_ms(compile_started),
            )
            return None
        os.replace(tmp_binary_path, binary_path)
        LOGGER.info(
            "player binary built path=%s compile_elapsed_ms=%d total_elapsed_ms=%d",
            binary_path,
            elapsed_ms(compile_started),
            elapsed_ms(started),
        )
        return binary_path
    except Exception:
        LOGGER.exception("player binary build raised exception")
        return None
    finally:
        if os.path.exists(tmp_binary_path):
            try:
                os.remove(tmp_binary_path)
            except Exception:
                LOGGER.exception("failed to cleanup temporary binary path=%s", tmp_binary_path)


def start_streaming_player() -> subprocess.Popen:
    started = time.perf_counter()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    swift_path = os.path.join(script_dir, PLAYER_SWIFT_FILENAME)
    LOGGER.info("starting streaming player swift_path=%s", swift_path)

    if not os.path.isfile(swift_path):
        LOGGER.error("swift player file not found path=%s", swift_path)
        raise RuntimeError(f"Swift player file not found: {swift_path}")

    fallback_cmd = ["swift", swift_path]
    cached_binary_path = _get_cached_player_binary(swift_path)
    primary_cmd = [cached_binary_path] if cached_binary_path else fallback_cmd

    try:
        proc = _start_player_process(primary_cmd)
        LOGGER.info(
            "streaming player started mode=%s elapsed_ms=%d",
            "binary" if cached_binary_path else "swift_script",
            elapsed_ms(started),
        )
        return proc
    except Exception:
        LOGGER.exception("failed to start primary player cmd=%s", " ".join(primary_cmd))
        if primary_cmd == fallback_cmd:
            raise RuntimeError("Failed to start Swift player script.")
        try:
            proc = _start_player_process(fallback_cmd)
            LOGGER.warning("primary binary start failed, fallback swift script started elapsed_ms=%d", elapsed_ms(started))
            return proc
        except Exception:
            LOGGER.exception("fallback swift script start failed")
            raise RuntimeError("Failed to start Swift player binary and fallback Swift script.")


def _extract_openai_error_message(raw_body: bytes) -> str:
    if not raw_body:
        return ""

    decoded = raw_body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError:
        return decoded.strip()[:500]

    if isinstance(parsed, dict):
        err = parsed.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

    return decoded.strip()[:500]


def stream_with_audio_api(api_key: str, input_text: str, player_proc: subprocess.Popen) -> None:
    started = time.perf_counter()
    LOGGER.info(
        "audio api stream start model=%s voice=%s input_chars=%d timeout_seconds=%s",
        MODEL_NAME,
        VOICE_NAME,
        len(input_text),
        REQUEST_TIMEOUT_SECONDS,
    )

    payload = {
        "model": MODEL_NAME,
        "voice": VOICE_NAME,
        "input": input_text,
        "instructions": "Read the text naturally and exactly as written without adding extra words.",
        "response_format": "pcm",
        "stream_format": "audio",
    }

    request_data = json.dumps(payload).encode("utf-8")
    request_obj = urllib.request.Request(
        API_URL,
        data=request_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    got_audio = False
    audio_chunks = 0
    total_audio_bytes = 0
    first_audio_latency_ms: Optional[int] = None

    try:
        open_started = time.perf_counter()
        with urllib.request.urlopen(request_obj, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            LOGGER.info(
                "audio api connected status=%s content_type=%s connect_elapsed_ms=%d",
                getattr(response, "status", "unknown"),
                response.headers.get("Content-Type"),
                elapsed_ms(open_started),
            )

            while True:
                try:
                    chunk = response.read(STREAM_READ_CHUNK_BYTES)
                except TimeoutError as exc:
                    LOGGER.warning(
                        "stream read timeout chunks=%d bytes=%d elapsed_ms=%d",
                        audio_chunks,
                        total_audio_bytes,
                        elapsed_ms(started),
                    )
                    raise RuntimeError("Timed out while receiving streamed audio from OpenAI.") from exc

                if not chunk:
                    break

                if player_proc.stdin is None:
                    LOGGER.error("player stdin unavailable during stream")
                    raise RuntimeError("Audio player stdin is not available.")

                try:
                    player_proc.stdin.write(chunk)
                    player_proc.stdin.flush()
                except BrokenPipeError as exc:
                    LOGGER.exception("broken pipe while writing audio to player")
                    raise RuntimeError("Audio player process closed its stdin unexpectedly.") from exc

                chunk_size = len(chunk)
                got_audio = True
                audio_chunks += 1
                total_audio_bytes += chunk_size
                if first_audio_latency_ms is None:
                    first_audio_latency_ms = elapsed_ms(started)
                    LOGGER.info("first audio chunk received size=%d latency_ms=%d", chunk_size, first_audio_latency_ms)
                if audio_chunks % 25 == 0:
                    LOGGER.info(
                        "audio progress chunks=%d bytes=%d elapsed_ms=%d",
                        audio_chunks,
                        total_audio_bytes,
                        elapsed_ms(started),
                    )
    except urllib.error.HTTPError as exc:
        error_body = exc.read()
        message = _extract_openai_error_message(error_body)
        LOGGER.error(
            "openai http error status=%s reason=%s body=%s",
            exc.code,
            exc.reason,
            message,
        )
        suffix = f": {message}" if message else ""
        raise RuntimeError(f"OpenAI API request failed with HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        LOGGER.exception("openai url error reason=%s", exc.reason)
        raise RuntimeError(f"Failed to reach OpenAI API: {exc.reason}") from exc
    except socket.timeout as exc:
        LOGGER.exception("socket timeout while streaming audio")
        raise RuntimeError("Timed out while receiving streamed audio from OpenAI.") from exc

    if not got_audio:
        LOGGER.error("no audio returned by audio api elapsed_ms=%d", elapsed_ms(started))
        raise RuntimeError("No audio returned from OpenAI audio API.")

    LOGGER.info(
        "audio api stream done chunks=%d bytes=%d first_audio_latency_ms=%s total_elapsed_ms=%d",
        audio_chunks,
        total_audio_bytes,
        first_audio_latency_ms,
        elapsed_ms(started),
    )


def main() -> None:
    log_path = setup_logging()
    started = time.perf_counter()
    LOGGER.info("script start")

    api_key = get_api_key()
    if not api_key:
        print(f"Error: OPENAI_API_KEY not found. Log: {log_path}")
        sys.exit(1)

    input_text = get_input_text()
    if not input_text:
        print(f"No text provided or selected. Log: {log_path}")
        sys.exit(1)

    player_proc: Optional[subprocess.Popen] = None
    try:
        player_proc = start_streaming_player()
        stream_with_audio_api(api_key=api_key, input_text=input_text, player_proc=player_proc)
        if player_proc.stdin is not None:
            player_proc.stdin.close()
            LOGGER.info("player stdin closed")
        LOGGER.info("script completed successfully total_elapsed_ms=%d", elapsed_ms(started))
    except Exception as exc:
        LOGGER.exception("script failed total_elapsed_ms=%d", elapsed_ms(started))
        if player_proc and player_proc.stdin is not None:
            try:
                player_proc.stdin.close()
                LOGGER.info("player stdin closed during error handling")
            except Exception:
                LOGGER.exception("failed closing player stdin during error handling")
        print(f"Error: {exc}. Log: {log_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()

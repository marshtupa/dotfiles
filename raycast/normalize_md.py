#!/usr/bin/env python3
import argparse
import os
import pathlib
import sys
import json
import urllib.request
import ssl
from typing import Optional
from pathlib import Path
import subprocess
import shlex


SYSTEM_PROMPT_PATH = "~/dotfiles/raycast/normalize_system_prompt.txt"

def read_text_file(path_like) -> str:
    # раскрыть переменные окружения ($HOME и т.п.) и тильду (~)
    p = Path(os.path.expandvars(str(path_like))).expanduser()

    # (опционально) превратить в абсолютный путь; strict=True даст раннюю ошибку, если файла нет
    p = p.resolve()

    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    return p.read_text(encoding="utf-8").strip()

def load_env_from_local_shell(keys: list[str]) -> None:
    """Load env vars from ~/.zshrc.d/.local-shell for GUI contexts (e.g., Raycast).
    Only fills variables that are currently unset in os.environ.
    """
    try:
        path = os.path.expanduser("~/.zshrc.d/.local-shell")
        if not os.path.exists(path):
            return
        cmd = [
            "zsh",
            "-c",
            f"source {shlex.quote(path)} 2>/dev/null; env -0",
        ]
        out = subprocess.check_output(cmd)
        for entry in out.split(b"\0"):
            if not entry:
                continue
            name_b, _, value_b = entry.partition(b"=")
            if not _:
                continue
            name = name_b.decode("utf-8", "ignore")
            if name in keys and os.getenv(name) is None:
                os.environ[name] = value_b.decode("utf-8", "ignore")
    except Exception:
        # Best-effort; silently continue if sourcing fails
        return

def _ssl_context_from_env() -> ssl.SSLContext:
    """Build SSL context with best-effort CA resolution.
    Priority:
      1) OPENROUTER_CA_BUNDLE / SSL_CERT_FILE / REQUESTS_CA_BUNDLE
      2) certifi bundle if available
      3) system default context
    """
    cafile = (
        os.getenv("OPENROUTER_CA_BUNDLE")
        or os.getenv("SSL_CERT_FILE")
        or os.getenv("REQUESTS_CA_BUNDLE")
    )
    if cafile and os.path.exists(cafile):
        return ssl.create_default_context(cafile=cafile)
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def call_openrouter(content: str, model: str, system_prompt: str) -> str:
    api_key = os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPEN_ROUTER_API_KEY is not set")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "temperature": 0.0,
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    ctx = _ssl_context_from_env()
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        details = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        raise RuntimeError(f"OpenRouter HTTP error {e.code}: {details}")
    except ssl.SSLError as e:
        raise RuntimeError(
            "SSL error: certificate verify failed. "
            "Try setting OPENROUTER_CA_BUNDLE/SSL_CERT_FILE/REQUESTS_CA_BUNDLE to your CA file, "
            "or install/update certifi. On macOS (python.org build), run 'Install Certificates.command'. "
            f"Details: {e}"
        )
    except Exception as e:
        raise RuntimeError(f"OpenRouter request failed: {e}")

    try:
        return payload["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"Unexpected OpenRouter response: {json.dumps(payload)[:1000]}")


def main():
    # Ensure Raycast/GUI runs can see env from user's shell file
    load_env_from_local_shell([
        "OPEN_ROUTER_API_KEY"
    ])
    parser = argparse.ArgumentParser(
        description="Normalize a Markdown file using OpenRouter (ChatGPT-5) and write .normalized.md next to it."
    )
    parser.add_argument("md_path", help="Path to the source .md file")
    parser.add_argument(
        "--model",
        help="OpenRouter model id",
        default=os.getenv("OPENROUTER_MODEL", "openai/gpt-5"),
    )
    args = parser.parse_args()

    src = pathlib.Path(args.md_path)
    if not src.exists():
        print(f"ERROR: file not found: {src}", file=sys.stderr)
        sys.exit(1)

    try:
        original = src.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: cannot read {src}: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve system prompt file path
    sys_prompt_path = pathlib.Path(SYSTEM_PROMPT_PATH)
    system_prompt = read_text_file(sys_prompt_path)

    try:
        normalized = call_openrouter(original, args.model, system_prompt)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Build output: <stem>.normalized.md (preserve multi-part stems like archive.tar)
    stem = src.with_suffix("").name
    out = src.with_name(f"{stem}.normalized.md")
    try:
        out.write_text(normalized, encoding="utf-8")
    except Exception as e:
        print(f"ERROR: cannot write {out}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Normalized: {out}")


if __name__ == "__main__":
    main()

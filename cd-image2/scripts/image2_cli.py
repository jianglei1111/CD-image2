#!/usr/bin/env python3
"""
CD-image2 client.

This intentionally uses httpx to match the known-working legacy image2 script.
Some upstream channels reject urllib-style requests even when the payload is the
same, so do not replace this with urllib unless the channel has been retested.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - exercised only on fresh envs
    httpx = None


BASE_URL = "https://sp.chedankj.com/v1"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_TIMEOUT = 600
RETRY_STATUSES = {502, 504, 522, 524}


class Image2Error(Exception):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CD-image2 generation/edit client")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("prompt", help="Image prompt or edit instruction")
        subparser.add_argument("--api-key", default=None, help="API key; prefer IMAGE2_API_KEY env var")
        subparser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name, default: {DEFAULT_MODEL}")
        subparser.add_argument("--size", default=DEFAULT_SIZE, help=f"Output size, default: {DEFAULT_SIZE}")
        subparser.add_argument(
            "--quality",
            default=DEFAULT_QUALITY,
            choices=["low", "medium", "high", "auto"],
            help=f"Image quality, default: {DEFAULT_QUALITY}",
        )
        subparser.add_argument("--count", "-n", type=int, default=1, help="Number of images, default: 1")
        subparser.add_argument("--output", default=None, help="Output PNG path; for count > 1 suffixes are added")
        subparser.add_argument("--output-dir", default=".", help="Output directory when --output is omitted")
        subparser.add_argument("--slug", default=None, help="Short filename slug when --output is omitted")
        subparser.add_argument(
            "--response-format",
            default="auto",
            choices=["auto", "b64_json", "url"],
            help="Requested upstream response format; auto omits the field and accepts either b64_json or url",
        )
        subparser.add_argument("--retries", type=int, default=3, help="Retries for gateway timeout errors")
        subparser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Request timeout seconds, default: {DEFAULT_TIMEOUT}")

    generate = subparsers.add_parser("generate", help="Generate image from text")
    add_common(generate)

    edit = subparsers.add_parser("edit", help="Edit an existing image")
    add_common(edit)
    edit.add_argument("--input", required=True, help="Input image path")

    return parser.parse_args()


def require_httpx() -> None:
    if httpx is not None:
        return
    raise Image2Error(
        "Missing dependency: httpx. Install it with: python -m pip install httpx"
    )


def get_api_key(args: argparse.Namespace) -> str:
    key = args.api_key or os.environ.get("IMAGE2_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise Image2Error(
            "Missing API key. Ask the user to create a key at https://www.chedankj.com with group image."
        )
    return key


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:60] or "image2-output"


def output_paths(args: argparse.Namespace) -> list[Path]:
    count = max(1, args.count)
    if args.output:
        base = Path(args.output)
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = slugify(args.slug or args.prompt)
        base = Path(args.output_dir) / f"{slug}-{stamp}.png"

    base = base.resolve()
    base.parent.mkdir(parents=True, exist_ok=True)
    if count == 1:
        return [base]

    suffix = base.suffix or ".png"
    return [base.with_name(f"{base.stem}-{index}{suffix}") for index in range(1, count + 1)]


def parse_error_body(raw: str) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500]
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code") or error.get("type")
        if message:
            return str(message)
    if isinstance(error, str):
        return error
    return raw[:500]


def extract_image_output(data: dict) -> tuple[str, str]:
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise Image2Error("Response does not contain image data")
    first = items[0]
    if not isinstance(first, dict):
        raise Image2Error("Unexpected image data format")
    b64_data = first.get("b64_json")
    if isinstance(b64_data, str) and b64_data:
        return ("b64_json", b64_data)
    image_url = first.get("url")
    if isinstance(image_url, str) and image_url:
        return ("url", image_url)
    raise Image2Error("Response image data contains neither b64_json nor url")


def save_b64_png(path: Path, b64_data: str) -> None:
    try:
        path.write_bytes(base64.b64decode(b64_data))
    except Exception as exc:
        raise Image2Error(f"Failed to save image to {path}: {exc}") from exc


def save_url_image(path: Path, image_url: str, timeout: int, retries: int) -> None:
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.get(image_url, follow_redirects=True, timeout=timeout)
        except httpx.RequestError as exc:
            raise Image2Error(f"Image URL download network error: {exc}") from exc

        if response.status_code == 200:
            if not response.content:
                raise Image2Error(f"Image URL returned an empty body: {image_url}")
            try:
                path.write_bytes(response.content)
            except Exception as exc:
                raise Image2Error(f"Failed to save downloaded image to {path}: {exc}") from exc
            return

        if response.status_code in RETRY_STATUSES and attempt < attempts:
            print(f"[image2] image download HTTP {response.status_code}; retrying {attempt}/{attempts}...", flush=True)
            continue

        message = response.reason_phrase or response.text[:200]
        raise Image2Error(f"Image URL download HTTP {response.status_code}: {message}", status=response.status_code, body=response.text)


def save_image_output(path: Path, image_output: tuple[str, str], timeout: int, retries: int) -> str:
    output_type, value = image_output
    if output_type == "b64_json":
        save_b64_png(path, value)
        return output_type
    if output_type == "url":
        save_url_image(path, value, timeout=timeout, retries=retries)
        return output_type
    raise Image2Error(f"Unsupported image output type: {output_type}")


def request_with_retries(callable_request, retries: int) -> dict:
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            response = callable_request()
        except httpx.RequestError as exc:
            raise Image2Error(f"Network error: {exc}") from exc

        if response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise Image2Error(f"Invalid JSON response: {exc}", body=response.text[:800]) from exc

        if response.status_code in RETRY_STATUSES and attempt < attempts:
            print(f"[image2] HTTP {response.status_code}; retrying {attempt}/{attempts}...", flush=True)
            continue

        message = parse_error_body(response.text) or response.reason_phrase
        raise Image2Error(
            f"HTTP {response.status_code}: {message}",
            status=response.status_code,
            body=response.text,
        )

    raise Image2Error("Request failed after retries")


def generate_once(args: argparse.Namespace, api_key: str) -> tuple[str, str]:
    url = f"{BASE_URL.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "quality": args.quality,
        "n": 1,
    }
    if args.response_format != "auto":
        payload["response_format"] = args.response_format

    def do_request():
        return httpx.post(url, headers=headers, json=payload, timeout=args.timeout)

    return extract_image_output(request_with_retries(do_request, args.retries))


def edit_once(args: argparse.Namespace, api_key: str) -> tuple[str, str]:
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise Image2Error(f"Input image does not exist: {input_path}")
    if not input_path.is_file():
        raise Image2Error(f"Input path is not a file: {input_path}")

    url = f"{BASE_URL.rstrip('/')}/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}

    def do_request():
        with input_path.open("rb") as img_file:
            files = {
                "image": (input_path.name, img_file, "image/png"),
            }
            data = {
                "model": args.model,
                "prompt": args.prompt,
                "size": args.size,
                "quality": args.quality,
            }
            if args.response_format != "auto":
                data["response_format"] = args.response_format
            return httpx.post(url, headers=headers, files=files, data=data, timeout=args.timeout)

    return extract_image_output(request_with_retries(do_request, args.retries))


def main() -> int:
    args = parse_args()
    try:
        require_httpx()
        api_key = get_api_key(args)
        paths = output_paths(args)
        print("[image2] Starting request. Generation can take a few minutes.", flush=True)
        print(f"[image2] mode={args.command} model={args.model} size={args.size} quality={args.quality}", flush=True)
        print(f"[image2] base_url={BASE_URL}", flush=True)

        source_types = []
        for index, path in enumerate(paths, start=1):
            if args.command == "generate":
                image_output = generate_once(args, api_key)
            else:
                image_output = edit_once(args, api_key)
            source_type = save_image_output(path, image_output, timeout=args.timeout, retries=args.retries)
            source_types.append(source_type)
            print(f"[image2] saved {index}/{len(paths)} from {source_type}: {path}", flush=True)

        print("[image2] OK", flush=True)
        print(json.dumps({"ok": True, "paths": [str(path) for path in paths], "source_types": source_types}, ensure_ascii=False), flush=True)
        return 0
    except Image2Error as exc:
        if exc.status:
            print(f"[image2] ERROR HTTP {exc.status}: {exc}", file=sys.stderr, flush=True)
        else:
            print(f"[image2] ERROR: {exc}", file=sys.stderr, flush=True)
        if exc.body:
            print(exc.body[:800], file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

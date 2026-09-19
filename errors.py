"""
errors.py — Shared helper for user-facing error messages.

Raw exception text (stack traces, provider JSON payloads, low-level
socket errors) is developer-facing and reads as scary/broken to a normal
user. This module gives every part of the CLI one place to turn an
exception into a short, calm message, while still preserving the full
technical detail behind an opt-in debug flag (KLYRO_DEBUG=1) for anyone
who actually needs to diagnose it.
"""

import os

DEBUG = os.getenv("KLYRO_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def friendly(context: str, e: Exception) -> str:
    """
    Build a clear, helpful error message for the user.
    Surfaces actionable root causes (invalid API key, quota, timeout) directly,
    while keeping low-level stack traces behind KLYRO_DEBUG=1.
    """
    if DEBUG:
        return f"{context}: {e}"

    raw = str(e)
    raw_lower = raw.lower()

    if "api key not valid" in raw_lower or "api_key_invalid" in raw_lower or ("invalid_argument" in raw_lower and "key" in raw_lower):
        return "API key tidak valid. Silakan ketik /provider untuk memasukkan API key yang benar."
    if "quota" in raw_lower or "rate limit" in raw_lower or "429" in raw_lower or "resource_exhausted" in raw_lower:
        return "Kuota harian atau rate limit API tercapai (HTTP 429). Coba beralih provider atau tunggu sejenak."
    if "connection refused" in raw_lower or "failed to establish a new connection" in raw_lower:
        return "Tidak dapat terhubung ke host. Pastikan koneksi internet atau server lokal aktif."
    if "timed out" in raw_lower or "timeout" in raw_lower:
        return "Koneksi ke server timeout setelah menunggu terlalu lama."
    if "404" in raw_lower or "not found" in raw_lower:
        return "Model atau resource tidak ditemukan di provider (404)."

    if raw.startswith("[") and "]" in raw:
        return raw

    return f"{context}. Run with KLYRO_DEBUG=1 for technical details."

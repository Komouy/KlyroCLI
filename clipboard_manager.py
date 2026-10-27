"""
clipboard_manager.py — Cross-platform clipboard integration for Klyro CLI.
Supports Windows (clip.exe / PowerShell Set-Clipboard), macOS (pbcopy),
Linux (wl-copy, xclip, xsel), and Android Termux (termux-clipboard-set).
Falls back to pyperclip if installed. Zero external dependencies required.
"""

from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
from typing import Optional


# Regex to detect code fences and extract language/filename + body
_CODE_BLOCK_RE = re.compile(r'```([^\n]*)\n(.*?)```', re.DOTALL)
_ACTION_TAG_RE = re.compile(r'<!--\s*ACTION:[^>]*-->', re.IGNORECASE | re.DOTALL)


def extract_code_blocks(markdown_text: str) -> list[dict]:
    """
    Extract all fenced code blocks from markdown text.
    Returns:
        List of dicts: [{"lang": str, "info": str, "code": str, "lines": int}]
    """
    if not markdown_text:
        return []

    blocks = []
    for match in _CODE_BLOCK_RE.finditer(markdown_text):
        info_line = match.group(1).strip()
        code_body = match.group(2)
        lang = info_line.split(":")[0].strip() if info_line else ""
        blocks.append({
            "lang": lang or "code",
            "info": info_line,
            "code": code_body,
            "lines": len(code_body.splitlines()),
        })
    return blocks


def get_copy_target(response_text: str, mode: str = "auto") -> tuple[str, str]:
    """
    Determine what text to copy based on requested mode:
    - 'code': extract latest code block (or joined code blocks if multiple)
    - 'all': full response text (with ACTION tags stripped)
    - 'auto': code block if present, otherwise full response

    Returns:
        (content_to_copy: str, description: str)
    """
    if not response_text:
        return "", "Tidak ada respons AI yang tersimpan untuk disalin"

    cleaned_response = _ACTION_TAG_RE.sub("", response_text).strip()
    blocks = extract_code_blocks(response_text)

    mode = (mode or "auto").strip().lower()

    if mode == "code":
        if not blocks:
            return "", "Tidak ditemukan blok kode dalam respons terakhir"
        last_block = blocks[-1]
        desc = f"Blok kode {last_block['lang']} ({last_block['lines']} baris)"
        return last_block["code"], desc

    if mode == "all":
        line_count = len(cleaned_response.splitlines())
        desc = f"Seluruh respons AI ({line_count} baris)"
        return cleaned_response, desc

    # mode == "auto"
    if blocks:
        last_block = blocks[-1]
        desc = f"Blok kode {last_block['lang']} ({last_block['lines']} baris)"
        return last_block["code"], desc

    line_count = len(cleaned_response.splitlines())
    desc = f"Respons AI ({line_count} baris)"
    return cleaned_response, desc


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    """
    Copy text string to OS system clipboard.
    Returns:
        (success: bool, status_message: str)
    """
    if not text:
        return False, "Teks kosong, tidak ada yang disalin"

    # 1. Try pyperclip if installed
    try:
        import pyperclip
        pyperclip.copy(text)
        return True, "Clipboard updated (pyperclip)"
    except Exception:
        pass

    # 2. Windows: built-in clip.exe or PowerShell
    if sys.platform == "win32":
        # First attempt: clip.exe
        try:
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
            p.communicate(input=text.encode("utf-8", errors="replace"))
            if p.returncode == 0:
                return True, "Berhasil disalin ke clipboard Windows (clip)"
        except Exception:
            pass

        # Second attempt: PowerShell Set-Clipboard
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                input=text,
                text=True,
                capture_output=True,
                timeout=5,
            )
            if res.returncode == 0:
                return True, "Berhasil disalin ke clipboard Windows (PowerShell)"
        except Exception as e:
            return False, f"Gagal menyalin ke clipboard Windows: {e}"

    # 3. macOS: pbcopy
    if sys.platform == "darwin":
        if shutil.which("pbcopy"):
            try:
                p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                p.communicate(input=text.encode("utf-8", errors="replace"))
                if p.returncode == 0:
                    return True, "Berhasil disalin ke clipboard macOS"
            except Exception as e:
                return False, f"Gagal menyalin ke clipboard macOS: {e}"

    # 4. Android Termux
    if shutil.which("termux-clipboard-set"):
        try:
            p = subprocess.Popen(["termux-clipboard-set"], stdin=subprocess.PIPE)
            p.communicate(input=text.encode("utf-8", errors="replace"))
            if p.returncode == 0:
                return True, "Berhasil disalin ke clipboard Termux"
        except Exception:
            pass

    # 5. Linux: Wayland (wl-copy) or X11 (xclip / xsel)
    linux_candidates = [
        (["wl-copy"], "wl-copy"),
        (["xclip", "-selection", "clipboard"], "xclip"),
        (["xsel", "--clipboard", "--input"], "xsel"),
    ]
    for cmd_args, prog in linux_candidates:
        if shutil.which(cmd_args[0]):
            try:
                p = subprocess.Popen(cmd_args, stdin=subprocess.PIPE)
                p.communicate(input=text.encode("utf-8", errors="replace"))
                if p.returncode == 0:
                    return True, f"Berhasil disalin ke clipboard ({prog})"
            except Exception:
                continue

    return False, "Tidak ada utilitas clipboard yang tersedia (install xclip, wl-clipboard, atau pyperclip)"


def copy_last_ai_response(folder_path: str = None, mode: str = "auto") -> tuple[bool, str, str]:
    """
    Fetch the last AI response (from memory or history.json) and copy it to clipboard.
    Returns:
        (success: bool, target_desc: str, detail_msg: str)
    """
    import session_manager

    last_resp = session_manager.get_last_response()
    if not last_resp and folder_path:
        # Fallback to last history item in workspace
        recent = session_manager.load_history(folder_path, limit=1)
        if recent:
            last_resp = recent[-1].get("response_summary", "")

    if not last_resp:
        return False, "", "Belum ada respons AI pada sesi ini. Ajukan pertanyaan terlebih dahulu."

    text_to_copy, target_desc = get_copy_target(last_resp, mode=mode)
    if not text_to_copy:
        return False, "", target_desc

    ok, msg = copy_to_clipboard(text_to_copy)
    return ok, target_desc, msg

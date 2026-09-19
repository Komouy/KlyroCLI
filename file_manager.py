import os
import re
from config import MAKS_UKURAN_FILE, MAKS_TOTAL_KONTEKS, EKSTENSI_DIIZINKAN, FOLDER_DIABAIKAN
from theme import ICON_DIR, ICON_FILE, yellow, white, dim
from errors import friendly

def scan_struktur(folder_path, prefix=""):
    """
    Menghasilkan tampilan visual struktur direktori (tree view) berbasis icon teks.
    """
    if not os.path.exists(folder_path):
        return f"[ERROR] Folder '{folder_path}' not found."

    output = []
    try:
        items = sorted(os.listdir(folder_path))
    except Exception as e:
        return f"[ERROR] {friendly('Could not access the folder', e)}"

    # Filter item yang tidak diabaikan
    items = [item for item in items if item not in FOLDER_DIABAIKAN]

    for index, item in enumerate(items):
        item_path = os.path.join(folder_path, item)
        is_last = (index == len(items) - 1)
        connector = "+-- " if is_last else "|-- "
        
        if os.path.isdir(item_path):
            output.append(f"{prefix}{connector}{ICON_DIR} {yellow(item + '/')}")
            extension = "    " if is_last else "|   "
            sub_tree = scan_struktur(item_path, prefix + extension)
            if sub_tree:
                output.append(sub_tree)
        else:
            _, ext = os.path.splitext(item)
            allowed = ext.lower() in EKSTENSI_DIIZINKAN
            indicator = ICON_FILE if allowed else dim("[SKIP]")
            nama_file = white(item) if allowed else dim(item)
            output.append(f"{prefix}{connector}{indicator} {nama_file}")

    return "\n".join(output)


def list_daftar_file(folder_path):
    """
    Mengembalikan daftar semua path file (relative) yang ada dalam folder.
    """
    file_list = []
    if not os.path.exists(folder_path):
        return file_list

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in FOLDER_DIABAIKAN]
        for file in sorted(files):
            if len(file_list) >= 250:
                break
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, folder_path).replace("\\", "/")
            file_list.append(rel_path)
        if len(file_list) >= 250:
            break
    return sorted(file_list)


def baca_semua_file(folder_path):
    """
    Membaca semua file kode yang diizinkan dan menggabungkannya menjadi teks konteks.
    Returns:
        konteks (str): Teks gabungan semua isi file
        file_dibaca (list): Daftar file yang berhasil dibaca
        file_dilewati (list): Daftar tuple (file, alasan)
    """
    if not os.path.exists(folder_path):
        return "", [], [(folder_path, "Folder not found")]

    file_dibaca = []
    file_dilewati = []
    isi_konteks = []
    total_karakter = 0

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in FOLDER_DIABAIKAN]

        for file in sorted(files):
            if len(file_dibaca) >= 200 or total_karakter >= MAKS_TOTAL_KONTEKS:
                break

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, folder_path)
            _, ext = os.path.splitext(file)

            # Cek ekstensi
            if ext.lower() not in EKSTENSI_DIIZINKAN:
                continue

            # Cek ukuran file
            try:
                ukuran = os.path.getsize(file_path)
                if ukuran > MAKS_UKURAN_FILE:
                    continue

                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    konten = f.read()

                panjang_konten = len(konten)
                if total_karakter + panjang_konten > MAKS_TOTAL_KONTEKS:
                    break

                total_karakter += panjang_konten
                isi_konteks.append(f"--- FILE: {rel_path} ---\n{konten}\n")
                file_dibaca.append(rel_path)

            except Exception as e:
                file_dilewati.append((rel_path, friendly("Could not read the file", e)))

        if len(file_dibaca) >= 200 or total_karakter >= MAKS_TOTAL_KONTEKS:
            break

    konteks_gabungan = "\n".join(isi_konteks)
    return konteks_gabungan, file_dibaca, file_dilewati


def baca_satu_file(file_path):
    """
    Membaca isi satu file tertentu.
    """
    if not os.path.exists(file_path):
        return None, f"File '{file_path}' not found."
    
    import security
    if security.is_binary_or_media_file(file_path):
        return None, f"Could not read file: '{os.path.basename(file_path)}' is a binary or media file."

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), None
    except Exception as e:
        return None, friendly("Could not read the file", e)


_FILE_MENTION_RE = re.compile(r'(?:^|[\s(\[{"\'])@([A-Za-z0-9_\-./\\]+\.[A-Za-z0-9_]+)')


def resolve_file_mentions(text: str, folder_aktif: str) -> tuple[str, list[dict], list[str]]:
    """
    Detect @filename mentions in user prompt, read and pin their contents to the prompt context.
    Returns:
        enriched_prompt (str): Prompt augmented with pinned file contents.
        pinned_files (list[dict]): Metadata of resolved files [{"name": str, "size_kb": float, "chars": int}]
        missing_files (list[str]): Names of files mentioned that could not be resolved.
    """
    if not text or "@" not in text:
        return text, [], []

    raw_mentions = _FILE_MENTION_RE.findall(text)
    if not raw_mentions:
        return text, [], []

    all_project_files = list_daftar_file(folder_aktif)
    file_map_lower = {f.lower().replace("\\", "/"): f for f in all_project_files}
    basename_map_lower = {os.path.basename(f).lower(): f for f in all_project_files}

    pinned_files = []
    missing_files = []
    pinned_blocks = []
    seen_paths = set()

    for raw in raw_mentions:
        cleaned = raw.strip().rstrip(".,?!:;\"'")
        if not cleaned:
            continue

        norm_rel = cleaned.replace("\\", "/").lower()
        resolved_rel = None

        # 1. Exact match with project files
        if norm_rel in file_map_lower:
            resolved_rel = file_map_lower[norm_rel]
        # 2. Match by basename (e.g. @agent.py -> core/agent.py)
        elif norm_rel in basename_map_lower:
            resolved_rel = basename_map_lower[norm_rel]
        elif os.path.basename(norm_rel) in basename_map_lower:
            resolved_rel = basename_map_lower[os.path.basename(norm_rel)]
        else:
            # 3. Direct filesystem check
            direct_path = os.path.join(folder_aktif, cleaned)
            if os.path.isfile(direct_path) and is_safe_path(folder_aktif, direct_path):
                resolved_rel = os.path.relpath(direct_path, folder_aktif).replace("\\", "/")

        if not resolved_rel:
            if cleaned not in missing_files:
                missing_files.append(cleaned)
            continue

        if resolved_rel in seen_paths:
            continue
        seen_paths.add(resolved_rel)

        abs_path = os.path.join(folder_aktif, resolved_rel)
        if not is_safe_path(folder_aktif, abs_path):
            missing_files.append(cleaned)
            continue

        try:
            import validations
            allowed, block_reason = validations.validate_file_mention_candidate(resolved_rel, abs_path)
            if not allowed:
                missing_files.append(f"{cleaned} ({block_reason})")
                continue
        except Exception:
            pass

        content, err = baca_satu_file(abs_path)
        if err or content is None:
            missing_files.append(cleaned)
            continue

        # Cap individual pinned file to 64 KB to protect context limits
        MAX_PINNED_CHARS = 64_000
        was_cut = False
        if len(content) > MAX_PINNED_CHARS:
            content = content[:MAX_PINNED_CHARS]
            was_cut = True

        size_kb = round(os.path.getsize(abs_path) / 1024.0, 1)
        pinned_files.append({
            "name": resolved_rel,
            "size_kb": size_kb,
            "chars": len(content),
            "truncated": was_cut
        })

        _, ext = os.path.splitext(resolved_rel)
        lang = ext.lstrip(".") or "text"
        cut_note = f" (truncated to {MAX_PINNED_CHARS} chars)" if was_cut else ""
        pinned_blocks.append(
            f"--- EXPLICITLY PINNED FILE: {resolved_rel}{cut_note} ---\n```{lang}\n{content.strip()}\n```\n--- END PINNED FILE ---"
        )

    if not pinned_blocks:
        return text, [], missing_files

    header = (
        "[📌 PINNED CONTEXT: The user explicitly referenced the following workspace files with '@'. "
        "Prioritize these contents when responding to the user's instructions:]\n\n"
    )
    enriched_prompt = f"{header}" + "\n\n".join(pinned_blocks) + f"\n\n[USER INSTRUCTION]:\n{text}"
    return enriched_prompt, pinned_files, missing_files


_WINDOWS_ABS_PATH_RE = re.compile(r'^([a-zA-Z]:[\\/]|\\\\)')

_WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}

_PROTECTED_PATH_PATTERNS = [
    r"^\.git([\\/].*)?$",           # .git directory or files within
    r"^\.klyro([\\/].*)?$",          # .klyro directory or files within
    r"^klyro_config\.json$",         # Klyro config file
    r"^\.env(\.[a-zA-Z0-9_\-]+)?$",  # .env, .env.local, .env.production, etc.
]


def is_windows_reserved_name(path: str) -> bool:
    """Check if any path component or its stem matches Windows reserved device names."""
    if not path:
        return False
    parts = re.split(r"[\\/]", str(path))
    for part in parts:
        clean = part.strip().lower()
        if not clean:
            continue
        stem = clean.split(".")[0]
        if clean in _WINDOWS_RESERVED_NAMES or stem in _WINDOWS_RESERVED_NAMES:
            return True
    return False


def is_protected_workspace_path(rel_path: str) -> tuple[bool, str]:
    """
    Check if a path targets sensitive project infrastructure that should be protected
    from accidental AI deletion or destructive overwriting.
    Returns: (is_protected: bool, reason: str)
    """
    if not rel_path:
        return False, ""
    norm = str(rel_path).replace("\\", "/").strip().lstrip("/")
    for pat in _PROTECTED_PATH_PATTERNS:
        if re.match(pat, norm, re.IGNORECASE):
            return True, f"Akses ditolak: '{rel_path}' adalah file/direktori sistem terlindungi (.git / .env / .klyro / config)."
    return False, ""


def is_safe_path(base_folder, target_path, rel_path=None):
    """
    Memastikan path target berada di dalam base folder (mencegah path traversal)
    dan bukan merupakan Windows reserved device name.
    """
    if is_windows_reserved_name(rel_path or target_path):
        return False

    if rel_path is not None and _WINDOWS_ABS_PATH_RE.match(str(rel_path)):
        return False

    # Resolve links before comparing paths; an in-workspace symlink must not
    # provide an escape hatch to files outside the workspace.
    base_abs = os.path.realpath(os.path.abspath(base_folder))
    target_abs = os.path.realpath(os.path.abspath(target_path))
    try:
        common = os.path.commonpath([base_abs, target_abs])
    except ValueError:
        # Beda drive letter di Windows (atau kasus lain yang tak sebanding).
        return False
    return common == base_abs


def check_balanced_delimiters(code: str) -> tuple[bool, str]:
    """
    Check matching {}, [], () delimiters while ignoring characters inside
    strings and comments for C/JS-family languages.
    """
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    in_block_comment = False
    escape = False

    lines = code.splitlines()
    for line_idx, line in enumerate(lines, 1):
        i = 0
        n = len(line)
        in_line_comment = False
        while i < n:
            ch = line[i]
            next_ch = line[i + 1] if i + 1 < n else ''

            if in_block_comment:
                if ch == '*' and next_ch == '/':
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_line_comment:
                break

            if not in_single_quote and not in_double_quote and not in_backtick:
                if ch == '/' and next_ch == '/':
                    in_line_comment = True
                    break
                if ch == '/' and next_ch == '*':
                    in_block_comment = True
                    i += 2
                    continue

            if ch == '\\' and (in_single_quote or in_double_quote or in_backtick):
                escape = not escape
                i += 1
                continue

            if ch == "'" and not in_double_quote and not in_backtick and not escape:
                in_single_quote = not in_single_quote
                i += 1
                continue

            if ch == '"' and not in_single_quote and not in_backtick and not escape:
                in_double_quote = not in_double_quote
                i += 1
                continue

            if ch == '`' and not in_single_quote and not in_double_quote and not escape:
                in_backtick = not in_backtick
                i += 1
                continue

            escape = False

            if not in_single_quote and not in_double_quote and not in_backtick:
                if ch in "({[":
                    stack.append((ch, line_idx))
                elif ch in ")}]":
                    if not stack:
                        return False, f"Unmatched closing delimiter '{ch}' on line {line_idx}"
                    last_open, open_line = stack.pop()
                    if pairs[ch] != last_open:
                        return False, f"Mismatched delimiter: expected closing for '{last_open}' (from line {open_line}), found '{ch}' on line {line_idx}"

            i += 1

    if stack:
        unclosed, open_line = stack[-1]
        return False, f"Unclosed delimiter '{unclosed}' opened on line {open_line} (possible truncated output)"

    return True, "Delimiters balanced."


def validasi_sintaks(file_path, konten, old_content=None):
    """
    Validasi sintaks otomatis untuk file:
      - Python (.py) via ast.parse
      - JSON (.json) via json.loads
      - TOML (.toml) via tomllib.loads
      - Balanced delimiters (curly braces, brackets, parentheses) untuk JS, TS, Go, Rust, C, Java, etc.
      - Deteksi pemotongan ekstrem (truncation warning) jika file lama berisi banyak baris dan file baru kosong/terpotong.
    Returns:
        is_valid (bool), error_message (str)
    """
    # 1. Truncation alert
    if old_content:
        old_lines = len(old_content.strip().splitlines())
        new_lines = len(konten.strip().splitlines())
        if old_lines >= 15 and new_lines <= 2:
            return False, f"Destructive Truncation: file length dropped drastically from {old_lines} to {new_lines} lines. The AI output might have been cut off."

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # 2. Git merge conflict markers check
    DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt"}
    if ext not in DOC_EXTENSIONS:
        try:
            import validations
            has_conflict, c_line, c_marker = validations.check_git_conflict_markers(konten)
            if has_conflict:
                return False, f"Git conflict marker on line {c_line}: `{c_marker}` — unresolved conflict detected"
        except Exception:
            pass

    if ext == ".py":
        import ast
        try:
            ast.parse(konten)
            return True, "Valid Python syntax."
        except SyntaxError as e:
            line_info = f"line {e.lineno}" if e.lineno else "unknown line"
            snippet = f": `{e.text.strip()}`" if getattr(e, "text", None) and e.text.strip() else ""
            return False, f"SyntaxError on {line_info}: {e.msg}{snippet}"
    elif ext == ".json":
        import json
        try:
            json.loads(konten)
            return True, "Valid JSON format."
        except Exception as e:
            return False, f"JSON Error: {e}"
    elif ext == ".toml":
        try:
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib
            tomllib.loads(konten)
            return True, "Valid TOML format."
        except ModuleNotFoundError:
            return True, "Valid TOML format (tomllib not available on Python <3.11)."
        except Exception as e:
            return False, f"TOML Syntax Error: {e}"
    elif ext in [".js", ".jsx", ".ts", ".tsx", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java", ".cs", ".php"]:
        ok, msg = check_balanced_delimiters(konten)
        if not ok:
            return False, msg
        return True, "Valid syntax structure (delimiters balanced)."

    return True, "No dedicated validator for this file type."


_FENCE_LINE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
_NAMED_FENCE_INFO = re.compile(
    r"^(?:[\w.+-]+[:\s]+)?([A-Za-z0-9_\-./\\]+\.[A-Za-z0-9]+)\s*$"
)
_FILE_HEADER = re.compile(r"^#{1,6}\s*FILE:\s*([A-Za-z0-9_\-./\\]+)\s*$")
_COMMENT_FNAME = re.compile(
    r"^(?:#|//)\s*([A-Za-z0-9_\-./\\]+\.[A-Za-z0-9]+)\s*$"
)


def _filename_from_fence_info(info: str):
    """Return a relative path if the fence info string names a file, else None."""
    info = (info or "").strip().strip('"').strip("'")
    if not info:
        return None
    if ":" in info:
        _lang, rest = info.split(":", 1)
        rest = rest.strip().strip('"').strip("'")
        if rest:
            m = _NAMED_FENCE_INFO.match(rest) or (
                re.match(r"^([A-Za-z0-9_\-./\\]+\.[A-Za-z0-9]+)$", rest)
            )
            if m:
                return m.group(1).replace("\\", "/")
            if "/" in rest or "\\" in rest:
                return rest.replace("\\", "/")
    m = _NAMED_FENCE_INFO.match(info)
    if m:
        name = m.group(1)
        # Bare language ids like "python" have no extension — not a filename.
        base = os.path.basename(name.replace("\\", "/"))
        if "." in base:
            return name.replace("\\", "/")
    return None


def _parse_fence_line(line: str):
    m = _FENCE_LINE.match(line.rstrip("\r\n"))
    if not m:
        return None
    ticks = m.group(2)
    return len(ticks), ticks[0], (m.group(3) or "").strip()


def extract_named_file_fences(response_text: str) -> dict:
    """
    Extract filename → body from AI markdown, including nested inner fences.

    A ```lang:path opener is closed only by a bare fence of the same (or greater)
    length. Inner language-only fences (```bash) are treated as content so a
    README that documents shell commands is not truncated at the first ```.
    """
    text = response_text or ""
    lines = text.splitlines(keepends=True)
    seen = {}
    i = 0
    n = len(lines)

    while i < n:
        header_name = None
        hm = _FILE_HEADER.match(lines[i].strip())
        if hm:
            header_name = hm.group(1).replace("\\", "/")
            i += 1
            while i < n and not lines[i].strip():
                i += 1
            if i >= n:
                break

        if i >= n:
            break
        opening = _parse_fence_line(lines[i])
        if not opening:
            i += 1
            continue

        tick_len, tick_char, info = opening
        fname = header_name or _filename_from_fence_info(info)
        i += 1
        body_parts = []
        inner = 0
        closed_on_bare = False
        while i < n:
            inner_fence = _parse_fence_line(lines[i])
            if inner_fence:
                t2, c2, info2 = inner_fence
                if c2 == tick_char and t2 >= tick_len:
                    if inner == 0:
                        if not info2:
                            closed_on_bare = True
                            break
                        if _filename_from_fence_info(info2) and not header_name:
                            # A new named file fence — close this block; don't consume.
                            break
                        inner += 1
                        body_parts.append(lines[i])
                        i += 1
                        continue
                    if not info2:
                        inner -= 1
                    else:
                        inner += 1
                    body_parts.append(lines[i])
                    i += 1
                    continue
            body_parts.append(lines[i])
            i += 1

        code = "".join(body_parts)
        if not fname:
            first = code.splitlines()[0].strip() if code.strip() else ""
            cm = _COMMENT_FNAME.match(first)
            if cm:
                fname = cm.group(1).replace("\\", "/")
                rest = code.splitlines(keepends=True)
                code = "".join(rest[1:]) if len(rest) > 1 else ""

        if fname:
            seen[fname] = code
        if closed_on_bare:
            i += 1

    return seen


def backup_file(file_path):
    """
    Membuat file backup (.bak) sebelum file ditimpa.
    """
    if os.path.exists(file_path):
        import shutil
        backup_path = file_path + ".bak"
        try:
            shutil.copy2(file_path, backup_path)
            return True, backup_path
        except Exception as e:
            return False, str(e)
    return False, "Original file does not exist yet, backup skipped."


def tulis_file(file_path, konten, buat_backup=True):
    """
    Menulis atau mengupdate isi file secara atomik dengan opsi backup otomatis.
    Menggunakan pola write-to-temp + os.replace untuk mencegah file korup jika crash/interupsi.
    """
    abs_path = os.path.abspath(file_path)
    dir_name = os.path.dirname(abs_path)

    if is_windows_reserved_name(abs_path):
        return False, f"Cannot write file: '{os.path.basename(file_path)}' is a Windows reserved device name."

    try:
        os.makedirs(dir_name, exist_ok=True)
        if buat_backup and os.path.exists(abs_path):
            backup_file(abs_path)

        tmp_path = f"{abs_path}.tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(konten)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, abs_path)
        return True, "File saved successfully."
    except Exception as e:
        tmp_candidate = f"{abs_path}.tmp.{os.getpid()}"
        if os.path.exists(tmp_candidate):
            try:
                os.remove(tmp_candidate)
            except Exception:
                pass
        return False, friendly("Could not save the file", e)


def hapus_item(base_folder, rel_path):
    """
    Menghapus file atau folder di dalam base_folder secara aman.
    Menolak penghapusan root direktori, protected paths (.git, .env, .klyro),
    serta path traversal.
    """
    if not rel_path or rel_path.strip() in [".", "/", "\\", ""]:
        return False, "Cannot delete the project's root folder."

    protected, p_reason = is_protected_workspace_path(rel_path)
    if protected:
        return False, f"Security: {p_reason}"

    target_path = os.path.join(base_folder, rel_path)
    if not is_safe_path(base_folder, target_path, rel_path=rel_path):
        return False, "Security: deletion outside the project folder is not allowed."

    if not os.path.exists(target_path):
        return False, f"File/folder '{rel_path}' not found."

    try:
        if os.path.isdir(target_path):
            import shutil
            shutil.rmtree(target_path)
            return True, f"Folder '{rel_path}' deleted successfully."
        else:
            os.remove(target_path)
            # Also remove the .bak file if one exists
            bak_path = target_path + ".bak"
            if os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except:
                    pass
            return True, f"File '{rel_path}' deleted successfully."
    except Exception as e:
        return False, friendly("Could not delete", e)


def scan_todos(folder_path):
    """
    Mencari semua komentar TODO dan FIXME di dalam file proyek.
    """
    import re
    results = []
    
    # Dapatkan file yang terdaftar di dalam workspace
    files = list_daftar_file(folder_path)
    
    todo_pattern = re.compile(r"\b(TODO|FIXME)\b\s*:?\s*(.*)", re.IGNORECASE)
    
    for rel_path in files:
        fpath = os.path.join(folder_path, rel_path)
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    match = todo_pattern.search(line)
                    if match:
                        todo_text = match.group(2).strip()
                        results.append({
                            "file": rel_path,
                            "line": line_num,
                            "text": todo_text or "General tasks"
                        })
        except Exception:
            pass
            
    return results


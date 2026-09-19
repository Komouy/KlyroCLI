"""
search_tools.py — Project discovery tools for coding intelligence

Tools:
  - FileSearchTool: search files by glob pattern under a root path
  - SymbolSearchTool: locate functions/classes by symbol name regex
"""

import fnmatch
import os
import re
import sys
import time
from typing import Any, Dict, List

from core.tool_registry import Tool, ToolResult
from config import FOLDER_DIABAIKAN

# Directories that are never useful to a "find files in my project" search
# and can be enormous (node_modules, .git internals, venvs, caches, and -
# critically - OS/user-profile noise like AppData, Music, Pictures, Saved
# Games) - always pruned DURING the os.walk() traversal (not filtered after
# the fact).
#
# FIX: this used to be a small hardcoded set duplicated (with drift)
# between FileSearchTool and SymbolSearchTool, neither of which reused
# config.FOLDER_DIABAIKAN even though file_manager.py (startup scan,
# /tree, /files) already relies on that exact list and it is far more
# complete (it's the one place in the codebase that has already learned
# real-world lessons like "don't walk into AppData"). Both search tools
# now import the SAME canonical list, so /find and /symbols get the same
# noise-directory protection the rest of the app already has - instead of
# being the two tools that were quietly less safe than everything else.
_NOISE_DIR_NAMES = set(FOLDER_DIABAIKAN)


class _WalkProgress:
    """Emit lightweight traversal progress without polluting search results."""

    def __init__(self, label: str, interval: float = 2.0, enabled: bool = True):
        self.label = label
        self.interval = max(0.5, interval)
        self.enabled = enabled
        self.started = time.monotonic()
        self.last_report = self.started

    def report(self, directories: int, files: int, force: bool = False) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if not force and now - self.last_report < self.interval:
            return
        elapsed = now - self.started
        print(
            f"[{self.label}] scanning: {directories} directories, {files} files "
            f"({elapsed:.1f}s)",
            file=sys.stderr,
            flush=True,
        )
        self.last_report = now


def _compile_glob_pattern(pattern: str) -> "re.Pattern":
    """
    Compile a glob-style pattern into a regex matched against a `/`-joined
    relative path (root_path-relative, POSIX separators).

    Supports the same subset callers of this tool actually use:
      - '*'  matches any run of characters within one path segment
      - '?'  matches one character within one path segment
      - '**' matches zero or more whole path segments (so '**/*.py' matches
             both a root-level 'main.py' AND 'nested/deep/main.py' - the
             same "zero-or-more directories" semantics glob.glob(...,
             recursive=True) gave callers before, which tests/test_search_
             tools.py already relies on)
    """
    pattern = pattern.replace(os.sep, "/")
    segments = pattern.split("/")

    regex_segments: List[Any] = []
    for seg in segments:
        if seg == "**":
            regex_segments.append(None)  # marker: zero-or-more segments
            continue
        piece = ""
        for ch in seg:
            if ch == "*":
                piece += "[^/]*"
            elif ch == "?":
                piece += "[^/]"
            else:
                piece += re.escape(ch)
        regex_segments.append(piece)

    out = "^"
    n = len(regex_segments)
    for i, seg in enumerate(regex_segments):
        if seg is None:
            out += "(?:[^/]+/)*"
            continue
        out += seg
        if i < n - 1:
            out += "/"
    out += "$"
    return re.compile(out)


class FileSearchTool(Tool):
    """Search for files (and directories) matching a glob pattern under a root directory."""

    name = "file_search"
    description = "Find files by glob pattern within a project folder"
    schema = {
        "type": "object",
        "properties": {
            "root_path": {
                "type": "string",
                "description": "Root directory to search from"
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern relative to root_path, e.g. '**/*.py'"
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Whether to include hidden directories/files (optional)"
            },
            "show_progress": {
                "type": "boolean",
                "description": "Show traversal progress on stderr (optional, default true)"
            },
            "progress_interval": {
                "type": "number",
                "description": "Seconds between progress updates (optional, default 2)"
            },
        },
        "required": ["root_path", "pattern"],
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        self.validate_args(args)

        root_path = args["root_path"]
        pattern = args["pattern"]
        include_hidden = args.get("include_hidden", False)
        progress = _WalkProgress(
            "file_search",
            float(args.get("progress_interval", 2.0)),
            args.get("show_progress", True),
        )

        try:
            if not os.path.isabs(root_path):
                root_path = os.path.abspath(root_path)

            if not os.path.exists(root_path):
                return ToolResult(
                    success=False,
                    output=[],
                    error=f"Root path not found: {root_path}",
                    metadata={"root_path": root_path, "pattern": pattern},
                )

            if not os.path.isdir(root_path):
                return ToolResult(
                    success=False,
                    output=[],
                    error=f"Root path is not a directory: {root_path}",
                    metadata={"root_path": root_path, "pattern": pattern},
                )

            # NOTE (fix): this used to be glob.glob(root/pattern, recursive=True)
            # with hidden-dir filtering applied AFTER glob had already
            # enumerated everything under root_path - so on a huge root
            # (e.g. an entire user home directory) it silently walked into
            # .git/, node_modules/, AppData/, etc. before any filtering
            # happened, making a single /find take a very long time with
            # zero progress output in between. Walking with os.walk() lets
            # us prune noise directories (and hidden ones) DURING descent,
            # same as SymbolSearchTool already does - so those subtrees are
            # never even entered, not just filtered from the final list.
            matcher = _compile_glob_pattern(pattern)
            matches: List[str] = []
            directories_scanned = 0
            files_scanned = 0

            for current_root, dirnames, filenames in os.walk(root_path):
                directories_scanned += 1
                files_scanned += len(filenames)
                progress.report(directories_scanned, files_scanned)
                dirnames[:] = sorted(
                    d for d in dirnames
                    if d not in _NOISE_DIR_NAMES
                    and (include_hidden or not d.startswith("."))
                )

                for d in dirnames:
                    full_path = os.path.join(current_root, d)
                    rel = os.path.relpath(full_path, root_path).replace(os.sep, "/")
                    if matcher.match(rel):
                        matches.append(full_path)

                for filename in sorted(filenames):
                    if not include_hidden and filename.startswith("."):
                        continue
                    full_path = os.path.join(current_root, filename)
                    rel = os.path.relpath(full_path, root_path).replace(os.sep, "/")
                    if matcher.match(rel):
                        matches.append(full_path)

            matches.sort()
            progress.report(directories_scanned, files_scanned, force=True)

            return ToolResult(
                success=True,
                output=matches,
                metadata={
                    "root_path": root_path,
                    "pattern": pattern,
                    "count": len(matches),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            return ToolResult(
                success=False,
                output=[],
                error=str(exc),
                details=f"Failed to search files in {root_path}",
            )


class SymbolSearchTool(Tool):
    """Search for function/class symbols across a project tree."""

    name = "symbol_search"
    description = "Find symbols such as functions, classes, and methods in code files"
    schema = {
        "type": "object",
        "properties": {
            "root_path": {
                "type": "string",
                "description": "Root directory to scan recursively"
            },
            "query": {
                "type": "string",
                "description": "Regex pattern to match symbol names, e.g. 'build_user|UserService'"
            },
            "file_pattern": {
                "type": "string",
                "description": "Optional glob for file names, e.g. '**/*.py'"
            },
            "show_progress": {
                "type": "boolean",
                "description": "Show traversal progress on stderr (optional, default true)"
            },
            "progress_interval": {
                "type": "number",
                "description": "Seconds between progress updates (optional, default 2)"
            },
        },
        "required": ["root_path", "query"],
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        self.validate_args(args)

        root_path = args["root_path"]
        query = args["query"]
        file_pattern = args.get("file_pattern")
        progress = _WalkProgress(
            "symbol_search",
            float(args.get("progress_interval", 2.0)),
            args.get("show_progress", True),
        )

        try:
            if not os.path.isabs(root_path):
                root_path = os.path.abspath(root_path)

            if not os.path.exists(root_path):
                return ToolResult(
                    success=False,
                    output=[],
                    error=f"Root path not found: {root_path}",
                    metadata={"root_path": root_path, "query": query},
                )

            if not os.path.isdir(root_path):
                return ToolResult(
                    success=False,
                    output=[],
                    error=f"Root path is not a directory: {root_path}",
                    metadata={"root_path": root_path, "query": query},
                )

            symbol_regex = re.compile(
                r"^\s*(?:async\s+)?(?P<kind>def|class|function|fn|interface|enum|const|let|var)\s+(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            )
            pattern_compiled = re.compile(query, re.IGNORECASE)

            matches: List[Dict[str, Any]] = []
            directories_scanned = 0
            files_scanned = 0
            for current_root, dirnames, filenames in os.walk(root_path):
                directories_scanned += 1
                files_scanned += len(filenames)
                progress.report(directories_scanned, files_scanned)
                dirnames[:] = [
                    directory
                    for directory in dirnames
                    if not directory.startswith(".")
                    and directory not in _NOISE_DIR_NAMES
                ]

                for filename in sorted(filenames):
                    full_path = os.path.join(current_root, filename)
                    if file_pattern and not fnmatch.fnmatch(full_path, os.path.join(root_path, file_pattern)):
                        continue

                    if not filename.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift")):
                        continue

                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as handle:
                            content = handle.read()
                    except OSError:
                        continue

                    for line_number, line in enumerate(content.splitlines(), start=1):
                        match = symbol_regex.match(line)
                        if not match:
                            continue

                        symbol_name = match.group("symbol")
                        if not pattern_compiled.search(symbol_name):
                            continue

                        matches.append(
                            {
                                "file": full_path,
                                "symbol": symbol_name,
                                "kind": match.group("kind"),
                                "line": line_number,
                                "match": line.strip(),
                            }
                        )

            matches.sort(key=lambda item: (item["file"], item["line"], item["symbol"]))
            progress.report(directories_scanned, files_scanned, force=True)
            return ToolResult(
                success=True,
                output=matches,
                metadata={
                    "root_path": root_path,
                    "query": query,
                    "count": len(matches),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            return ToolResult(
                success=False,
                output=[],
                error=str(exc),
                details=f"Failed to search symbols in {root_path}",
            )
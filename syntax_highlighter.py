"""
syntax_highlighter.py — Lightweight, zero-dependency ANSI syntax highlighter
designed for Klyro CLI's Nordic Frost terminal theme.
"""

from __future__ import annotations

import re
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_AQUA, FROST_ICE, FROST_MINT, FROST_INDIGO,
    FROST_CORAL, FROST_AMBER, FROST_WHITE, FROST_GRAY, FROST_DARK,
)

# ─────────────────────────────────────────────────────────────
# LANGUAGE KEYWORDS & PATTERNS
# ─────────────────────────────────────────────────────────────

PYTHON_KEYWORDS = {
    "and", "as", "assert", "async", "await", "break", "case", "class",
    "continue", "def", "del", "elif", "else", "except", "finally", "for",
    "from", "global", "if", "import", "in", "is", "lambda", "match",
    "nonlocal", "not", "or", "pass", "raise", "return", "try", "while",
    "with", "yield",
}

PYTHON_BUILTINS = {
    "True", "False", "None", "self", "cls", "print", "len", "range",
    "int", "str", "float", "bool", "list", "dict", "set", "tuple",
    "super", "isinstance", "type", "enumerate", "zip", "open",
}

JS_KEYWORDS = {
    "async", "await", "break", "case", "catch", "class", "const", "continue",
    "debugger", "default", "delete", "do", "else", "export", "extends",
    "finally", "for", "from", "function", "if", "import", "in", "instanceof",
    "let", "new", "of", "return", "static", "super", "switch", "this",
    "throw", "try", "typeof", "var", "void", "while", "with", "yield",
    "interface", "type", "implements", "declare", "namespace",
}

JS_BUILTINS = {
    "true", "false", "null", "undefined", "NaN", "Infinity",
    "console", "window", "document", "process", "Promise", "Array",
    "Object", "String", "Number", "Boolean", "JSON", "Math",
}

BASH_KEYWORDS = {
    "if", "then", "else", "elif", "fi", "for", "while", "do", "done",
    "case", "esac", "function", "select", "time", "until", "echo",
    "export", "source", "alias", "return", "exit", "local", "read",
    "cd", "mkdir", "rm", "cp", "mv", "grep", "cat", "chmod", "curl",
}

SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "INSERT", "INTO", "UPDATE", "DELETE",
    "CREATE", "TABLE", "DROP", "ALTER", "JOIN", "INNER", "LEFT", "RIGHT",
    "OUTER", "FULL", "ON", "GROUP", "BY", "ORDER", "HAVING", "LIMIT",
    "OFFSET", "UNION", "ALL", "AS", "AND", "OR", "NOT", "IN", "IS",
    "NULL", "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END",
}

# Normalize common lang aliases
_LANG_ALIASES = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "javascript",
    "tsx": "typescript",
    "sh": "bash",
    "zsh": "bash",
    "ps1": "powershell",
    "yml": "yaml",
    "htm": "html",
}


def normalize_lang(lang: str) -> str:
    if not lang:
        return "text"
    cleaned = lang.split(":")[0].strip().lower()
    return _LANG_ALIASES.get(cleaned, cleaned)


def highlight_line(line: str, lang: str = "python") -> str:
    """Highlight a single line of source code with Nordic Frost ANSI colors."""
    if not line:
        return line

    lang = normalize_lang(lang)
    if lang in ("text", "plain", "txt"):
        return line

    # 1. JSON
    if lang == "json":
        return _highlight_json_line(line)

    # 2. Markdown
    if lang in ("markdown", "md"):
        return _highlight_markdown_line(line)

    # 3. HTML / XML
    if lang in ("html", "xml", "svg"):
        return _highlight_html_line(line)

    # 4. General / C-like / Python / JS / Bash
    return _highlight_general_line(line, lang)


def _highlight_json_line(line: str) -> str:
    # Keys: "key":
    def repl_key(m):
        return f'{FROST_CYAN}"{m.group(1)}"{RESET}:'
    line = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*:', repl_key, line)

    # String values: : "value"
    def repl_val(m):
        prefix = m.group(1)
        val = m.group(2)
        return f'{prefix}{FROST_MINT}"{val}"{RESET}'
    line = re.sub(r'(:\s*)"([^"\\]*(?:\\.[^"\\]*)*)"', repl_val, line)

    # Numbers
    line = re.sub(r'\b(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b', f'{FROST_AMBER}\\1{RESET}', line)

    # Booleans & null
    line = re.sub(r'\b(true|false|null)\b', f'{FROST_ICE}\\1{RESET}', line)
    return line


def _highlight_markdown_line(line: str) -> str:
    stripped = line.strip()
    # Headings: # Heading
    if stripped.startswith("#"):
        return f"{FROST_CYAN}{BOLD}{line}{RESET}"
    # Bullet points: - item or * item
    if stripped.startswith(("- ", "* ", "+ ")):
        return f"{FROST_MINT}•{RESET}{line[line.find(stripped[0])+1:]}"
    # Blockquotes: > quote
    if stripped.startswith(">"):
        return f"{FROST_ICE}{line}{RESET}"
    return line


def _highlight_html_line(line: str) -> str:
    # Comments: <!-- ... -->
    if "<!--" in line:
        return re.sub(r'(<!--.*?-->)', f'{FROST_DARK}\\1{RESET}', line)
    # Tags: <tag or </tag or />
    line = re.sub(r'(</?)([a-zA-Z0-9_\-]+)', f'{FROST_DARK}\\1{RESET}{FROST_CYAN}\\2{RESET}', line)
    line = re.sub(r'(/?>)', f'{FROST_DARK}\\1{RESET}', line)
    # Attributes: attr="value"
    line = re.sub(r'\b([a-zA-Z0-9_\-]+)=(".*?"|\'.*?\')', f'{FROST_ICE}\\1{RESET}={FROST_MINT}\\2{RESET}', line)
    return line


def _highlight_general_line(line: str, lang: str) -> str:
    # Extract comment part if present
    comment_char = "#" if lang in ("python", "bash", "yaml", "toml", "ruby") else "//"
    comment_idx = -1

    # Check if comment_char exists outside of string quotes
    in_quote = None
    for idx, ch in enumerate(line):
        if ch in ('"', "'", "`"):
            if not in_quote:
                in_quote = ch
            elif in_quote == ch and (idx == 0 or line[idx - 1] != "\\"):
                in_quote = None
        elif not in_quote:
            if line[idx:idx + len(comment_char)] == comment_char:
                comment_idx = idx
                break

    comment_part = ""
    code_part = line
    if comment_idx != -1:
        code_part = line[:comment_idx]
        comment_part = f"{FROST_DARK}{line[comment_idx:]}{RESET}"

    # Pick keywords/builtins based on language
    if lang == "python":
        keywords = PYTHON_KEYWORDS
        builtins = PYTHON_BUILTINS
    elif lang in ("javascript", "typescript"):
        keywords = JS_KEYWORDS
        builtins = JS_BUILTINS
    elif lang == "bash":
        keywords = BASH_KEYWORDS
        builtins = {"true", "false"}
    elif lang == "sql":
        keywords = SQL_KEYWORDS
        builtins = {"NULL", "TRUE", "FALSE"}
    else:
        keywords = PYTHON_KEYWORDS | JS_KEYWORDS
        builtins = PYTHON_BUILTINS | JS_BUILTINS

    # Regex token replacement on code_part
    # 1. Strings: "...", '...', `...`
    def repl_string(m):
        return f"{FROST_MINT}{m.group(0)}{RESET}"
    code_part = re.sub(r'("([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\'|`([^`\\]|\\.)*`)', repl_string, code_part)

    # 2. Decorators (Python / TS)
    if lang in ("python", "typescript"):
        code_part = re.sub(r'(@\w+)', f'{FROST_CORAL}\\1{RESET}', code_part)

    # 3. Numbers
    code_part = re.sub(r'\b(\d+(?:\.\d+)?|0x[0-9a-fA-F]+)\b', f'{FROST_AMBER}\\1{RESET}', code_part)

    # 4. Keywords
    kw_pattern = r'\b(' + '|'.join(re.escape(k) for k in keywords) + r')\b'
    code_part = re.sub(kw_pattern, f'{FROST_CYAN}\\1{RESET}', code_part)

    # 5. Builtins / Booleans
    bi_pattern = r'\b(' + '|'.join(re.escape(b) for b in builtins) + r')\b'
    code_part = re.sub(bi_pattern, f'{FROST_ICE}\\1{RESET}', code_part)

    # 6. Function definitions: def foo( / function foo(
    code_part = re.sub(r'\b(def|function)\s+([a-zA-Z0-9_]+)', f'{FROST_CYAN}\\1{RESET} {FROST_INDIGO}{BOLD}\\2{RESET}', code_part)

    return code_part + comment_part


def highlight_code_block(code_lines: list[str], lang: str = "python") -> list[str]:
    """Highlight a list of code lines, preserving indentation."""
    return [highlight_line(l, lang) for l in code_lines]

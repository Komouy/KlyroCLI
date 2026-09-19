"""
undo_manager.py — Multi-Step File Modification Revert System for KlyroCLI
Maintains a transactional undo stack for file edits, creations, renames, and deletions.

Persisted to <project>/.klyro/undo_log.json so the undo history survives a
CLI crash or restart — previously this was purely in-memory and any
unsaved crash silently lost the ability to /undo, even though the .bak
backups it depends on were already sitting on disk.
"""

import os
import json
import shutil
import file_manager
from errors import friendly

# In-memory cache mirroring the on-disk log: folder_path -> list of transactions
# (each transaction is a list of op dicts). Loaded lazily per folder on first use.
_UNDO_STACK = {}
_LOADED_FOLDERS = set()

MAX_UNDO_STEPS = 25


def validate_operation(op: dict, folder_abs: str) -> bool:
    """
    Validate that an undo operation has a valid structure and safe paths:
      - 'modify': valid path inside workspace, old_content is str or None
      - 'create': valid path inside workspace
      - 'delete': valid path inside workspace, old_content is str or None
      - 'rename': valid src & dst inside workspace
    """
    if not isinstance(op, dict):
        return False

    op_type = op.get("type")
    if op_type not in ("modify", "create", "delete", "rename"):
        return False

    if op_type in ("modify", "delete"):
        target = op.get("path")
        if not target or not isinstance(target, str):
            return False
        if not file_manager.is_safe_path(folder_abs, target):
            return False
        if "old_content" in op and op["old_content"] is not None and not isinstance(op["old_content"], str):
            return False
        return True

    elif op_type == "create":
        target = op.get("path")
        if not target or not isinstance(target, str):
            return False
        return file_manager.is_safe_path(folder_abs, target)

    elif op_type == "rename":
        src = op.get("src")
        dst = op.get("dst")
        if not src or not dst or not isinstance(src, str) or not isinstance(dst, str):
            return False
        return file_manager.is_safe_path(folder_abs, src) and file_manager.is_safe_path(folder_abs, dst)

    return False


def _log_path(folder_path: str) -> str:
    klyro_dir = os.path.join(os.path.abspath(folder_path), ".klyro")
    try:
        os.makedirs(klyro_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(klyro_dir, "undo_log.json")


def _ensure_loaded(folder_abs: str):
    """Lazily load persisted undo history for a folder into memory, once."""
    if folder_abs in _LOADED_FOLDERS:
        return
    _LOADED_FOLDERS.add(folder_abs)

    log_file = _log_path(folder_abs)
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                # Sanitize and validate loaded transactions
                cleaned_stack = []
                for txn in data:
                    if isinstance(txn, list):
                        valid_txn = [op for op in txn if validate_operation(op, folder_abs)]
                        if valid_txn:
                            cleaned_stack.append(valid_txn)
                _UNDO_STACK[folder_abs] = cleaned_stack
        except Exception:
            pass  # Corrupt/unreadable log: start fresh rather than crash

    if folder_abs not in _UNDO_STACK:
        _UNDO_STACK[folder_abs] = []


def _persist(folder_abs: str):
    """
    Write the current in-memory stack for this folder to disk using atomic replacement.
    Prevents corrupt/zero-byte undo_log.json if interrupted mid-write.
    """
    log_file = _log_path(folder_abs)
    tmp_file = f"{log_file}.tmp.{os.getpid()}"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(_UNDO_STACK.get(folder_abs, []), f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, log_file)
    except Exception:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def record_transaction(folder_path: str, ops: list[dict]):
    """
    Record an atomic transaction containing one or more file operations.
    Validates all ops before recording to protect stack integrity.
    op format:
      - {"type": "modify", "path": str, "old_content": str}
      - {"type": "create", "path": str}
      - {"type": "delete", "path": str, "old_content": str}
      - {"type": "rename", "src": str, "dst": str}
    """
    if not ops:
        return

    folder_abs = os.path.abspath(folder_path)
    _ensure_loaded(folder_abs)

    valid_ops = [op for op in ops if validate_operation(op, folder_abs)]
    if not valid_ops:
        return

    _UNDO_STACK[folder_abs].append(valid_ops)
    # Limit max undo steps
    if len(_UNDO_STACK[folder_abs]) > MAX_UNDO_STEPS:
        _UNDO_STACK[folder_abs].pop(0)

    _persist(folder_abs)


def get_undo_depth(folder_path: str) -> int:
    """Return number of reversible transactions for folder."""
    folder_abs = os.path.abspath(folder_path)
    _ensure_loaded(folder_abs)
    return len(_UNDO_STACK.get(folder_abs, []))


def apply_undo(folder_path: str) -> tuple[bool, list[str]]:
    """
    Revert the most recent file modification transaction.
    Returns: (success: bool, list_of_reverted_actions: list[str])
    """
    folder_abs = os.path.abspath(folder_path)
    _ensure_loaded(folder_abs)
    stack = _UNDO_STACK.get(folder_abs, [])

    if not stack:
        return False, ["No recent file changes to undo."]

    ops = stack.pop()
    _persist(folder_abs)
    reverted_logs = []

    # Reverse operations order to undo cleanly
    for op in reversed(ops):
        op_type = op.get("type")
        
        try:
            if op_type in ("modify", "delete"):
                target = op.get("path")
                old_content = op.get("old_content")
                if target and old_content is not None:
                    if not file_manager.is_safe_path(folder_abs, target):
                        reverted_logs.append(f"Security: skipped unsafe path {target}")
                        continue
                    ok_write, msg_write = file_manager.tulis_file(target, old_content, buat_backup=False)
                    rel = os.path.relpath(target, folder_abs)
                    if ok_write:
                        action_label = "Restored previous content of" if op_type == "modify" else "Restored deleted file"
                        reverted_logs.append(f"{action_label}: {rel}")
                    else:
                        reverted_logs.append(f"Failed to restore {rel}: {msg_write}")

            elif op_type == "create":
                target = op.get("path")
                if target:
                    if not file_manager.is_safe_path(folder_abs, target):
                        reverted_logs.append(f"Security: skipped unsafe path {target}")
                        continue
                    if os.path.exists(target):
                        os.remove(target)
                        rel = os.path.relpath(target, folder_abs)
                        reverted_logs.append(f"Removed created file: {rel}")

            elif op_type == "rename":
                src = op.get("src")
                dst = op.get("dst")
                if dst and src:
                    if not file_manager.is_safe_path(folder_abs, src) or not file_manager.is_safe_path(folder_abs, dst):
                        reverted_logs.append(f"Security: skipped unsafe rename path {dst} -> {src}")
                        continue
                    if os.path.exists(dst):
                        os.makedirs(os.path.dirname(os.path.abspath(src)), exist_ok=True)
                        os.rename(dst, src)
                        rel_src = os.path.relpath(src, folder_abs)
                        rel_dst = os.path.relpath(dst, folder_abs)
                        reverted_logs.append(f"Restored file name: {rel_dst} → {rel_src}")

        except Exception as e:
            reverted_logs.append(friendly(f"Could not revert {op_type}", e))

    return True, reverted_logs

# Debugging Notes for KlyroCLI

## Kelompok A — Keamanan (Security)

### 1. Missing import in search tools

#### Problem
`tools/search_tools.py` used `glob.fnmatch.fnmatch(...)` but the module `glob` was never imported.

This caused a runtime `NameError` when the symbol-search flow ran, even though the rest of the project looked intact from a superficial import check.

#### Impact
- `SymbolSearchTool` can fail at runtime
- project discovery becomes unreliable
- the agent workflow loses the ability to find relevant symbols in code

#### Root cause
The code path was added without a matching import and without a small regression test covering the tool behavior.

#### Fix
Add the missing import:

```python
import glob
```

and verify with a focused test covering file and symbol search behavior.

---

### 2. Search tools were not yet part of the core tool layer

#### Problem
The roadmap defined a coding-intelligence phase with project understanding, relevant-file selection, and symbol search, but the actual tool layer lacked concrete implementations for those capabilities.

#### Impact
- the agent could not discover relevant files before editing
- context gathering was too shallow
- the AI had limited ability to reason about project structure

#### Root cause
The generic agent and registry existed, but the specialized search tools were missing from the actual runtime tool set.

#### Fix
Implement and register:
- `FileSearchTool`
- `SymbolSearchTool`

Then export them from `tools/__init__.py` and register them in the demo agent setup.

---

### 3. Shell command execution is the highest-risk security area

#### Problem
`tools/shell_tools.py` executes commands with `shell=True` unless constrained.

This is easy to use, but it becomes dangerous if an AI prompt or user input contains unsafe shell syntax or command injection patterns.

#### Impact
- dangerous commands can be executed
- developer system or workspace can be modified unintentionally
- trust between the AI and the user breaks down

#### Root cause
The tool is powerful and flexible, but no explicit allowlist/filter policy is enforced before execution.

#### Fix
Use a layered safety approach:
- block known dangerous patterns (`rm -rf`, `del /s`, `format`, `curl | bash`, etc.)
- require confirmation before high-risk commands
- restrict working directory when possible
- enforce a safe command allowlist for common workflows

---

### 4. File safety policy must be centralized

#### Problem
The project has path validation logic in several places, but safety decisions should not be spread across multiple modules with slightly different rules.

#### Impact
- one module may allow a path another rejects
- file writes/deletes may behave inconsistently
- hidden edge cases can show up only in production workflows

#### Root cause
Path validation and sandbox logic are implemented in separate places rather than following a single policy source of truth.

#### Fix
Establish one canonical rule for:
- allowed root directory
- relative path restrictions
- absolute path rejection
- traversal protections

Ideally, all file operations should route through the same validator.

---

### 5. Critical risk: AI can trigger destructive operations without enough friction

#### Problem
The tool layer allows AI-driven shell/file mutation actions, but not every call requires a strong user checkpoint or risk review.

#### Impact
- a mistaken or malicious instruction can cause destructive behavior
- low-friction execution increases the likelihood of accidental damage

#### Root cause
The system focuses on capability and speed, but does not always create a strong safety barrier before the operation is executed.

#### Fix
Require explicit confirmation for:
- shell execution
- file writes
- file deletes
- directory creation
- rename/move operations

Prefer a fail-closed default: if confidence is low, deny and show the exact risk.

---

## Kelompok B — UX (User Experience)

### 1. Approval prompts are too blunt and not informative enough

#### Problem
Many confirmation prompts are generic, such as “Confirm? (Y/n)”, without enough context about what will change.

#### Impact
- users do not know what the AI is about to do
- users become confused or annoyed
- trust in the system drops because the prompt feels opaque

#### Root cause
The system prioritizes action execution speed over clarity of intent and explanation.

#### Fix
Display:
- file target
- action type
- short summary of the change
- whether it is a write, delete, move, or shell action
- risk warning if relevant

---

### 2. Too many interruptions can reduce productivity

#### Problem
If the AI asks for confirmation for every tiny action, the user experiences constant interruptions during ordinary tasks.

#### Impact
- user loses momentum
- agent feels slow and noisy
- the workflow becomes frustrating

#### Root cause
The approval system is applied uniformly without distinguishing low-risk actions from high-risk actions.

#### Fix
Use tiered approval:
- low-risk read/search actions: no interruption
- medium-risk write operations: one confirmation summary
- high-risk shell commands: louder warning + explicit confirmation
- optional “approve this session” mode for low-risk repeated tasks

---

### 3. Error messages are sometimes too vague

#### Problem
When an action fails, the user may only see a generic error without context about what happened or what to do next.

#### Impact
- users do not know whether the issue is their input, a tool problem, or a security block
- debugging becomes slower
- the AI feels unreliable

#### Root cause
The system reports failure but not enough diagnostic or recovery guidance.

#### Fix
Return structured errors with:
- action name
- reason category
- short message
- suggested next step

Examples:
- blocked by safety policy
- path outside workspace
- command timed out
- invalid input

---

### 4. The system needs clearer mental model for the user

#### Problem
Users need to understand what the agent is doing at each stage: reading, planning, changing, verifying, or blocking.

#### Impact
- the interface feels mysterious
- users do not know whether the AI is working or stuck
- confidence drops during multi-step tasks

#### Root cause
The system is capable, but not transparent enough in the way it communicates progress and decision points.

#### Fix
Show a simple flow:
1. read/search
2. decide
3. propose change
4. ask for approval
5. apply
6. verify

This makes the agent feel predictable and understandable.

---

### 5. UX and safety must be aligned, not treated as separate concerns

#### Problem
Security and UX are often handled by different code paths, leading to poor user experience even when behavior is technically safe.

#### Impact
- prompts feel either too harsh or too vague
- users either ignore warnings or get overwhelmed by them
- the AI feels less trustworthy

#### Root cause
The project treats safety as a backend concern and UX as a frontend concern, but here they must work together in the same workflow.

#### Fix
Tie safety warnings to clear user-facing explanations:
- what is dangerous
- why it is blocked
- what the user can do instead

This gives both protection and confidence.

---

## Cross-cutting issues

### Tool behavior is not fully protected by end-to-end tests

#### Problem
The project had some basic unit-level checks, but not enough integration coverage for the real agent workflows and dangerous operations.

#### Impact
- bugs are only discovered after a user triggers a specific flow
- confidence in the tool layer is lower than it should be
- refactors can silently break real user behavior

---

## Status terbaru — Approval UX flow

### 1. Tugas yang sudah selesai

#### Problem
Approval flow sebelumnya terlalu generik dan tidak memberi konteks yang cukup sebelum user menyetujui suatu mutating action.

#### Impact
- user tidak tahu aksi apa yang akan dijalankan
- keputusan setuju/tolak terasa asal-asalan
- user lebih mudah ragu atau terganggu oleh prompt yang terlalu umum

#### Root cause
Prompt approval fokus pada “is there a confirmation?” tetapi tidak menjelaskan target, jenis aksi, atau risiko yang terlibat.

#### Fix implemented
Dalam `approval_gate.py`, kami menambahkan summary yang jelas untuk:
- file write
- file delete
- directory create
- rename / move
- shell execution

Prompt sekarang menampilkan:
- aksi yang diminta
- target file/folder
- ringkasan perubahan
- warning jika action destruktif atau berisiko tinggi

Selain itu, kami juga menambahkan regression test untuk approval summary pada file write dan shell command.

#### Evidence
Verifikasi yang dijalankan berhasil:

```powershell
& "C:\Python314\python.exe" -m pytest -q tests/test_approval_gate.py tests/test_shell_safety.py tests/test_search_tools.py -rA
```

Hasil: 6 passed in 0.15s.

---

### 2. Yang masih kurang / perlu diperbaiki berikutnya

#### A. Approval belum benar-benar tiered
Masih ada peluang untuk membedakan low-risk dan high-risk lebih jelas.

Yang kurang:
- read/search tidak perlu interupsi
- write biasa perlu ringkasan singkat
- shell berisiko tinggi perlu warning yang lebih kuat
- ada kemungkinan “approve once for this session” untuk task yang berulang

#### B. UX masih bisa dibuat lebih ringan
Prompt approval yang sudah lebih jelas itu bagus, tapi masih bisa dibuat lebih halus agar tidak terasa mengganggu.

Yang kurang:
- pemisahan antara “informasi” dan “keputusan final”
- mode ringkas untuk aksi kecil yang terdengar aman
- pengurangan interupsi pada workflow rutin

#### C. Safety policy dan UX policy belum sepenuhnya bersatu
Saat ini keamanan dan tampilan UI dipikirkan sebagai dua jalur yang berbeda, padahal dalam workflow approval keduanya harus berjalan bersama.

Yang kurang:
- satu sumber kebenaran untuk tingkat risiko tindakan
- aksi yang sama harus punya ringkasan, risiko, dan penolakan yang konsisten

#### D. Masih perlu observasi masalah realistis di workflow nyata
Unit test dan targeted regression sudah membantu, tetapi tidak menggantikan pengujian terhadap alur real user yang lebih panjang dan lebih beragam.

Yang kurang:
- end-to-end scenario dengan multi-step agent task
- validasi kesan UX oleh pengguna nyata
- monitoring apakah prompt terlalu banyak muncul atau terlalu sedikit

---

### 3. Kesimpulan status saat ini

Approval UX sudah berada pada status “fix selesai untuk titik masalah utama”: user kini diberi konteks yang cukup sebelum menyetujui perubahan. Namun, sistem masih perlu ditingkatkan dari sisi efisiensi dan konsistensi risk-tiering agar workflow terasa lebih natural dan tidak terlalu interruptif.

---

## Status audit keamanan — 2026-09-03

### 1. Workspace symlink escape

#### Finding
`is_safe_path()` sebelumnya membandingkan `abspath()` saja. Symlink yang berada di dalam workspace dapat mengarah ke file atau folder di luar workspace, sehingga path terlihat aman walaupun target sebenarnya berada di luar batas.

#### Fix implemented
Validasi workspace sekarang menggunakan `realpath()` untuk base folder dan target sebelum `commonpath()` dibandingkan. Ini menutup escape melalui symlink untuk file read/write/delete/mkdir/rename yang memakai validator terpusat.

### 2. Shell working-directory escape

#### Finding
`ShellTool` menerima `cwd` bebas. Walaupun command sudah meminta approval, command yang disetujui dapat berjalan dari direktori di luar workspace.

#### Fix implemented
`ShellTool` sekarang:
- default berjalan dari workspace
- menolak `cwd` di luar workspace
- menyelesaikan symlink pada `cwd` sebelum pemeriksaan
- menolak perbedaan drive atau path yang tidak dapat dibandingkan

### 3. Regression evidence

Verifikasi terarah berhasil:

```text
7 passed, 1 skipped in 1.30s
```

Test yang ditambahkan:
- shell `cwd` di luar workspace harus diblokir
- file read melalui symlink ke luar workspace harus diblokir

Test symlink di-skip pada environment Windows ini karena akun tidak memiliki privilege membuat symlink (`WinError 1314`). Ini adalah keterbatasan environment test, bukan hasil keamanan yang dianggap lulus.

### 4. Risiko yang masih tersisa

- Banyak pemanggilan `subprocess.run(..., shell=True)` masih berada di legacy CLI, runner, doctor, dan terminal; masing-masing perlu audit boundary dan approval secara terpisah.
- Denylist command tetap hanya lapisan warning, bukan bukti bahwa command aman.
- Registry/demo masih dapat membuat `ShellTool()` tanpa base folder eksplisit; default saat ini adalah current working directory, sehingga integrasi production harus selalu mengirim workspace root yang benar.

---

## Status audit search traversal — 2026-09-03

### Fakta noise directory

`config.FOLDER_DIABAIKAN` saat ini sudah berisi `AppData`. Karena search tools memang memakai daftar canonical tersebut untuk pruning saat `os.walk()`, subtree `AppData\Local` dan `AppData\LocalLow` ikut berhenti secara otomatis ketika root pencarian melewati home directory. `dll` adalah ekstensi file, bukan nama directory, sehingga tidak termasuk kategori noise-dir.

Root pencarian tetap sepenuhnya mengikuti `root_path` yang diminta caller. Memilih home directory lalu mencari `**/*` tetap merupakan permintaan untuk memindai seluruh area yang tidak dipangkas; tool tidak mengubah root itu secara diam-diam.

### Progress indicator

`FileSearchTool` dan `SymbolSearchTool` sekarang menampilkan progress periodik ke `stderr`:
- jumlah directory yang sudah dipindai
- jumlah file yang sudah ditemukan dalam traversal
- waktu berjalan
- laporan akhir ketika traversal selesai

Progress dapat dimatikan dengan `show_progress: false`, dan interval dapat diatur dengan `progress_interval`.

### QuickEdit limitation

Progress output membantu membedakan proses lambat dari proses macet, tetapi Windows QuickEdit dapat tetap menjeda proses ketika console masuk mode selection setelah user mengklik/menyeleksi output. Ini adalah isu konfigurasi console interaktif dan belum dianggap selesai oleh perubahan search tool.

### Static diagnostic fixed

Pemanggilan `glob.fnmatch.fnmatch` diganti menjadi import langsung `fnmatch.fnmatch`, sehingga diagnostics Pylance/compile tidak lagi melaporkan attribute yang tidak dikenal.

#### Root cause
The project has many modules and features, but the test suite is too narrow relative to the system complexity.

#### Fix
Add focused regression tests for:
- file search
- symbol search
- safe path validation
- file read/write restrictions
- shell command blocking behavior

---

### Project complexity is growing faster than governance

#### Problem
The project has many moving parts at once: agent loop, tool registry, files, shell commands, config, sessions, undo, doctor, routing, provider selection, and UI logic.

#### Impact
- bugs appear in unrelated areas because no single policy governs them all
- debugging becomes harder as system complexity increases
- small changes may have unpredictable side effects

#### Root cause
The project is growing in layers without a strong discipline for ownership and verification.

#### Fix
Use a layered roadmap and work in slices:
1. Core agent loop
2. Coding intelligence
3. Safety / approval
4. UX and workflow polish
5. Advanced features

Each slice should have:
- a clear goal
- a minimal test
- a verification step before moving on

---

## Recommended operating principles

1. Never start a new feature before the current one is verified.
2. Keep safety checks centralized.
3. Use targeted tests instead of broad, expensive validation cycles.
4. Treat shell execution and file mutation as privileged operations.
5. Maintain one source of truth for workspace boundaries and allowed directories.
6. Make user prompts short, relevant, and understandable.
7. Separate low-risk and high-risk operations in the approval flow.

---

## Verification status

The targeted issue for the search layer has been tested and verified:

- `tests/test_search_tools.py`
- Result: 2 passed in 0.17s
- `tests/test_shell_safety.py`
- Result: 2 passed in 0.15s
- Import smoke test: successful
- Project compile check: successful

This confirms the key bugs in the search tool layer and the critical shell safety gate were fixed and did not immediately regress.

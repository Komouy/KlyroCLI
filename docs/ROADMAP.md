Roadmap KlyroCLI

Phase 1 — Core Agent

Agent Loop
Tool abstraction
Context management
Action execution
Error → retry loop

Phase 2 — Coding Intelligence

Project understanding
Relevant-file selection
Symbol/code search
Dependency awareness
Better context compression

Phase 3 — Safety

Permission system
Command approval
File-change approval
Sandbox
Undo/rollback

Phase 4 — Developer Experience

Better diff
Progress UI
Todo/task tracking
Git integration
Diagnostics

Phase 5 — Advanced

Smart routing
Consensus
Multi-agent
MCP
Plugin system
Background tasks

Dengan begitu, consensus_engine.py dan smart routing bukan menjadi pusat Klyro. Mereka menjadi kemampuan tambahan di atas core agent.

1. CoreAgent — ini prioritas nomor satu

Potongan:

class CoreAgent:
    def plan(task) -> Action[]
    def execute(action) -> Result
    def observe(result) -> State
    def retry_policy(error) -> bool

adalah arah yang bagus.

Tapi saya akan membuatnya sedikit lebih generik:

class Agent:
    def run(self, task):
        ...

Internalnya:

run(task)
   │
   ▼
plan()
   │
   ▼
Action
   │
   ▼
execute()
   │
   ▼
Result
   │
   ▼
observe()
   │
   ├── success → next action / finish
   │
   └── error
         │
         ▼
    retry_policy()
         │
       retry

Ini penting karena nanti Klyro bisa melakukan sesuatu seperti:

User:
"Perbaiki error login."

Agent:
  ↓
inspect files
  ↓
find authentication code
  ↓
read relevant files
  ↓
identify error
  ↓
edit
  ↓
run test
  ↓
observe error
  ↓
edit again
  ↓
run test
  ↓
success

Itulah agent loop sebenarnya.

Bukan sekadar:

prompt → AI → ACTION → selesai
2. Tool Registry — ini bahkan lebih penting daripada ACTION parser

Sekarang:

AI
 ↓
ACTION tag
 ↓
apply_actions.py

terlalu spesifik.

Targetnya:

AI
 ↓
Tool call
 ↓
Tool Registry
 ↓
Tool Executor

Contoh:

tools = {
    "file_read": FileReadTool(),
    "file_write": FileWriteTool(),
    "file_search": FileSearchTool(),
    "shell": ShellTool(),
}

Kemudian setiap tool mempunyai kontrak:

class Tool:
    name: str
    description: str
    schema: dict

    def execute(self, args) -> Result:
        ...

Misalnya:

file_read
├── path: string
└── start_line: optional[int]

atau:

shell
├── command: string
└── timeout: optional[int]
Kenapa ini fundamental?

Karena nantinya kamu bisa menambahkan:

GitTool
SearchTool
TestTool
BuildTool
BrowserTool
DatabaseTool
MCPTool

tanpa mengubah CoreAgent.

Jadi:

CoreAgent
    │
    └── ToolRegistry
           ├── FileReadTool
           ├── FileWriteTool
           ├── ShellTool
           ├── SearchTool
           └── ...

Ini dependency inversion yang jauh lebih sehat.

3. Retry jangan langsung dibuat terlalu pintar

Bagian ini:

No intelligent retry on transient errors
No exponential backoff

benar, tetapi saya tidak akan langsung membuat sistem retry yang sangat kompleks.

Mulai dari klasifikasi:

Error
 │
 ├── Permanent
 │      └── DON'T RETRY
 │
 ├── Transient
 │      └── RETRY
 │
 ├── Rate Limit
 │      └── BACKOFF / FALLBACK
 │
 └── Authentication
        └── DON'T RETRY

Contohnya:

if error.is_rate_limit:
    backoff()
    try_next_provider()

elif error.is_transient:
    backoff()
    retry()

elif error.is_authentication:
    fail()

else:
    ask_agent_or_user()

Kemudian baru tambahkan exponential backoff:

1s
 ↓
2s
 ↓
4s
 ↓
8s

dengan maximum retry limit.

Jangan sampai Klyro:

error
 ↓
retry
 ↓
error
 ↓
retry
 ↓
error
 ↓
retry
 ↓
...
4. Phase 2 adalah upgrade paling besar untuk kualitas Klyro

Menurut saya ini bagian paling menarik dari roadmap kamu.

Saat ini:

Project
 ↓
ambil banyak file
 ↓
masukkan context
 ↓
LLM

Target:

Project
 ↓
ProjectAnalyzer
 ↓
Project Index
 ├── files
 ├── symbols
 ├── imports
 ├── dependencies
 ├── entry points
 └── relationships
        ↓
Question
        ↓
Relevance Scoring
        ↓
Relevant Context
        ↓
LLM

Ini akan membuat Klyro jauh lebih efisien.

5. Jangan hanya membuat ProjectAnalyzer

Saya sarankan dipisah:

ProjectAnalyzer
├── StructureAnalyzer
├── SymbolIndexer
├── DependencyAnalyzer
└── EntryPointDetector

Misalnya project:

src/
├── main.py
├── auth/
│   ├── login.py
│   └── register.py
├── database/
│   └── db.py
└── utils/
    └── validation.py

Klyro bisa mengetahui:

main.py
 └── auth/login.py
       ├── database/db.py
       └── utils/validation.py

Kemudian user bertanya:

"Perbaiki login."

Tidak perlu:

main.py
login.py
register.py
db.py
validation.py
+ 195 file lainnya

Klyro cukup mengambil:

auth/login.py
database/db.py
utils/validation.py

plus file terkait lain jika diperlukan.

Ini akan mengurangi context noise secara signifikan.

6. Symbol Index adalah fitur yang sangat worth it

Misalnya Klyro menemukan:

def authenticate_user(...)

dan menyimpan:

Symbol:
authenticate_user

Type:
function

File:
src/auth/login.py

Line:
42

References:
src/routes/auth.py
src/tests/test_auth.py

Kemudian user mengatakan:

"Kenapa authenticate_user dipanggil dua kali?"

Klyro tidak perlu membaca seluruh project.

Dia bisa langsung:

search symbol
      ↓
authenticate_user
      ↓
references
      ↓
auth.py
test_auth.py

Ini mulai membuat Klyro terasa seperti coding agent sungguhan, bukan chatbot dengan akses filesystem.

7. Smart File Selection harus memakai scoring

Jangan hanya:

if filename contains keyword:
    include()

Buat relevance score.

Contoh konseptual:

Score(file) =

+ keyword relevance
+ symbol relevance
+ import relationship
+ directory relevance
+ dependency proximity
+ recently modified

Misalnya:

login.py        0.98
auth.py         0.91
database.py     0.76
user.py         0.63
homepage.py     0.08
README.md       0.02

Kemudian:

Top relevant files
        ↓
Context budget
        ↓
LLM

Ini jauh lebih bagus daripada fixed:

max 200 files
max 500K characters

Limit tersebut tetap berguna sebagai safety budget, tetapi bukan strategi utama pemilihan context.

8. Approval Gate saya taruh setelah Tool Registry

Saya sedikit mengubah roadmap kamu di sini.

Jangan menunggu semua Phase 2 selesai untuk membuat permission system.

Karena begitu Klyro punya generic:

file_write
shell
file_delete

maka permission layer harus ada.

Arsitekturnya:

Agent
 ↓
Tool Call
 ↓
Permission Manager
 ↓
┌───────────────┐
│ allowed?      │
└───────┬───────┘
        │
   ┌────┴────┐
   │         │
 YES         NO
   │         │
   ▼         ▼
Execute    Ask User

Contohnya:

Klyro wants to execute:

rm -rf ./build

[Allow] [Deny]

Sedangkan:

file_read

bisa saja langsung diizinkan.

Jadi nanti ada level:

READ
WRITE
DELETE
EXECUTE
NETWORK
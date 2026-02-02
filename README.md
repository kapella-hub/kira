# kira

Agentic CLI wrapper for [kiro-cli](https://kiro.dev) with persistent memory, skills, and team collaboration.

## Features

- **Smart Memory**: Cross-session context with auto-extraction, decay, and relevance scoring
- **Run Logs**: Automatic logging of all sessions with search and history
- **Skills System**: Reusable prompts and workflows
- **Team Context**: Shared project knowledge via git-tracked files
- **Interactive REPL**: Dynamic prompts, tab completion, quick toggles
- **Thinking Mode**: Multi-phase reasoning with self-critique

## Installation

**macOS/Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/kapella-hub/kira/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/kapella-hub/kira/main/install.ps1 | iex
```

**Update:**
```bash
kira update
```

**Requirements:**
- Python 3.12+
- [kiro-cli](https://kiro.dev) (for LLM interaction)

## Quick Start

```bash
# Interactive REPL (recommended)
kira

# One-shot prompt
kira chat "Explain this codebase"

# With thinking mode
kira chat -T "Design a REST API"

# Resume previous session
kira chat -r "Continue from before"
```

## Interactive REPL

Start the REPL with just `kira`:

```
Kira [B][TMC] >
```

The prompt shows:
- Model tier: `[F]`ast, `[S]`mart, `[B]`est
- Active modes: `[T]`hinking, `[A]`utonomous, `[M]`emory, `[C]`ontext

### Quick Commands

```bash
/help                  # Show all commands
/model opus            # Switch model (fast, smart, opus)
/memory on|off         # Toggle memory
/thinking on|off       # Toggle deep reasoning
/config                # Show all settings
/status                # System status
```

## Memory System

Kira remembers important information across sessions.

### Memory Types

- **Semantic**: Facts, definitions, concepts
- **Episodic**: Conversations, events, decisions
- **Procedural**: How-to, patterns, approaches

### CLI Commands

```bash
# Basic operations
kira memory list                    # List all memories
kira memory add "key" "content"     # Add memory
kira memory get "key"               # Get specific memory
kira memory search "query"          # Full-text search

# Filter by type
kira memory list --type procedural
kira memory add "api:auth" "OAuth2 flow" --type procedural

# View with decay info
kira memory list --decay
kira memory stats --decay

# Maintenance
kira memory cleanup --dry-run       # Preview cleanup
kira memory cleanup                 # Remove old low-importance memories
kira memory consolidate --dry-run   # Preview duplicate merging
kira memory consolidate             # Merge similar memories
```

### Auto-Extraction

Memories are automatically extracted from responses:

1. **Explicit markers**: `[REMEMBER:key] content`
2. **Pattern detection**: Decisions, solutions, important notes

### Decay & Relevance

- Importance decays 5% per week without access
- Memories are scored for relevance to current task
- Cleanup removes old, low-importance entries

## Team Context

Share project knowledge with your team via `.kira/context.md`:

```bash
# In REPL
/context init          # Analyze project
/context refresh       # Update analysis
/context note "text"   # Add team note
/context issue "bug"   # Record known issue
/context log           # Show change history
```

The context file is git-tracked, so team knowledge is shared automatically.

## Skills

Reusable prompts and workflows:

```bash
kira skills list                   # Available skills
kira skills show architect         # View skill details
kira chat -s architect "Design"    # Use skill

# Custom skills
kira skills add myskill -d "Description" --local
```

### Built-in Skills

- **architect**: Design software architecture
- **reviewer**: Thorough code review
- **researcher**: Investigate before recommending
- **coder**: Implement with best practices
- **debugger**: Systematic problem diagnosis

## Run Logs

Kira automatically logs all chat sessions and REPL interactions for history and debugging.

### CLI Commands

```bash
# View recent runs
kira logs list                    # List recent runs
kira logs list --mode repl        # Filter by mode (repl, chat, thinking, autonomous)
kira logs list -n 50              # Show more runs

# View run details
kira logs show 42                 # Show run #42
kira logs show 42 --full          # Include full prompts/responses
kira logs last                    # Show most recent run

# Search history
kira logs search "authentication" # Search prompts and responses

# Statistics
kira logs stats                   # Show log statistics

# Cleanup
kira logs clear --older-than 30   # Clear runs older than 30 days
kira logs clear --mode chat       # Clear only chat runs
```

### REPL Commands

```bash
/logs                  # Show recent runs
/logs stats            # Log statistics
/logs current          # Current session info
```

### Storage

Logs are stored at `~/.kira/data/runs.db` (SQLite).

## Configuration

### Quick Toggles (REPL)

```bash
/model opus           # claude-opus-4
/model fast           # claude-3-haiku
/memory off           # Disable memory
/thinking on          # Enable deep reasoning
/trust on             # Auto-approve tools
/timeout 600          # Set timeout
/config save          # Persist changes
```

### Config Files

User config (`~/.kira/config.yaml`):
```yaml
defaults:
  trust_all_tools: true

kira:
  model: claude-opus-4
  timeout: 1200

memory:
  enabled: true
  max_context_tokens: 2000
  min_importance: 3

thinking:
  enabled: true

personality:
  enabled: true
  name: Kira
```

Project config (`.kira/config.yaml`) overrides user config.

## How It Works

1. **Memory Injection**: Relevant memories prepended to prompt
2. **Context Loading**: Team knowledge from `.kira/context.md`
3. **Skill Activation**: Selected skill prompts included
4. **kiro-cli Execution**: Full prompt sent to kiro-cli
5. **Memory Extraction**: Responses scanned for learnable content

kiro-cli handles:
- LLM interaction
- Tool execution (file, shell, web)
- Extended thinking

## License

MIT

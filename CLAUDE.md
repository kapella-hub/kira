# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

kira is a CLI wrapper for kiro-cli that adds:
- **Persistent memory** across sessions (SQLite with FTS5)
- **Skills system** for reusable prompts/workflows (YAML files)
- **Session management** with memory injection
- **Thinking mode** for two-phase execution (analyze then execute)
- **Model selection** with aliases (fast/smart/best)
- **Agent spawning** for specialized task handling
- **Workflow orchestration** for multi-stage coding tasks

It delegates LLM interaction to kiro-cli using non-interactive mode (prompts via stdin).

## kiro-cli Integration

KiroClient invokes kiro-cli in non-interactive mode:
```bash
kiro-cli chat --no-interactive --wrap never --trust-all-tools [--model MODEL]
```

Key implementation details:
- **Prompts sent via stdin** (not command-line arguments)
- **Output streamed from stdout** with real-time filtering
- **ANSI codes and banners filtered** for clean output
- **Uses `--wrap never`** to disable line wrapping
- **Auto read/write access** to current working directory (trust_all_tools: true by default)

## Tech Stack

- Python 3.12+
- typer (CLI framework)
- rich (terminal output)
- pyyaml (skill files)
- SQLite with FTS5 (memory storage)

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run
kira                              # Interactive REPL
kira chat "your prompt"           # One-shot prompt
kira chat -s architect "Design"   # With skill
kira chat -m opus "Complex task"  # With model
kira chat -T "Plan and execute"   # Thinking mode
kira chat -W coding "Build API"   # Workflow

# Test
pytest

# Lint
ruff check src/
ruff format src/
```

## Architecture

```
src/kira/
├── cli/                    # CLI commands (typer)
│   ├── app.py              # Main entry point
│   └── commands/           # Subcommands: chat, memory, skills, config
├── core/
│   ├── kiro.py             # KiroClient subprocess wrapper
│   ├── session.py          # SessionManager with memory injection
│   ├── config.py           # Configuration loading
│   └── models.py           # Model aliases (fast/smart/best)
├── memory/
│   ├── store.py            # MemoryStore (SQLite + FTS5)
│   └── models.py           # Memory dataclass
├── skills/
│   ├── manager.py          # SkillManager
│   └── builtin/            # Built-in skill YAML files
├── thinking/               # Deep reasoning mode (7 phases)
│   ├── reasoning.py        # DeepReasoning (main reasoning engine)
│   ├── planner.py          # ThinkingPlanner (legacy two-phase)
│   ├── executor.py         # ThinkingExecutor (legacy execution)
│   └── models.py           # ThinkingResult, Verification, Complexity
├── agents/                 # Agent spawning system
│   ├── classifier.py       # TaskClassifier (keyword-based)
│   ├── registry.py         # AgentRegistry with built-in agents
│   ├── spawner.py          # AgentSpawner lifecycle
│   └── models.py           # TaskType, ClassifiedTask
└── workflows/              # Multi-stage workflow orchestration
    ├── models.py           # Workflow, Stage, StageResult
    ├── coding.py           # CODING_WORKFLOW definition
    ├── orchestrator.py     # WorkflowOrchestrator
    └── detector.py         # CodingTaskDetector
```

## Key Features

### Deep Reasoning Mode (`-T`)
Adaptive multi-phase reasoning with self-critique, loop-back, and verification:
```bash
kira chat -T "implement user authentication"
```

**7 Thinking Phases + Execution:**
1. **Understand** - Deep analysis of task, implicit requirements, constraints
2. **Explore** - Brainstorm 3-4 different approaches with pros/cons
3. **Analyze** - Evaluate approaches, identify issues and mitigations
4. **Plan** - Create detailed step-by-step execution plan
5. **Critique** - Self-critique the plan, find weaknesses and blind spots
6. **Refine** - Improve plan based on critique, increase confidence
7. **Verify** - Final validation against original requirements (NEW)
8. **Execute** - Run the refined plan with full context

**Advanced Features:**
- **Adaptive Phases**: Trivial tasks skip exploration/critique (UNDERSTAND → PLAN only)
- **Confidence Loop-back**: If critique confidence < 50%, loops back to EXPLORE
- **Phase-Specific Models**: Uses faster models for simple phases, best for critique/refine
- **Memory-Informed**: Pulls relevant past reasoning from memory
- **Streaming Output**: Shows each phase as it completes

**Output includes:**
- Task understanding with success criteria
- Multiple approaches evaluated
- Chosen approach with reasoning
- Detailed execution steps with verification
- Self-critique with confidence score
- Refined plan addressing weaknesses
- Final verification against requirements

### Model Selection
Use aliases or full model names:
```bash
kira run -M fast "quick question"    # claude-3-haiku
kira run -M smart "moderate task"    # claude-sonnet-4
kira run -M best "complex analysis"  # claude-opus-4
```

### Workflow Orchestration
Multi-stage workflows for coding tasks:
```bash
kira run -W coding "Build a user API"
kira run --auto-workflow "Implement authentication"
kira run -W coding --skip reviewer --skip docs "Quick fix"
```

**Coding workflow stages:**
1. architect - Design solution architecture
2. coder - Implement the solution
3. reviewer - Review implementation (optional)
4. docs - Update documentation (optional)

### Agent System
Task classification and specialized agent spawning:
- TaskClassifier identifies task type (CODING, ARCHITECTURE, DEBUGGING, etc.)
- AgentRegistry holds agent specs with skills and prompts
- AgentSpawner manages agent lifecycle

## Key Patterns

### Memory Injection
Session manager injects relevant memories into prompts before sending to kiro-cli:
```python
session = session_manager.start(memory_tags=["project"])
full_prompt = session_manager.build_prompt(user_prompt)
```

### Memory Extraction
Agent can output `[REMEMBER:key] content` markers which are automatically extracted and stored:
```python
saved = session_manager.save_memories(response)
```

### Project Memory (Team Sharing)
Project-specific knowledge is stored in `.kira/project-memory.yaml` and shared via git:
- Use `[PROJECT:key] content` markers to save project knowledge
- REPL commands: `/project`, `/project add`, `/project search`
- Automatically loaded when working in a project with `.kira/` directory
- Human-readable YAML format for easy review and merge

Example marker in agent output:
```
[PROJECT:api:auth] This project uses JWT tokens with refresh token rotation
```

### Skills
Skills are YAML files with name, description, and prompt. Loaded from:
1. `src/kira/skills/builtin/` (shipped with package)
2. `~/.kira/skills/` (user-defined)
3. `.kira/skills/` (project-local)

**Built-in skills:** architect, reviewer, researcher, coder, debugger, documenter

### Workflow Detection
CodingTaskDetector uses aggressive regex patterns to identify coding tasks:
- Strong patterns: `implement.*feature`, `create.*api`, `build.*endpoint`
- Context clues: function, class, module, api, database
- Confidence threshold: 0.6 (configurable)

## Configuration

User config: `~/.kira/config.yaml`
Project config: `.kira/agent.yaml`
User memory: `~/.kira/memory.db` (personal, not shared)
Project memory: `.kira/project-memory.yaml` (shared via git)
Project context: `.kira/context.md` (shared via git)

```yaml
# Example config
defaults:
  agent: orchestrator
  trust_all_tools: true  # Auto read/write in working directory

kiro:
  model: claude-sonnet-4
  timeout: 600

memory:
  enabled: true
  max_context_tokens: 2000
  min_importance: 3
  auto_extract: true

thinking:
  enabled: false
  planning_model: claude-3-haiku
  show_plan: true
  save_plans: true

autonomous:
  enabled: true              # Self-verification and auto-retry
  max_retries: 3             # Retry failures up to N times
  run_tests: true            # Run tests after code changes
  verification_enabled: true # Verify syntax/imports

workflow:
  auto_detect: true
  detection_threshold: 0.6
  interactive: true

agents:
  auto_spawn: false
  use_llm_classification: false
  default_agent: general

skills:
  - architect
  - researcher
```

## CLI Reference (Claude Code-like Interface)

```bash
# Interactive REPL (no arguments)
kira                              # Start interactive mode
kira -c                           # Resume previous conversation
kira -m opus                      # Interactive with specific model

# One-shot prompts
kira chat "explain this code"     # Send prompt, get response
kira chat -p "summarize this"     # Print-only (no follow-up)
kira chat -c "continue this"      # Continue previous conversation
kira chat -m opus "complex task"  # With specific model
kira chat -s architect "design"   # With skill
kira chat -T "plan this"          # Thinking mode (two-phase)
kira chat -W coding "build API"   # Run coding workflow
kira chat --auto-workflow "task"  # Auto-detect workflow

# Memory management
kira memory list
kira memory search "query"
kira memory add "key" "content"
kira memory delete "key"

# Skills management
kira skills list
kira skills show <name>
kira skills create <name>

# Configuration
kira config show
kira config set <key> <value>

# Status
kira status
kira version
```

## Interactive REPL Commands

When in interactive mode, you can use these commands:
- `/help` - Show help
- `/exit`, `/quit` - Exit REPL
- `/clear` - Clear conversation
- `/model` - Interactive model selection (shows numbered menu)
- `/model <name>` - Switch model directly (fast/smart/opus)
- `/skill <name>` - Activate a skill
- `/skills` - List available skills
- `/memory` - Show memory stats
- `/project` - Show project knowledge (shared via git)
- `/status` - Show system status

**Model Selection Example:**
```
> /model

Select Model

#   Model                  Tier     Description
1   ✓ Claude Sonnet 4      smart    Balanced performance (default)
2     Claude 3 Haiku       fast     Fastest, most cost-effective
3     Claude Opus 4        best     Most capable, best for complex tasks

Select model (1-3) or press Enter to cancel: 3
Model set to: Claude Opus 4
```

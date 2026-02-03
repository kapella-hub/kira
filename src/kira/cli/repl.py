"""Interactive REPL for kira (Claude Code-like interface)."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.box import ROUNDED
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

from ..context import ContextManager, ProjectAnalyzer, ChangeType
from ..core.config import Config
from ..core.client import KiraClient, KiraNotFoundError
from ..core.models import get_available_models, get_model_info, resolve_model
from ..core.session import SessionManager
from ..logs import RunLogStore
from ..logs.models import RunMode
from ..memory.store import MemoryStore
from ..skills.manager import SkillManager

if TYPE_CHECKING:
    pass

# Theme colors
COLORS = {
    "primary": "cyan",
    "secondary": "blue",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "muted": "dim white",
    "accent": "magenta",
}

# REPL prompt style for prompt_toolkit
PROMPT_STYLE = Style.from_dict({
    "prompt": "ansicyan bold",
    "model": "ansiblue",
    "mode": "ansimagenta",
    "rprompt": "ansigray",
})

# Available commands for completion
COMMANDS = [
    "/help", "/exit", "/quit", "/clear",
    "/model", "/config", "/skill", "/skills",
    "/memory", "/learned", "/project", "/thinking", "/autonomous", "/personality",
    "/verbose", "/trust", "/timeout",
    "/status", "/compact", "/history",
    "/context", "/logs", "/cd", "/view",
]

# Context subcommands for completion
CONTEXT_COMMANDS = ["refresh", "note", "log", "issue", "save", "show"]

# Memory subcommands for completion
MEMORY_COMMANDS = ["on", "off", "stats", "decay"]

# Project memory subcommands
PROJECT_COMMANDS = ["list", "add", "search"]

CONFIG_KEYS = [
    "model", "memory", "thinking", "autonomous",
    "personality", "personality.name", "verbose",
    "trust", "timeout", "retries", "save",
]

MODEL_ALIASES = ["fast", "smart", "opus", "haiku", "sonnet", "best"]


class REPLCompleter(Completer):
    """Custom completer for REPL commands."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()

        if not text or text == "/":
            # Complete commands
            for cmd in COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))

        elif text.startswith("/config "):
            # Complete config keys
            partial = words[-1] if len(words) > 1 else ""
            for key in CONFIG_KEYS:
                if key.startswith(partial):
                    yield Completion(key, start_position=-len(partial))

        elif text.startswith("/model "):
            # Complete model aliases
            partial = words[-1] if len(words) > 1 else ""
            for alias in MODEL_ALIASES:
                if alias.startswith(partial):
                    yield Completion(alias, start_position=-len(partial))

        elif text.startswith("/context "):
            # Complete context subcommands
            partial = words[-1] if len(words) > 1 else ""
            for subcmd in CONTEXT_COMMANDS:
                if subcmd.startswith(partial):
                    yield Completion(subcmd, start_position=-len(partial))

        elif text.startswith("/memory "):
            # Complete memory subcommands
            partial = words[-1] if len(words) > 1 else ""
            for subcmd in MEMORY_COMMANDS:
                if subcmd.startswith(partial):
                    yield Completion(subcmd, start_position=-len(partial))

        elif text.startswith("/"):
            # Complete partial commands
            for cmd in COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))


class InteractiveREPL:
    """Interactive REPL for conversational agent interaction."""

    def __init__(
        self,
        model: str | None = None,
        trust: bool = False,
        skills: list[str] | None = None,
        resume: bool = False,
        agent: str | None = None,
        no_memory: bool = False,
        verbose: bool = False,
    ):
        self.model = model
        self.trust = trust
        self.skills = skills or []
        self.resume = resume
        self.agent = agent
        self.no_memory = no_memory
        self.verbose = verbose

        self.console = Console()
        self.config = Config.load()
        self.running = False
        self.message_count = 0
        self.session_start = time.time()

        # Run logging
        self.log_store = RunLogStore()
        self.run_id: int | None = None

        # Project context manager
        self.context_manager = ContextManager(Path.cwd())

        # History file
        history_dir = Config.USER_CONFIG_DIR / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = history_dir / "repl_history"

    def _get_model_display(self) -> tuple[str, str]:
        """Get model display name and tier."""
        model = self.model or self.config.kira.model or "claude-sonnet-4"
        info = get_model_info(model)
        if info:
            return info.display_name, info.tier
        return model, "unknown"

    def _get_prompt_tokens(self) -> list:
        """Build dynamic prompt with model and mode indicators."""
        model_name, tier = self._get_model_display()

        # Build mode indicators
        modes = []
        if self.config.thinking.enabled:
            modes.append("T")  # Thinking
        if self.config.autonomous.enabled:
            modes.append("A")  # Autonomous
        if self.config.memory.enabled and not self.no_memory:
            modes.append("M")  # Memory
        if self.context_manager.exists():
            modes.append("C")  # Context

        # Tier indicator with color
        tier_short = {"fast": "F", "smart": "S", "best": "B"}.get(tier, "?")

        # Build prompt parts
        parts = []

        # Agent name if personality enabled
        if self.config.personality.enabled:
            parts.append(("class:prompt", f"{self.config.personality.name} "))

        # Model tier badge
        parts.append(("class:model", f"[{tier_short}]"))

        # Mode badges
        if modes:
            parts.append(("class:mode", f"[{''.join(modes)}]"))

        parts.append(("class:prompt", " > "))

        return parts

    def _check_for_updates(self) -> None:
        """Check for kiro-cli updates and show reminder if needed."""
        try:
            result = KiraClient.check_for_updates()
            if result and result.get("should_remind") and result.get("message"):
                self.console.print(f"[{COLORS['warning']}]! {result['message']}[/]")
                self.console.print()
        except Exception:
            pass  # Don't let update check errors break startup

    def _show_welcome(self) -> None:
        """Display welcome message with personality."""
        from .. import __version__
        from ..core.personality import get_personality

        model_name, tier = self._get_model_display()
        cwd = Path.cwd()
        personality = get_personality()

        # Build welcome panel content
        welcome_lines = []
        welcome_lines.append(f"[bold {COLORS['primary']}]{personality.format_greeting()}[/]")
        welcome_lines.append("")
        welcome_lines.append(f"[{COLORS['muted']}]Working in:[/] [bold]{cwd.name}/[/]")
        welcome_lines.append(f"[{COLORS['muted']}]Model:[/] [bold {COLORS['secondary']}]{model_name}[/] [{COLORS['muted']}]({tier})[/]")

        # Show active modes
        active_modes = []
        if self.config.thinking.enabled:
            active_modes.append(f"[{COLORS['accent']}]thinking[/]")
        if self.config.autonomous.enabled:
            active_modes.append(f"[{COLORS['accent']}]autonomous[/]")
        if self.context_manager.exists():
            active_modes.append(f"[{COLORS['success']}]context[/]")
        if self.config.memory.enabled and not self.no_memory:
            active_modes.append(f"[{COLORS['accent']}]memory[/]")

        if active_modes:
            welcome_lines.append(f"[{COLORS['muted']}]Modes:[/] {' '.join(active_modes)}")

        welcome_content = "\n".join(welcome_lines)

        # Create panel
        panel = Panel(
            welcome_content,
            title=f"[bold {COLORS['primary']}]kira[/] [dim]v{__version__}[/]",
            subtitle=f"[{COLORS['muted']}]/help for commands[/]",
            box=ROUNDED,
            padding=(1, 2),
            border_style=COLORS['primary'],
        )

        self.console.print()
        self.console.print(panel)
        self.console.print()

    def _show_help(self) -> None:
        """Display help in a formatted panel."""
        # Basic commands table
        cmd_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        cmd_table.add_column("Command", style=f"bold {COLORS['primary']}")
        cmd_table.add_column("Description", style=COLORS['muted'])

        commands = [
            ("/help", "Show this help"),
            ("/exit", "Exit the REPL"),
            ("/clear", "Clear screen"),
            ("/cd <path>", "Change working directory"),
            ("/view <file>[:lines]", "View file with syntax highlighting"),
            ("/status", "Show system status"),
            ("/config", "Show all settings"),
            ("/config save", "Save settings to disk"),
        ]

        for cmd, desc in commands:
            cmd_table.add_row(cmd, desc)

        # Quick settings table
        settings_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        settings_table.add_column("Command", style=f"bold {COLORS['secondary']}")
        settings_table.add_column("Example", style=COLORS['muted'])

        settings = [
            ("/model <name>", "fast, smart, opus"),
            ("/thinking on|off", "Toggle deep reasoning"),
            ("/autonomous on|off", "Toggle self-correction"),
            ("/personality on|off", "Toggle personality"),
            ("/verbose on|off", "Toggle detailed output"),
            ("/trust on|off", "Toggle auto-approve tools"),
            ("/timeout <secs>", "Set command timeout"),
        ]

        for cmd, example in settings:
            settings_table.add_row(cmd, example)

        # Context table (team collaboration)
        context_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        context_table.add_column("Command", style=f"bold {COLORS['success']}")
        context_table.add_column("Description", style=COLORS['muted'])

        context_cmds = [
            ("/context", "Show project context"),
            ("/context init", "Analyze project & create context"),
            ("/context refresh", "Re-analyze and update"),
            ("/context note <text>", "Add a note for team"),
            ("/context issue <text>", "Record a known issue"),
            ("/context log", "Show change history"),
        ]

        for cmd, desc in context_cmds:
            context_table.add_row(cmd, desc)

        # Memory table
        memory_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        memory_table.add_column("Command", style=f"bold {COLORS['warning']}")
        memory_table.add_column("Description", style=COLORS['muted'])

        memory_cmds = [
            ("/memory", "Show memory stats"),
            ("/memory stats", "Detailed stats by type/source"),
            ("/memory decay", "Show decay report"),
            ("/learned", "Show recently auto-learned memories"),
            ("/memory on|off", "Toggle memory"),
            ("/project", "Show project knowledge (shared via git)"),
            ("/project add <key> <content>", "Add project memory"),
            ("/project search <query>", "Search project memories"),
        ]

        for cmd, desc in memory_cmds:
            memory_table.add_row(cmd, desc)

        # Skills table
        skills_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        skills_table.add_column("Command", style=f"bold {COLORS['accent']}")
        skills_table.add_column("Description", style=COLORS['muted'])

        skills_cmds = [
            ("/skills", "List available skills"),
            ("/skill <name>", "Activate a skill"),
        ]

        for cmd, desc in skills_cmds:
            skills_table.add_row(cmd, desc)

        # Logs table
        logs_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        logs_table.add_column("Command", style=f"bold {COLORS['muted']}")
        logs_table.add_column("Description", style=COLORS['muted'])

        logs_cmds = [
            ("/logs", "Show recent runs"),
            ("/logs stats", "Run log statistics"),
            ("/logs current", "Current session info"),
        ]

        for cmd, desc in logs_cmds:
            logs_table.add_row(cmd, desc)

        # Shortcuts
        shortcuts = Text()
        shortcuts.append("Tab", style=f"bold {COLORS['primary']}")
        shortcuts.append(" autocomplete  ", style=COLORS['muted'])
        shortcuts.append("Up/Down", style=f"bold {COLORS['primary']}")
        shortcuts.append(" history  ", style=COLORS['muted'])
        shortcuts.append("Ctrl+C", style=f"bold {COLORS['primary']}")
        shortcuts.append(" cancel  ", style=COLORS['muted'])
        shortcuts.append("Ctrl+D", style=f"bold {COLORS['primary']}")
        shortcuts.append(" exit", style=COLORS['muted'])

        # Combine into panel
        content = Group(
            Text("Commands", style=f"bold {COLORS['primary']}"),
            cmd_table,
            Text(""),
            Text("Quick Settings", style=f"bold {COLORS['secondary']}"),
            settings_table,
            Text(""),
            Text("Memory (persistent learning)", style=f"bold {COLORS['warning']}"),
            memory_table,
            Text(""),
            Text("Run Logs (history)", style=f"bold {COLORS['muted']}"),
            logs_table,
            Text(""),
            Text("Team Context (shared via git)", style=f"bold {COLORS['success']}"),
            context_table,
            Text(""),
            Text("Skills", style=f"bold {COLORS['accent']}"),
            skills_table,
            Text(""),
            Text("Keyboard", style=f"bold {COLORS['primary']}"),
            shortcuts,
        )

        panel = Panel(
            content,
            title=f"[bold]Help[/]",
            box=ROUNDED,
            padding=(1, 2),
            border_style=COLORS['muted'],
        )

        self.console.print(panel)

    def _handle_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns True if should continue REPL."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command in ("/exit", "/quit"):
            self._show_goodbye()
            return False

        elif command == "/help":
            self._show_help()

        elif command == "/clear":
            self.console.clear()
            self._print_status_bar()

        elif command == "/model":
            if args:
                self._set_model(args)
            else:
                self._select_model_interactive()

        elif command == "/skill":
            self._handle_skill(args)

        elif command == "/skills":
            self._show_skills()

        elif command == "/memory":
            self._handle_memory(args)

        elif command == "/learned":
            self._show_learned()

        elif command == "/status":
            self._show_status()

        elif command == "/config":
            self._handle_config(args)

        elif command == "/thinking":
            self._quick_toggle("thinking", args)

        elif command == "/autonomous":
            self._quick_toggle("autonomous", args)

        elif command == "/personality":
            self._quick_toggle("personality", args)

        elif command == "/verbose":
            self._quick_toggle("verbose", args)

        elif command == "/trust":
            self._quick_toggle("trust", args)

        elif command == "/timeout":
            if args:
                self._set_config("timeout", args)
            else:
                self.console.print(f"[{COLORS['muted']}]Timeout: {self.config.kira.timeout}s[/]")
                self.console.print(f"[{COLORS['muted']}]Usage: /timeout <seconds>[/]")

        elif command == "/compact":
            self.verbose = not self.verbose
            status = "off" if self.verbose else "on"
            self._print_success(f"Compact mode: {status}")

        elif command == "/history":
            self._show_history()

        elif command == "/context":
            self._handle_context(args)

        elif command == "/logs":
            self._show_logs(args)

        elif command == "/cd":
            self._change_directory(args)

        elif command == "/view":
            self._view_file(args)

        elif command == "/project":
            self._handle_project(args)

        else:
            self._print_warning(f"Unknown command: {command}")
            self.console.print(f"[{COLORS['muted']}]Type /help for available commands[/]")

        return True

    def _quick_toggle(self, key: str, args: str) -> None:
        """Handle quick toggle commands like /memory on, /thinking off."""
        if not args:
            # Show current value and usage
            current = self._get_toggle_value(key)
            status = f"[{COLORS['success']}]on[/]" if current else f"[{COLORS['error']}]off[/]"
            self.console.print(f"[{COLORS['primary']}]{key.capitalize()}:[/] {status}")
            self.console.print(f"[{COLORS['muted']}]Usage: /{key} on|off[/]")
            return

        # Toggle or set value
        if args.lower() in ("toggle", "t"):
            current = self._get_toggle_value(key)
            self._set_config(key, "off" if current else "on")
        else:
            self._set_config(key, args)

    def _get_toggle_value(self, key: str) -> bool:
        """Get current value of a toggle setting."""
        if key == "memory":
            return not self.no_memory and self.config.memory.enabled
        elif key == "thinking":
            return self.config.thinking.enabled
        elif key == "autonomous":
            return self.config.autonomous.enabled
        elif key == "personality":
            return self.config.personality.enabled
        elif key == "verbose":
            return self.verbose
        elif key == "trust":
            return self.trust or self.config.kira.trust_all_tools
        return False

    def _set_model(self, value: str) -> None:
        """Set the model."""
        resolved = resolve_model(value)
        if resolved:
            self.model = resolved
            self.config.kira.model = resolved
            info = get_model_info(resolved)
            display = info.display_name if info else resolved
            self._print_success(f"Model: {display}")
        else:
            self.model = value
            self.config.kira.model = value
            self._print_success(f"Model: {value}")

    def _handle_skill(self, args: str) -> None:
        """Handle /skill command."""
        if args:
            self.skills.append(args)
            self._print_success(f"Activated: {args}")
        else:
            if self.skills:
                skills_str = ", ".join(self.skills)
                self.console.print(f"[{COLORS['primary']}]Active skills:[/] {skills_str}")
            else:
                self.console.print(f"[{COLORS['muted']}]No active skills[/]")

    def _show_skills(self) -> None:
        """Show available skills."""
        manager = SkillManager()
        skills_list = manager.list_all()

        if not skills_list:
            self.console.print(f"[{COLORS['muted']}]No skills available[/]")
            return

        table = Table(show_header=True, header_style=f"bold {COLORS['primary']}", box=ROUNDED)
        table.add_column("Skill", style="bold")
        table.add_column("Description", style=COLORS['muted'])

        for skill in skills_list:
            table.add_row(skill.name, skill.description)

        self.console.print(table)

    def _handle_memory(self, args: str) -> None:
        """Handle /memory command and subcommands."""
        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""

        if not subcmd:
            # Show basic stats
            self._show_memory_stats()
        elif subcmd in ("on", "off"):
            # Toggle memory
            self._quick_toggle("memory", subcmd)
        elif subcmd == "stats":
            # Show detailed stats
            self._show_memory_stats(detailed=True)
        elif subcmd == "decay":
            # Show decay report
            self._show_memory_decay()
        else:
            self._print_warning(f"Unknown memory command: {subcmd}")
            self.console.print(f"[{COLORS['muted']}]Available: on, off, stats, decay[/]")
            self.console.print(f"[{COLORS['muted']}]CLI: kira memory list, kira memory cleanup, kira memory consolidate[/]")

    def _show_memory_stats(self, detailed: bool = False) -> None:
        """Show memory statistics."""
        store = MemoryStore()
        stats = store.get_stats()

        status = f"[{COLORS['success']}]enabled[/]" if not self.no_memory else f"[{COLORS['error']}]disabled[/]"
        self.console.print(f"[{COLORS['primary']}]Memory:[/] {status}")
        self.console.print(f"[{COLORS['muted']}]Total entries:[/] {stats['total']}")

        if stats['total'] == 0:
            return

        if detailed or stats['total'] > 0:
            # Show by type
            if stats.get('by_type'):
                type_parts = []
                for mtype, count in stats['by_type'].items():
                    type_parts.append(f"{mtype[:4]}: {count}")
                self.console.print(f"[{COLORS['muted']}]By type:[/] {', '.join(type_parts)}")

            # Show by source
            if stats.get('by_source'):
                source_parts = []
                for source, count in stats['by_source'].items():
                    source_parts.append(f"{source}: {count}")
                self.console.print(f"[{COLORS['muted']}]By source:[/] {', '.join(source_parts)}")

            if detailed:
                # Show average access count
                self.console.print(f"[{COLORS['muted']}]Avg access count:[/] {stats.get('avg_access_count', 0):.1f}")

                # Show importance distribution
                if stats.get('by_importance'):
                    imp_parts = []
                    for imp, count in sorted(stats['by_importance'].items(), reverse=True):
                        if count > 0:
                            imp_parts.append(f"{imp}: {count}")
                    if imp_parts:
                        self.console.print(f"[{COLORS['muted']}]By importance:[/] {', '.join(imp_parts[:5])}")

        self.console.print()
        self.console.print(f"[{COLORS['muted']}]Commands: /memory on|off|stats|decay | /learned[/]")
        self.console.print(f"[{COLORS['muted']}]CLI: kira memory list, kira memory cleanup --dry-run[/]")

    def _show_learned(self) -> None:
        """Show recently auto-learned memories."""
        from ..memory.models import MemorySource

        store = MemoryStore()
        # Get auto-extracted memories
        memories = store.list_all(source=MemorySource.EXTRACTED, limit=10)

        if not memories:
            self.console.print(f"[{COLORS['muted']}]No auto-learned memories yet[/]")
            self.console.print(f"[{COLORS['muted']}]Kira learns from your conversations automatically[/]")
            return

        self.console.print(f"[{COLORS['primary']}]Recently Learned[/]\n")

        for mem in memories:
            # Truncate content for display
            content = mem.content[:80] + "..." if len(mem.content) > 80 else mem.content
            type_icon = {"semantic": "💡", "episodic": "📝", "procedural": "⚙️"}.get(mem.memory_type.value, "•")
            self.console.print(f"  {type_icon} [{COLORS['muted']}]{mem.key}[/]")
            self.console.print(f"     {content}")
            self.console.print()

        self.console.print(f"[{COLORS['muted']}]Total auto-learned: {len(memories)} | CLI: kira memory list[/]")

    def _show_memory_decay(self) -> None:
        """Show memory decay report."""
        from ..memory.maintenance import MemoryMaintenance

        store = MemoryStore()
        maintenance = MemoryMaintenance(store)
        report = maintenance.get_decay_report(limit=10)

        if not report:
            self.console.print(f"[{COLORS['muted']}]No memories to analyze[/]")
            return

        self.console.print(f"[{COLORS['primary']}]Memory Decay Report[/]")
        self.console.print()

        table = Table(show_header=True, header_style=f"bold {COLORS['primary']}", box=ROUNDED)
        table.add_column("Key", style="bold", max_width=25)
        table.add_column("Orig", justify="right", width=5)
        table.add_column("Now", justify="right", width=5)
        table.add_column("Decay", justify="right", width=7)
        table.add_column("Age", justify="right", width=6)

        for item in report:
            if item['decay_percentage'] > 0:
                decay_str = f"{item['decay_percentage']:.0f}%"
                decay_style = COLORS['warning'] if item['decay_percentage'] > 20 else COLORS['muted']
                table.add_row(
                    item['key'][:25],
                    str(item['original_importance']),
                    f"{item['decayed_importance']:.1f}",
                    f"[{decay_style}]{decay_str}[/]",
                    f"{item['age_days']}d",
                )

        self.console.print(table)
        self.console.print()
        self.console.print(f"[{COLORS['muted']}]Run 'kira memory cleanup --dry-run' to preview cleanup[/]")

    def _handle_project(self, args: str) -> None:
        """Handle /project command for project-local shared memory."""
        from ..memory.project_store import ProjectMemoryStore

        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower() if parts else ""
        subargs = parts[1] if len(parts) > 1 else ""

        project_memory = ProjectMemoryStore(Path.cwd())

        if not subcommand or subcommand == "list":
            self._show_project_memories(project_memory)
        elif subcommand == "add":
            self._add_project_memory(project_memory, subargs)
        elif subcommand == "search":
            self._search_project_memories(project_memory, subargs)
        elif subcommand == "init":
            self._init_project_memory(project_memory)
        else:
            self._print_warning(f"Unknown subcommand: {subcommand}")
            self.console.print(f"[{COLORS['muted']}]Usage: /project [list|add|search|init][/]")

    def _show_project_memories(self, store) -> None:
        """Show project memories (shared with team)."""
        if not store.exists():
            self.console.print(f"[{COLORS['muted']}]No project memory file found[/]")
            self.console.print(f"[{COLORS['muted']}]Use '/project init' to create .kira/project-memory.yaml[/]")
            self.console.print()
            self.console.print(f"[{COLORS['primary']}]Project memories are shared with your team via git.[/]")
            self.console.print(f"[{COLORS['muted']}]Mark learnings with [PROJECT:key] to save them.[/]")
            return

        memories = store.list_all()

        if not memories:
            self.console.print(f"[{COLORS['muted']}]No project memories yet[/]")
            self.console.print(f"[{COLORS['muted']}]Mark learnings with [PROJECT:key] to save them[/]")
            return

        self.console.print(f"[{COLORS['primary']}]Project Knowledge[/] (shared via git)")
        self.console.print()

        table = Table(show_header=True, header_style=f"bold {COLORS['primary']}", box=ROUNDED)
        table.add_column("Key", style="bold", max_width=25)
        table.add_column("Content", max_width=50)
        table.add_column("Imp", justify="right", width=4)
        table.add_column("Tags", max_width=20)

        for mem in memories[:15]:
            content = mem.content[:47] + "..." if len(mem.content) > 50 else mem.content
            tags = ", ".join(mem.tags[:3]) if mem.tags else "-"
            table.add_row(
                mem.key[:25],
                content,
                str(mem.importance),
                tags,
            )

        self.console.print(table)
        self.console.print()
        self.console.print(f"[{COLORS['muted']}]File: .kira/project-memory.yaml (commit to share)[/]")

    def _add_project_memory(self, store, args: str) -> None:
        """Add a project memory manually."""
        if not args:
            self.console.print(f"[{COLORS['muted']}]Usage: /project add <key> <content>[/]")
            self.console.print(f"[{COLORS['muted']}]Example: /project add auth:pattern We use JWT tokens for auth[/]")
            return

        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            self._print_warning("Both key and content are required")
            return

        key, content = parts
        store.store(key=key, content=content, importance=6)
        self._print_success(f"Added project memory: {key}")
        self.console.print(f"[{COLORS['muted']}]Commit .kira/project-memory.yaml to share[/]")

    def _search_project_memories(self, store, query: str) -> None:
        """Search project memories."""
        if not query:
            self.console.print(f"[{COLORS['muted']}]Usage: /project search <query>[/]")
            return

        if not store.exists():
            self.console.print(f"[{COLORS['muted']}]No project memory file found[/]")
            return

        results = store.search(query, limit=10)

        if not results:
            self.console.print(f"[{COLORS['muted']}]No matches found[/]")
            return

        self.console.print(f"[{COLORS['primary']}]Search Results:[/] {query}")
        self.console.print()

        for mem in results:
            content = mem.content[:60] + "..." if len(mem.content) > 60 else mem.content
            self.console.print(f"  [{COLORS['secondary']}]{mem.key}[/]")
            self.console.print(f"    {content}")
            self.console.print()

    def _init_project_memory(self, store) -> None:
        """Initialize project memory file."""
        if store.exists():
            self.console.print(f"[{COLORS['muted']}]Project memory already exists[/]")
            return

        store.ensure_dir()
        store.save()  # Create empty file
        self._print_success("Created .kira/project-memory.yaml")
        self.console.print(f"[{COLORS['muted']}]Add to git: git add .kira/project-memory.yaml[/]")

    def _handle_config(self, args: str) -> None:
        """Handle /config command."""
        parts = args.split(maxsplit=1)

        if not args:
            self._show_config()
            return

        key = parts[0].lower()
        value = parts[1] if len(parts) > 1 else ""

        if key == "save":
            self._save_config()
            return

        if not value:
            self._print_warning(f"Usage: /config {key} <value>")
            return

        self._set_config(key, value)

    def _show_config(self) -> None:
        """Display current configuration."""
        table = Table(
            show_header=True,
            header_style=f"bold {COLORS['primary']}",
            box=ROUNDED,
            padding=(0, 1),
        )
        table.add_column("Setting", style="bold")
        table.add_column("Value")
        table.add_column("Toggle", style=COLORS['muted'])

        def status(enabled: bool) -> str:
            return f"[{COLORS['success']}]on[/]" if enabled else f"[{COLORS['error']}]off[/]"

        model_name, tier = self._get_model_display()

        rows = [
            ("model", f"[{COLORS['secondary']}]{model_name}[/]", "/model <name>"),
            ("memory", status(not self.no_memory and self.config.memory.enabled), "/memory on|off"),
            ("thinking", status(self.config.thinking.enabled), "/thinking on|off"),
            ("autonomous", status(self.config.autonomous.enabled), "/autonomous on|off"),
            ("personality", status(self.config.personality.enabled), f"/personality on|off"),
            ("verbose", status(self.verbose), "/verbose on|off"),
            ("trust", status(self.trust or self.config.kira.trust_all_tools), "/trust on|off"),
            ("timeout", f"{self.config.kira.timeout}s", "/timeout <secs>"),
        ]

        for row in rows:
            table.add_row(*row)

        self.console.print(table)
        self.console.print()
        self.console.print(f"[{COLORS['muted']}]Quick toggles: /memory off, /thinking on, /model opus[/]")
        self.console.print(f"[{COLORS['muted']}]Save changes:  /config save[/]")

    def _set_config(self, key: str, value: str) -> None:
        """Set a configuration value."""
        def parse_bool(v: str) -> bool:
            return v.lower() in ("true", "1", "yes", "on")

        def parse_int(v: str) -> int | None:
            try:
                return int(v)
            except ValueError:
                return None

        key = key.lower()

        if key == "model":
            self._set_model(value)

        elif key == "memory":
            enabled = parse_bool(value)
            self.no_memory = not enabled
            self.config.memory.enabled = enabled
            self._print_success(f"Memory: {'enabled' if enabled else 'disabled'}")

        elif key == "thinking":
            enabled = parse_bool(value)
            self.config.thinking.enabled = enabled
            self._print_success(f"Thinking mode: {'enabled' if enabled else 'disabled'}")

        elif key == "autonomous":
            enabled = parse_bool(value)
            self.config.autonomous.enabled = enabled
            self._print_success(f"Autonomous mode: {'enabled' if enabled else 'disabled'}")

        elif key == "personality":
            enabled = parse_bool(value)
            self.config.personality.enabled = enabled
            self._print_success(f"Personality: {'enabled' if enabled else 'disabled'}")

        elif key == "personality.name":
            self.config.personality.name = value
            self._print_success(f"Agent name: {value}")

        elif key == "verbose":
            self.verbose = parse_bool(value)
            self._print_success(f"Verbose: {'enabled' if self.verbose else 'disabled'}")

        elif key == "trust":
            enabled = parse_bool(value)
            self.trust = enabled
            self.config.kira.trust_all_tools = enabled
            self._print_success(f"Trust all tools: {'enabled' if enabled else 'disabled'}")

        elif key == "timeout":
            timeout = parse_int(value)
            if timeout and timeout > 0:
                self.config.kira.timeout = timeout
                self._print_success(f"Timeout: {timeout}s")
            else:
                self._print_error("Invalid timeout value")

        elif key in ("retries", "autonomous.retries"):
            retries = parse_int(value)
            if retries is not None and retries >= 0:
                self.config.autonomous.max_retries = retries
                self._print_success(f"Max retries: {retries}")
            else:
                self._print_error("Invalid retries value")

        else:
            self._print_warning(f"Unknown key: {key}")

    def _save_config(self) -> None:
        """Save current configuration to user config file."""
        try:
            self.config.save_user_config()
            self._print_success(f"Saved to {Config.USER_CONFIG_FILE}")
        except Exception as e:
            self._print_error(f"Failed to save: {e}")

    def _select_model_interactive(self) -> None:
        """Show interactive model selection menu."""
        models = get_available_models()
        current = self.model or self.config.kira.model or "claude-sonnet-4"

        table = Table(
            show_header=True,
            header_style=f"bold {COLORS['primary']}",
            box=ROUNDED,
        )
        table.add_column("#", style="dim", width=3, justify="center")
        table.add_column("Model")
        table.add_column("Tier", style=COLORS['secondary'])
        table.add_column("Description", style=COLORS['muted'])

        for i, model in enumerate(models, 1):
            marker = f"[{COLORS['success']}]>[/]" if model.name == current else " "
            table.add_row(
                str(i),
                f"{marker} {model.display_name}",
                model.tier,
                model.description,
            )

        self.console.print(table)

        try:
            choice = input(f"\n[{COLORS['muted']}]Select (1-{len(models)}) or Enter to cancel:[/] ").strip()
            if not choice:
                return

            idx = int(choice) - 1
            if 0 <= idx < len(models):
                selected = models[idx]
                self.model = selected.name
                self._print_success(f"Model: {selected.display_name}")
            else:
                self._print_warning("Invalid selection")
        except (ValueError, KeyboardInterrupt):
            pass

    def _show_status(self) -> None:
        """Show system status."""
        table = Table(show_header=False, box=ROUNDED, padding=(0, 1))
        table.add_column("Component", style="bold")
        table.add_column("Status")

        # kiro-cli with version age
        if KiraClient.is_available():
            version = KiraClient.get_version() or "available"
            update_info = KiraClient.check_for_updates()
            if update_info and update_info.get("age_days"):
                age = update_info["age_days"]
                if age > 14:
                    table.add_row("kiro-cli", f"[{COLORS['warning']}]![/] {version} ({age}d old)")
                else:
                    table.add_row("kiro-cli", f"[{COLORS['success']}]✓[/] {version} ({age}d)")
            else:
                table.add_row("kiro-cli", f"[{COLORS['success']}]✓[/] {version}")
        else:
            table.add_row("kiro-cli", f"[{COLORS['error']}]✗[/] not found")

        # Memory
        try:
            store = MemoryStore()
            count = store.count()
            table.add_row("Memory", f"[{COLORS['success']}]✓[/] {count} entries")
        except Exception as e:
            table.add_row("Memory", f"[{COLORS['error']}]✗[/] {e}")

        # Model
        model_name, tier = self._get_model_display()
        table.add_row("Model", f"{model_name} ({tier})")

        # Project context
        if self.context_manager.exists():
            ctx = self.context_manager.context
            changes = len(ctx.changelog)
            table.add_row("Context", f"[{COLORS['success']}]✓[/] {changes} changes tracked")
        else:
            table.add_row("Context", f"[{COLORS['muted']}]not initialized[/]")

        # Session stats
        elapsed = int(time.time() - self.session_start)
        mins, secs = divmod(elapsed, 60)
        table.add_row("Session", f"{self.message_count} messages, {mins}m {secs}s")

        self.console.print(table)

    def _show_history(self) -> None:
        """Show recent command history."""
        self.console.print(f"[{COLORS['muted']}]Recent history is available via up/down arrows[/]")

    def _handle_context(self, args: str) -> None:
        """Handle /context command and subcommands."""
        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""
        subargs = parts[1] if len(parts) > 1 else ""

        if not subcmd or subcmd == "show":
            self._show_context()
        elif subcmd == "refresh":
            self._refresh_context()
        elif subcmd == "note":
            self._add_context_note(subargs)
        elif subcmd == "log":
            self._show_context_log()
        elif subcmd == "issue":
            self._add_context_issue(subargs)
        elif subcmd == "save":
            self._save_context()
        elif subcmd == "init":
            self._init_context()
        else:
            self._print_warning(f"Unknown context command: {subcmd}")
            self.console.print(f"[{COLORS['muted']}]Available: show, refresh, note, log, issue, save, init[/]")

    def _show_context(self) -> None:
        """Display current project context."""
        if not self.context_manager.exists():
            self.console.print(f"[{COLORS['warning']}]No project context found.[/]")
            self.console.print(f"[{COLORS['muted']}]Run /context init to analyze this project.[/]")
            return

        ctx = self.context_manager.context

        # Build display
        lines = []
        lines.append(f"[bold {COLORS['primary']}]Project: {ctx.name or self.context_manager.project_dir.name}[/]")

        if ctx.last_updated:
            lines.append(f"[{COLORS['muted']}]Updated: {ctx.last_updated.strftime('%Y-%m-%d %H:%M')} by @{ctx.last_updated_by}[/]")

        lines.append("")

        if ctx.overview:
            lines.append(f"[bold]Overview[/]")
            lines.append(ctx.overview[:300] + ("..." if len(ctx.overview) > 300 else ""))
            lines.append("")

        if ctx.tech_stack.languages or ctx.tech_stack.frameworks:
            lines.append(f"[bold]Tech Stack[/]")
            if ctx.tech_stack.languages:
                lines.append(f"  Languages: {', '.join(ctx.tech_stack.languages)}")
            if ctx.tech_stack.frameworks:
                lines.append(f"  Frameworks: {', '.join(ctx.tech_stack.frameworks)}")
            lines.append("")

        # Recent changes
        recent = ctx.get_recent_changes(3)
        if recent:
            lines.append(f"[bold]Recent Changes[/]")
            for change in recent:
                date_str = change.date.strftime("%Y-%m-%d")
                lines.append(f"  [{date_str}] {change.summary} (@{change.author})")
            lines.append("")

        # Known issues
        if ctx.known_issues:
            lines.append(f"[bold]Known Issues[/]")
            for issue in ctx.known_issues[:3]:
                lines.append(f"  [{issue.severity}] {issue.description}")
            lines.append("")

        panel = Panel(
            "\n".join(lines),
            title="[bold]Project Context[/]",
            subtitle=f"[{COLORS['muted']}]/context refresh to update[/]",
            box=ROUNDED,
            padding=(1, 2),
            border_style=COLORS['primary'],
        )
        self.console.print(panel)

    def _refresh_context(self) -> None:
        """Analyze project and update context."""
        self.console.print(f"[{COLORS['muted']}]Analyzing project...[/]")

        with self.console.status("[bold cyan]Scanning codebase..."):
            analyzer = ProjectAnalyzer(self.context_manager.project_dir)
            new_context = analyzer.analyze_to_context()

            # Preserve existing changelog and notes if any
            if self.context_manager.exists():
                old_ctx = self.context_manager.context
                new_context.changelog = old_ctx.changelog
                new_context.notes = old_ctx.notes
                new_context.known_issues = old_ctx.known_issues

            self.context_manager.save(new_context)

        self._print_success("Project context updated")
        self.console.print(f"[{COLORS['muted']}]Found: {', '.join(new_context.tech_stack.languages[:3])}[/]")
        self.console.print(f"[{COLORS['muted']}]File: {self.context_manager.context_path}[/]")

    def _add_context_note(self, note: str) -> None:
        """Add a note to project context."""
        if not note:
            self._print_warning("Usage: /context note <your note>")
            return

        if not self.context_manager.exists():
            self._print_warning("No context file. Run /context init first.")
            return

        self.context_manager.add_note(note)
        self._print_success("Note added to project context")

    def _show_context_log(self) -> None:
        """Show recent changes from context."""
        if not self.context_manager.exists():
            self._print_warning("No project context found.")
            return

        ctx = self.context_manager.context
        recent = ctx.get_recent_changes(10)

        if not recent:
            self.console.print(f"[{COLORS['muted']}]No changes recorded yet.[/]")
            return

        table = Table(
            show_header=True,
            header_style=f"bold {COLORS['primary']}",
            box=ROUNDED,
        )
        table.add_column("Date", style="dim", width=12)
        table.add_column("Author", width=12)
        table.add_column("Type", width=10)
        table.add_column("Summary")

        for change in recent:
            date_str = change.date.strftime("%Y-%m-%d")
            table.add_row(
                date_str,
                f"@{change.author}",
                change.change_type.value,
                change.summary[:50] + ("..." if len(change.summary) > 50 else ""),
            )

        self.console.print(table)

    def _add_context_issue(self, issue: str) -> None:
        """Add a known issue to context."""
        if not issue:
            self._print_warning("Usage: /context issue <description>")
            return

        if not self.context_manager.exists():
            self._print_warning("No context file. Run /context init first.")
            return

        self.context_manager.add_issue(issue)
        self._print_success("Issue added to project context")

    def _save_context(self) -> None:
        """Explicitly save context file."""
        if not self.context_manager.exists():
            self._print_warning("No context to save. Run /context init first.")
            return

        self.context_manager.save()
        self._print_success(f"Context saved to {self.context_manager.context_path}")

    def _init_context(self) -> None:
        """Initialize project context."""
        if self.context_manager.exists():
            self.console.print(f"[{COLORS['warning']}]Context already exists. Use /context refresh to update.[/]")
            return

        self._refresh_context()

    def _change_directory(self, args: str) -> None:
        """Change the working directory."""
        import os

        if not args:
            # Show current directory
            self.console.print(f"[{COLORS['primary']}]Working directory:[/] {Path.cwd()}")
            self.console.print(f"[{COLORS['muted']}]Usage: /cd <path>[/]")
            return

        # Expand user and resolve path
        new_path = Path(args).expanduser()
        if not new_path.is_absolute():
            new_path = Path.cwd() / new_path
        new_path = new_path.resolve()

        if not new_path.exists():
            self._print_error(f"Directory not found: {new_path}")
            return

        if not new_path.is_dir():
            self._print_error(f"Not a directory: {new_path}")
            return

        # Change directory
        os.chdir(new_path)
        self.context_manager = ContextManager(new_path)

        self._print_success(f"Changed to: {new_path}")

        # Check for project context
        if self.context_manager.exists():
            self.console.print(f"[{COLORS['muted']}]Found project context[/]")

    def _view_file(self, args: str) -> None:
        """View a file with syntax highlighting and line numbers.

        Usage:
            /view path/to/file.py           - View entire file
            /view path/to/file.py:50        - View from line 50
            /view path/to/file.py:50-100    - View lines 50-100
        """
        from rich.syntax import Syntax

        if not args:
            self.console.print(f"[{COLORS['primary']}]Usage:[/] /view <file>[:line[-end]]")
            self.console.print(f"[{COLORS['muted']}]Examples:[/]")
            self.console.print(f"  /view src/app.py          [dim]View entire file[/dim]")
            self.console.print(f"  /view src/app.py:50       [dim]View from line 50[/dim]")
            self.console.print(f"  /view src/app.py:50-100   [dim]View lines 50-100[/dim]")
            return

        # Parse file path and optional line range
        start_line = 1
        end_line = None

        if ':' in args:
            path_part, line_part = args.rsplit(':', 1)
            if '-' in line_part:
                try:
                    start_str, end_str = line_part.split('-', 1)
                    start_line = int(start_str)
                    end_line = int(end_str)
                except ValueError:
                    path_part = args  # Not a valid range, treat as path
            else:
                try:
                    start_line = int(line_part)
                except ValueError:
                    path_part = args  # Not a valid line number, treat as path
        else:
            path_part = args

        # Resolve path
        file_path = Path(path_part).expanduser()
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        file_path = file_path.resolve()

        if not file_path.exists():
            self._print_error(f"File not found: {file_path}")
            return

        if not file_path.is_file():
            self._print_error(f"Not a file: {file_path}")
            return

        # Read file content
        try:
            content = file_path.read_text()
        except Exception as e:
            self._print_error(f"Cannot read file: {e}")
            return

        # Detect language from extension
        ext_to_lang = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.jsx': 'javascript',
            '.java': 'java',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.hpp': 'cpp',
            '.cs': 'csharp',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.sh': 'bash',
            '.bash': 'bash',
            '.zsh': 'zsh',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.toml': 'toml',
            '.xml': 'xml',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.sql': 'sql',
            '.md': 'markdown',
            '.dockerfile': 'dockerfile',
        }

        suffix = file_path.suffix.lower()
        language = ext_to_lang.get(suffix, 'text')

        # Handle Dockerfile without extension
        if file_path.name.lower() == 'dockerfile':
            language = 'dockerfile'

        # Calculate line range
        lines = content.split('\n')
        total_lines = len(lines)

        if end_line is None:
            # Show from start_line to end (or reasonable chunk)
            if start_line > 1:
                end_line = min(start_line + 50, total_lines)  # Show 50 lines by default
            else:
                end_line = total_lines

        # Clamp to valid range
        start_line = max(1, min(start_line, total_lines))
        end_line = max(start_line, min(end_line, total_lines))

        # Extract the lines
        selected_lines = lines[start_line - 1:end_line]
        selected_content = '\n'.join(selected_lines)

        # Create syntax display
        syntax = Syntax(
            selected_content,
            language,
            line_numbers=True,
            start_line=start_line,
            theme="monokai",
            word_wrap=True,
            background_color="default",
        )

        # Show in panel with file info
        from rich.panel import Panel

        # Build title with file info
        rel_path = file_path.relative_to(Path.cwd()) if file_path.is_relative_to(Path.cwd()) else file_path
        if start_line > 1 or end_line < total_lines:
            title = f"[bold cyan]{rel_path}[/] [dim]({start_line}-{end_line} of {total_lines})[/dim]"
        else:
            title = f"[bold cyan]{rel_path}[/] [dim]({total_lines} lines)[/dim]"

        panel = Panel(
            syntax,
            title=title,
            title_align="left",
            border_style="dim",
            box=ROUNDED,
            padding=(0, 1),
        )
        self.console.print(panel)

        # Show navigation hint if not showing all
        if end_line < total_lines:
            next_start = end_line + 1
            self.console.print(f"[{COLORS['muted']}]More: /view {path_part}:{next_start}[/]")

    def _show_logs(self, args: str) -> None:
        """Show run logs."""
        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""

        if not subcmd:
            # Show recent runs
            runs = self.log_store.list_runs(limit=10)
            if not runs:
                self.console.print(f"[{COLORS['muted']}]No runs logged yet[/]")
                return

            table = Table(show_header=True, header_style=f"bold {COLORS['primary']}", box=ROUNDED)
            table.add_column("ID", style="dim", width=5)
            table.add_column("Mode", width=8)
            table.add_column("Msgs", justify="right", width=5)
            table.add_column("Duration", justify="right", width=8)
            table.add_column("Started", style="dim", width=14)

            for run in runs:
                started = run.started_at.strftime("%m-%d %H:%M")
                table.add_row(
                    str(run.id),
                    run.mode_display[:8],
                    str(run.entry_count),
                    run.duration_display,
                    started,
                )

            self.console.print(table)
            self.console.print(f"[{COLORS['muted']}]CLI: kira logs list, kira logs show <id>[/]")

        elif subcmd == "stats":
            stats = self.log_store.get_stats()
            self.console.print(f"[{COLORS['primary']}]Run Log Statistics[/]")
            self.console.print(f"[{COLORS['muted']}]Total runs:[/] {stats['total_runs']}")
            self.console.print(f"[{COLORS['muted']}]Total messages:[/] {stats['total_entries']}")
            if stats['by_mode']:
                mode_parts = [f"{m}: {c}" for m, c in stats['by_mode'].items()]
                self.console.print(f"[{COLORS['muted']}]By mode:[/] {', '.join(mode_parts)}")

        elif subcmd == "current":
            if self.run_id:
                self.console.print(f"[{COLORS['primary']}]Current run:[/] #{self.run_id}")
                self.console.print(f"[{COLORS['muted']}]Messages:[/] {self.message_count}")
            else:
                self.console.print(f"[{COLORS['muted']}]No active run[/]")

        else:
            self._print_warning(f"Unknown logs command: {subcmd}")
            self.console.print(f"[{COLORS['muted']}]Available: stats, current[/]")

    def _show_goodbye(self) -> None:
        """Show goodbye message."""
        elapsed = int(time.time() - self.session_start)
        mins, secs = divmod(elapsed, 60)

        # End the run log
        if self.run_id:
            self.log_store.end_run(self.run_id)

        self.console.print()
        self.console.print(f"[{COLORS['muted']}]Session: {self.message_count} messages in {mins}m {secs}s[/]")

        if self.config.personality.enabled:
            from ..core.personality import get_personality
            personality = get_personality()
            self.console.print(f"[bold {COLORS['primary']}]{personality.name}:[/] See you next time!")
        else:
            self.console.print(f"[{COLORS['primary']}]Goodbye![/]")

    def _print_success(self, msg: str) -> None:
        """Print success message."""
        self.console.print(f"[{COLORS['success']}]✓[/] {msg}")

    def _print_error(self, msg: str) -> None:
        """Print error message."""
        self.console.print(f"[{COLORS['error']}]✗[/] {msg}")

    def _print_warning(self, msg: str) -> None:
        """Print warning message."""
        self.console.print(f"[{COLORS['warning']}]![/] {msg}")

    def _print_status_bar(self) -> None:
        """Print a minimal status bar."""
        model_name, tier = self._get_model_display()
        modes = []
        if self.config.thinking.enabled:
            modes.append("T")
        if self.config.autonomous.enabled:
            modes.append("A")
        if self.config.memory.enabled and not self.no_memory:
            modes.append("M")

        mode_str = f"[{''.join(modes)}]" if modes else ""
        self.console.print(f"[{COLORS['muted']}]{model_name} {mode_str}[/]")

    async def _send_message(
        self,
        prompt: str,
        session_manager: SessionManager,
        client: KiraClient,
    ) -> None:
        """Send a message and display formatted response."""
        from .formatter import OutputFormatter

        self.message_count += 1
        start_time = time.time()

        # Log the entry
        entry_id = None
        if self.run_id:
            entry_id = self.log_store.add_entry(
                run_id=self.run_id,
                prompt=prompt,
                model=self.model or self.config.kira.model,
            )

        # Build prompt with context
        full_prompt = session_manager.build_prompt(prompt)

        # Show agent name
        self.console.print()
        if self.config.personality.enabled:
            agent_name = self.config.personality.name
            self.console.print(f"[bold {COLORS['primary']}]{agent_name}[/]")
        else:
            self.console.print(f"[bold {COLORS['secondary']}]Assistant[/]")

        # Collect response with spinner
        collected: list[str] = []

        # Show spinner while collecting response
        spinner = Spinner("dots", text=f"[{COLORS['muted']}]thinking...[/]", style=COLORS['primary'])

        try:
            with Live(spinner, console=self.console, refresh_per_second=10, transient=True) as live:
                async for chunk in client.run(full_prompt, agent=self.agent, resume=self.resume):
                    collected.append(chunk)
            # After first successful message, enable resume for subsequent messages
            # so kiro-cli maintains conversation context
            self.resume = True

        except KeyboardInterrupt:
            self.console.print()
            self._print_warning("Interrupted")
            if entry_id:
                duration = time.time() - start_time
                self.log_store.update_entry_response(entry_id, "".join(collected), duration)
            return
        except Exception as e:
            self.console.print()
            self._print_error(f"Error: {e}")
            if self.verbose:
                import traceback
                self.console.print(f"[{COLORS['muted']}]{traceback.format_exc()}[/]")
            return

        # Get full output
        full_output = "".join(collected)

        # Debug mode: dump raw output
        if self.verbose and os.environ.get("KIRA_DEBUG"):
            self.console.print(f"\n[dim]--- RAW ({len(full_output)} chars) ---[/]")
            self.console.print(f"[dim]{repr(full_output[:300])}...[/]")

        # Render formatted output
        if full_output.strip():
            formatter = OutputFormatter(self.console)
            formatter.format(full_output)

        # Show duration in verbose mode
        duration = time.time() - start_time
        if self.verbose and duration > 0:
            self.console.print()
            self.console.print(f"[{COLORS['muted']}]({duration:.1f}s)[/]")

        self.console.print()  # Final spacing

        # Log the response
        if entry_id:
            self.log_store.update_entry_response(entry_id, full_output, duration)

        # Extract memories (explicit markers + auto-extraction)
        if not self.no_memory and self.config.memory.auto_extract:
            saved = session_manager.save_memories(
                full_output,
                prompt=prompt,  # Pass prompt for context-aware extraction
                auto_extract=True,
            )
            if saved > 0 and self.verbose:
                self.console.print(f"[{COLORS['muted']}]Learned {saved} things[/]")

    def _get_working_dir(self) -> Path:
        """Get the working directory, falling back to default if needed."""
        cwd = Path.cwd()

        # Check if we're in a meaningful directory (has files or is a git repo)
        has_content = any(cwd.iterdir()) if cwd.exists() else False
        is_git_repo = (cwd / ".git").exists()
        is_project = (cwd / ".kira").exists() or (cwd / "pyproject.toml").exists() or (cwd / "package.json").exists()

        # If current directory seems valid, use it
        if has_content or is_git_repo or is_project:
            return cwd

        # Fall back to configured default
        if self.config.kira.default_working_dir:
            default_dir = Path(self.config.kira.default_working_dir).expanduser()
            if default_dir.exists():
                return default_dir

        # Fall back to home directory
        return Path.home()

    def run(self) -> None:
        """Run the interactive REPL."""
        self._show_welcome()
        self._check_for_updates()

        # Determine working directory
        work_dir = self._get_working_dir()
        if work_dir != Path.cwd():
            self.console.print(f"[{COLORS['muted']}]Working directory: {work_dir}[/]")
            self.console.print()

        # Initialize components
        memory_store = MemoryStore()
        skill_manager = SkillManager()
        session_manager = SessionManager(memory_store, skill_manager)

        # Resolve model
        resolved_model = resolve_model(self.model) or self.config.kira.model

        # Update context manager for the working directory
        self.context_manager = ContextManager(work_dir)

        # Start session with project context
        session = session_manager.start(
            working_dir=work_dir,
            skills=self.skills,
            memory_tags=None,
            memory_enabled=not self.no_memory and self.config.memory.enabled,
            max_context_tokens=self.config.memory.max_context_tokens,
            min_importance=self.config.memory.min_importance,
            context_manager=self.context_manager,
        )

        # Start run log
        self.run_id = self.log_store.start_run(
            session_id=session.id,
            mode=RunMode.REPL,
            model=resolved_model,
            working_dir=str(work_dir),
            skills=self.skills,
        )

        # Configure client
        try:
            client = KiraClient(
                agent=self.agent or self.config.default_agent,
                model=resolved_model,
                trust_all_tools=self.trust or self.config.kira.trust_all_tools,
                working_dir=session.working_dir,
                timeout=self.config.kira.timeout,
            )
        except KiraNotFoundError as e:
            self._print_error(str(e))
            sys.exit(1)

        # Create prompt session with history and completion
        prompt_session: PromptSession[str] = PromptSession(
            history=FileHistory(str(self.history_file)),
            style=PROMPT_STYLE,
            completer=REPLCompleter(),
            complete_while_typing=False,
        )

        self.running = True

        while self.running:
            try:
                # Get user input with dynamic prompt
                user_input = prompt_session.prompt(
                    self._get_prompt_tokens(),
                    multiline=False,
                ).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    self.running = self._handle_command(user_input)
                    continue

                # Send message
                asyncio.run(self._send_message(user_input, session_manager, client))

            except KeyboardInterrupt:
                self.console.print()
                self.console.print(f"[{COLORS['muted']}]Ctrl+C to cancel, /exit to quit[/]")
                continue
            except EOFError:
                self._show_goodbye()
                break

        self.console.print()


def start_repl(
    model: str | None = None,
    trust: bool = False,
    skills: list[str] | None = None,
    resume: bool = False,
    agent: str | None = None,
    no_memory: bool = False,
    verbose: bool = False,
) -> None:
    """Start the interactive REPL."""
    repl = InteractiveREPL(
        model=model,
        trust=trust,
        skills=skills,
        resume=resume,
        agent=agent,
        no_memory=no_memory,
        verbose=verbose,
    )
    repl.run()

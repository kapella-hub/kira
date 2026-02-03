"""Memory management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from ...memory.maintenance import MemoryMaintenance
from ...memory.models import MemorySource, MemoryType
from ...memory.store import MemoryStore
from ..output import console, print_error, print_info, print_memory_table, print_success

app = typer.Typer(help="Manage persistent memory")


def get_store() -> MemoryStore:
    """Get the memory store instance."""
    return MemoryStore()


def parse_memory_type(type_str: str | None) -> MemoryType | None:
    """Parse memory type string to enum."""
    if not type_str:
        return None
    try:
        return MemoryType(type_str.lower())
    except ValueError:
        valid = ", ".join(t.value for t in MemoryType)
        raise typer.BadParameter(f"Invalid type. Valid types: {valid}")


def parse_memory_types(types: list[str] | None) -> list[MemoryType] | None:
    """Parse list of memory type strings."""
    if not types:
        return None
    return [parse_memory_type(t) for t in types]


@app.command("list")
def list_memories(
    tags: Annotated[
        list[str] | None,
        typer.Option("--tags", "-t", help="Filter by tags"),
    ] = None,
    memory_type: Annotated[
        str | None,
        typer.Option("--type", "-T", help="Filter by type (semantic, episodic, procedural)"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option(
            "--source", "-s", help="Filter by source (user, extracted, consolidated, marker)"
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum entries to show"),
    ] = 50,
    show_decay: Annotated[
        bool,
        typer.Option("--decay", "-d", help="Show decayed importance values"),
    ] = False,
):
    """List all memories."""
    store = get_store()

    # Parse filters
    types = [parse_memory_type(memory_type)] if memory_type else None
    src = MemorySource(source) if source else None

    memories = store.list_all(tags=tags, memory_types=types, source=src, limit=limit)

    if not memories:
        print_info("No memories found")
        return

    print_memory_table(memories, show_decay=show_decay)

    total = store.count(tags=tags, memory_types=types, source=src)
    if total > limit:
        print_info(f"Showing {limit} of {total} memories")


@app.command("search")
def search_memories(
    query: Annotated[str, typer.Argument(help="Search query")],
    tags: Annotated[
        list[str] | None,
        typer.Option("--tags", "-t", help="Filter by tags"),
    ] = None,
    memory_type: Annotated[
        str | None,
        typer.Option("--type", "-T", help="Filter by type (semantic, episodic, procedural)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum results"),
    ] = 10,
):
    """Search memories using full-text search."""
    store = get_store()
    types = [parse_memory_type(memory_type)] if memory_type else None

    try:
        memories = store.search(query, tags=tags, memory_types=types, limit=limit)
    except Exception as e:
        print_error(f"Search failed: {e}")
        raise typer.Exit(1)

    if not memories:
        print_info(f"No memories matching '{query}'")
        return

    print_memory_table(memories, title=f"Search: {query}")


@app.command("add")
def add_memory(
    key: Annotated[str, typer.Argument(help="Memory key (e.g., 'project:config')")],
    content: Annotated[str, typer.Argument(help="Memory content")],
    tags: Annotated[
        list[str] | None,
        typer.Option("--tags", "-t", help="Tags for this memory"),
    ] = None,
    importance: Annotated[
        int,
        typer.Option("--importance", "-i", help="Importance (1-10)"),
    ] = 5,
    memory_type: Annotated[
        str,
        typer.Option("--type", "-T", help="Memory type (semantic, episodic, procedural)"),
    ] = "semantic",
):
    """Add or update a memory."""
    if importance < 1 or importance > 10:
        print_error("Importance must be between 1 and 10")
        raise typer.Exit(1)

    mtype = parse_memory_type(memory_type)
    store = get_store()
    memory = store.store(
        key,
        content,
        tags=tags,
        importance=importance,
        memory_type=mtype,
        source=MemorySource.USER,
    )
    print_success(f"Stored memory: {memory.key} (type: {mtype.value})")


@app.command("get")
def get_memory(
    key: Annotated[str, typer.Argument(help="Memory key")],
):
    """Get a specific memory by key."""
    store = get_store()
    memory = store.get(key)

    if not memory:
        print_error(f"Memory not found: {key}")
        raise typer.Exit(1)

    console.print(f"[cyan]Key:[/cyan] {memory.key}")
    console.print(f"[cyan]Content:[/cyan] {memory.content}")
    console.print(f"[cyan]Type:[/cyan] {memory.memory_type.value}")
    console.print(f"[cyan]Source:[/cyan] {memory.source.value}")
    console.print(
        f"[cyan]Importance:[/cyan] {memory.importance} (decayed: {memory.decayed_importance:.1f})"
    )
    console.print(f"[cyan]Tags:[/cyan] {', '.join(memory.tags) if memory.tags else '-'}")
    console.print(f"[cyan]Access count:[/cyan] {memory.access_count}")
    if memory.last_accessed_at:
        console.print(f"[cyan]Last accessed:[/cyan] {memory.last_accessed_at}")
    console.print(f"[cyan]Created:[/cyan] {memory.created_at}")
    console.print(f"[cyan]Updated:[/cyan] {memory.updated_at}")


@app.command("delete")
def delete_memory(
    key: Annotated[str, typer.Argument(help="Memory key to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Delete a memory by key."""
    store = get_store()

    memory = store.get(key, track_access=False)
    if not memory:
        print_error(f"Memory not found: {key}")
        raise typer.Exit(1)

    if not force:
        console.print(f"About to delete: [cyan]{key}[/cyan]")
        console.print(f"Content: {memory.content[:100]}...")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            raise typer.Abort()

    if store.delete(key):
        print_success(f"Deleted: {key}")
    else:
        print_error(f"Failed to delete: {key}")
        raise typer.Exit(1)


@app.command("clear")
def clear_memories(
    tags: Annotated[
        list[str] | None,
        typer.Option("--tags", "-t", help="Only clear memories with these tags"),
    ] = None,
    memory_type: Annotated[
        str | None,
        typer.Option("--type", "-T", help="Only clear memories of this type"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Only clear memories from this source"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Clear all memories or those matching filters."""
    store = get_store()

    types = [parse_memory_type(memory_type)] if memory_type else None
    src = MemorySource(source) if source else None

    count = store.count(tags=tags, memory_types=types, source=src)
    if count == 0:
        print_info("No memories to clear")
        return

    if not force:
        filters = []
        if tags:
            filters.append(f"tags: {', '.join(tags)}")
        if memory_type:
            filters.append(f"type: {memory_type}")
        if source:
            filters.append(f"source: {source}")

        if filters:
            console.print(f"About to delete {count} memories matching: {'; '.join(filters)}")
        else:
            console.print(f"About to delete ALL {count} memories")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            raise typer.Abort()

    deleted = store.clear(tags=tags, memory_types=types, source=src)
    print_success(f"Cleared {deleted} memories")


@app.command("stats")
def memory_stats(
    show_decay: Annotated[
        bool,
        typer.Option("--decay", "-d", help="Show decay report"),
    ] = False,
):
    """Show memory statistics."""
    store = get_store()
    stats = store.get_stats()

    console.print(f"[cyan]Total memories:[/cyan] {stats['total']}")

    if stats["total"] == 0:
        return

    console.print(f"[cyan]Average access count:[/cyan] {stats['avg_access_count']:.1f}")

    if stats["by_type"]:
        console.print("\n[cyan]By type:[/cyan]")
        for mtype, count in stats["by_type"].items():
            console.print(f"  {mtype}: {count}")

    if stats["by_source"]:
        console.print("\n[cyan]By source:[/cyan]")
        for source, count in stats["by_source"].items():
            console.print(f"  {source}: {count}")

    if stats["by_importance"]:
        console.print("\n[cyan]By importance:[/cyan]")
        for imp, count in sorted(stats["by_importance"].items(), reverse=True):
            console.print(f"  {imp}: {count}")

    if show_decay:
        maintenance = MemoryMaintenance(store)
        report = maintenance.get_decay_report(limit=20)

        if report:
            console.print("\n[cyan]Decay report (top 20 most decayed):[/cyan]")
            for item in report[:20]:
                decay_pct = item["decay_percentage"]
                if decay_pct > 0:
                    console.print(
                        f"  {item['key']}: {item['original_importance']} -> "
                        f"{item['decayed_importance']} ({decay_pct:.0f}% decay, "
                        f"{item['age_days']} days old)"
                    )


@app.command("cleanup")
def cleanup_memories(
    max_age: Annotated[
        int,
        typer.Option("--max-age", "-a", help="Maximum age in days for low-importance memories"),
    ] = 90,
    min_importance: Annotated[
        float,
        typer.Option("--min-importance", "-i", help="Minimum importance threshold (after decay)"),
    ] = 2.0,
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Only cleanup memories from this source"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview what would be deleted"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Clean up old, low-importance memories.

    Deletes memories that are:
    - Older than --max-age days
    - Have decayed importance below --min-importance
    """
    store = get_store()
    maintenance = MemoryMaintenance(store)

    src = MemorySource(source) if source else None

    result = maintenance.cleanup(
        max_age_days=max_age,
        min_importance=min_importance,
        source_filter=src,
        dry_run=True,  # Always preview first
    )

    if result.deleted_count == 0:
        print_info("No memories to clean up")
        return

    console.print(f"[yellow]Found {result.deleted_count} memories to delete:[/yellow]")
    for key in result.deleted_keys[:10]:
        console.print(f"  - {key}")
    if result.deleted_count > 10:
        console.print(f"  ... and {result.deleted_count - 10} more")

    if dry_run:
        print_info("Dry run - no changes made")
        return

    if not force:
        confirm = typer.confirm(f"Delete {result.deleted_count} memories?")
        if not confirm:
            raise typer.Abort()

    # Actually delete
    result = maintenance.cleanup(
        max_age_days=max_age,
        min_importance=min_importance,
        source_filter=src,
        dry_run=False,
    )

    print_success(f"Deleted {result.deleted_count} memories")


@app.command("consolidate")
def consolidate_memories(
    threshold: Annotated[
        float,
        typer.Option("--threshold", "-t", help="Similarity threshold for merging (0-1)"),
    ] = 0.85,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview what would be merged"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Consolidate duplicate/similar memories.

    Finds memories with similar content and merges them:
    - Keeps the highest importance memory's key
    - Uses the longest content
    - Combines all tags
    - Sums access counts
    """
    store = get_store()
    maintenance = MemoryMaintenance(store)

    # Find duplicates first
    duplicates = maintenance.find_duplicates(threshold=threshold)

    if not duplicates:
        print_info("No duplicate memories found")
        return

    console.print(f"[yellow]Found {len(duplicates)} similar memory pairs:[/yellow]")
    for pair in duplicates[:5]:
        console.print(f"  [{pair.similarity:.0%}] {pair.memory1.key} <-> {pair.memory2.key}")
    if len(duplicates) > 5:
        console.print(f"  ... and {len(duplicates) - 5} more pairs")

    if dry_run:
        result = maintenance.consolidate(threshold=threshold, dry_run=True)
        console.print(
            f"\n[cyan]Would merge into {len(result.new_memories)} consolidated memories[/cyan]"
        )
        console.print(f"[cyan]Would delete {len(result.deleted_keys)} memories[/cyan]")
        print_info("Dry run - no changes made")
        return

    if not force:
        confirm = typer.confirm("Merge these memories?")
        if not confirm:
            raise typer.Abort()

    result = maintenance.consolidate(threshold=threshold, dry_run=False)

    print_success(
        f"Consolidated {result.merged_count} groups, deleted {len(result.deleted_keys)} memories"
    )

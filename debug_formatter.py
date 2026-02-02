#!/usr/bin/env python3
"""Debug script to test formatter with actual kiro-cli output."""

import asyncio
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent / "src"))

from kira.core.client import KiraClient
from kira.cli.formatter import OutputFormatter
from rich.console import Console


async def main():
    console = Console()

    # Test prompt
    prompt = "write a simple hello world bash script"

    console.print(f"[cyan]Sending prompt:[/] {prompt}\n")
    console.print("[yellow]--- Collecting raw output ---[/]")

    # Get output from kiro-cli
    client = KiraClient()
    chunks = []

    async for chunk in client.run(prompt):
        chunks.append(chunk)
        # Show chunks as they come
        sys.stdout.write(f"[chunk: {len(chunk)} bytes]")
        sys.stdout.flush()

    raw_output = "".join(chunks)

    console.print("\n\n[yellow]--- RAW OUTPUT REPR ---[/]")
    console.print(repr(raw_output[:1000]))

    console.print("\n[yellow]--- RAW OUTPUT AS TEXT ---[/]")
    console.print(raw_output, highlight=False)

    console.print("\n[yellow]--- FORMATTED OUTPUT ---[/]")
    formatter = OutputFormatter(console)
    formatter.format(raw_output)

    console.print("\n[green]Done![/]")


if __name__ == "__main__":
    asyncio.run(main())

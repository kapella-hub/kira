"""File operation tools."""

from __future__ import annotations

import time
from pathlib import Path

from .base import BaseTool, registry
from .models import ToolResult, ToolStatus


@registry.register
class ReadFile(BaseTool):
    """Read contents of a file."""

    name = "read_file"
    description = "Read the contents of a file"
    requires_trust = False

    async def execute(
        self,
        path: str | None = None,
        **kwargs: str | int | bool | list[str] | None,
    ) -> ToolResult:
        """Read a file.

        Args:
            path: Path to file to read.
            **kwargs: Additional arguments (ignored).

        Returns:
            Tool result with file contents.
        """
        if not path:
            return self.make_result(ToolStatus.FAILURE, "", error="path argument required")

        start = time.time()
        file_path = Path(self.context.working_dir) / path

        if not file_path.exists():
            return self.make_result(ToolStatus.FAILURE, "", error=f"File not found: {path}")

        if not file_path.is_file():
            return self.make_result(ToolStatus.FAILURE, "", error=f"Not a file: {path}")

        try:
            content = file_path.read_text()
            result = self.make_result(
                ToolStatus.SUCCESS,
                content,
                duration=time.time() - start,
            )
            self.record({"path": path}, result)
            return result
        except PermissionError:
            return self.make_result(
                ToolStatus.PERMISSION_DENIED,
                "",
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return self.make_result(ToolStatus.FAILURE, "", error=str(e))


@registry.register
class WriteFile(BaseTool):
    """Write contents to a file."""

    name = "write_file"
    description = "Write contents to a file"
    requires_trust = True

    async def execute(
        self,
        path: str | None = None,
        content: str | None = None,
        **kwargs: str | int | bool | list[str] | None,
    ) -> ToolResult:
        """Write a file.

        Args:
            path: Path to file to write.
            content: Content to write.
            **kwargs: Additional arguments (ignored).

        Returns:
            Tool result.
        """
        if not path:
            return self.make_result(ToolStatus.FAILURE, "", error="path argument required")
        if content is None:
            return self.make_result(ToolStatus.FAILURE, "", error="content argument required")

        start = time.time()
        file_path = Path(self.context.working_dir) / path

        # Check trust level
        can_exec, reason = self.can_execute()
        if not can_exec:
            return self.make_result(ToolStatus.PERMISSION_DENIED, "", error=reason)

        # Dry run mode
        if self.context.dry_run:
            return self.make_result(
                ToolStatus.SUCCESS,
                f"[DRY RUN] Would write {len(content)} bytes to {path}",
                duration=time.time() - start,
            )

        try:
            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            is_new = not file_path.exists()
            file_path.write_text(content)

            result = self.make_result(
                ToolStatus.SUCCESS,
                f"Wrote {len(content)} bytes to {path}",
                files_created=[path] if is_new else [],
                files_modified=[] if is_new else [path],
                duration=time.time() - start,
            )
            self.record({"path": path, "content_length": len(content)}, result)
            return result
        except PermissionError:
            return self.make_result(
                ToolStatus.PERMISSION_DENIED,
                "",
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return self.make_result(ToolStatus.FAILURE, "", error=str(e))


@registry.register
class EditFile(BaseTool):
    """Edit a file by replacing text."""

    name = "edit_file"
    description = "Edit a file by replacing text"
    requires_trust = True

    async def execute(
        self,
        path: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
        **kwargs: str | int | bool | list[str] | None,
    ) -> ToolResult:
        """Edit a file by replacing text.

        Args:
            path: Path to file to edit.
            old_text: Text to find and replace.
            new_text: Replacement text.
            **kwargs: Additional arguments (ignored).

        Returns:
            Tool result.
        """
        if not path:
            return self.make_result(ToolStatus.FAILURE, "", error="path argument required")
        if old_text is None:
            return self.make_result(ToolStatus.FAILURE, "", error="old_text argument required")
        if new_text is None:
            return self.make_result(ToolStatus.FAILURE, "", error="new_text argument required")

        start = time.time()
        file_path = Path(self.context.working_dir) / path

        if not file_path.exists():
            return self.make_result(ToolStatus.FAILURE, "", error=f"File not found: {path}")

        # Check trust level
        can_exec, reason = self.can_execute()
        if not can_exec:
            return self.make_result(ToolStatus.PERMISSION_DENIED, "", error=reason)

        try:
            content = file_path.read_text()

            if old_text not in content:
                return self.make_result(
                    ToolStatus.FAILURE,
                    "",
                    error=f"Text not found in {path}",
                )

            # Dry run mode
            if self.context.dry_run:
                count = content.count(old_text)
                return self.make_result(
                    ToolStatus.SUCCESS,
                    f"[DRY RUN] Would replace {count} occurrence(s) in {path}",
                    duration=time.time() - start,
                )

            new_content = content.replace(old_text, new_text)
            file_path.write_text(new_content)

            count = content.count(old_text)
            result = self.make_result(
                ToolStatus.SUCCESS,
                f"Replaced {count} occurrence(s) in {path}",
                files_modified=[path],
                duration=time.time() - start,
            )
            self.record(
                {"path": path, "replacements": count},
                result,
            )
            return result
        except PermissionError:
            return self.make_result(
                ToolStatus.PERMISSION_DENIED,
                "",
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return self.make_result(ToolStatus.FAILURE, "", error=str(e))


@registry.register
class ListDirectory(BaseTool):
    """List contents of a directory."""

    name = "list_dir"
    description = "List contents of a directory"
    requires_trust = False

    async def execute(
        self,
        path: str | None = None,
        **kwargs: str | int | bool | list[str] | None,
    ) -> ToolResult:
        """List directory contents.

        Args:
            path: Path to directory (default: working dir).
            **kwargs: Additional arguments (ignored).

        Returns:
            Tool result with directory listing.
        """
        start = time.time()
        dir_path = Path(self.context.working_dir)
        if path:
            dir_path = dir_path / path

        if not dir_path.exists():
            return self.make_result(
                ToolStatus.FAILURE, "", error=f"Directory not found: {path or '.'}"
            )

        if not dir_path.is_dir():
            return self.make_result(ToolStatus.FAILURE, "", error=f"Not a directory: {path or '.'}")

        try:
            entries: list[str] = []
            for entry in sorted(dir_path.iterdir()):
                if entry.is_dir():
                    entries.append(f"{entry.name}/")
                else:
                    entries.append(entry.name)

            output = "\n".join(entries) if entries else "(empty directory)"
            result = self.make_result(
                ToolStatus.SUCCESS,
                output,
                duration=time.time() - start,
            )
            self.record({"path": path or "."}, result)
            return result
        except PermissionError:
            return self.make_result(
                ToolStatus.PERMISSION_DENIED,
                "",
                error=f"Permission denied: {path or '.'}",
            )
        except Exception as e:
            return self.make_result(ToolStatus.FAILURE, "", error=str(e))


@registry.register
class DeleteFile(BaseTool):
    """Delete a file."""

    name = "delete_file"
    description = "Delete a file"
    requires_trust = True

    async def execute(
        self,
        path: str | None = None,
        **kwargs: str | int | bool | list[str] | None,
    ) -> ToolResult:
        """Delete a file.

        Args:
            path: Path to file to delete.
            **kwargs: Additional arguments (ignored).

        Returns:
            Tool result.
        """
        if not path:
            return self.make_result(ToolStatus.FAILURE, "", error="path argument required")

        start = time.time()
        file_path = Path(self.context.working_dir) / path

        if not file_path.exists():
            return self.make_result(ToolStatus.FAILURE, "", error=f"File not found: {path}")

        # Check trust level
        can_exec, reason = self.can_execute()
        if not can_exec:
            return self.make_result(ToolStatus.PERMISSION_DENIED, "", error=reason)

        # Dry run mode
        if self.context.dry_run:
            return self.make_result(
                ToolStatus.SUCCESS,
                f"[DRY RUN] Would delete {path}",
                duration=time.time() - start,
            )

        try:
            if file_path.is_file():
                file_path.unlink()
            elif file_path.is_dir():
                import shutil

                shutil.rmtree(file_path)

            result = self.make_result(
                ToolStatus.SUCCESS,
                f"Deleted {path}",
                files_deleted=[path],
                duration=time.time() - start,
            )
            self.record({"path": path}, result)
            return result
        except PermissionError:
            return self.make_result(
                ToolStatus.PERMISSION_DENIED,
                "",
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return self.make_result(ToolStatus.FAILURE, "", error=str(e))

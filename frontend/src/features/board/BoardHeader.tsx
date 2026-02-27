import { useState, useMemo } from 'react';
import { Search, Plus, Sparkles, MoreHorizontal, RefreshCw, Settings, Users, Gitlab, FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/Button.tsx';
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { updateBoard } from '@/api/boards.ts';
import { createColumn } from '@/api/boards.ts';
import { syncBoard } from '@/api/jira.ts';
import type { GitLabSettings } from '@/types/gitlab.ts';

export function BoardHeader() {
  const board = useBoardStore((s) => s.currentBoard);
  const { addColumn } = useBoardStore();
  const { setSearchOpen, addToast, openModal } = useUIStore();
  const [editingName, setEditingName] = useState(false);
  const [editName, setEditName] = useState('');
  const [editingDesc, setEditingDesc] = useState(false);
  const [editDesc, setEditDesc] = useState('');
  const [syncing, setSyncing] = useState(false);

  const gitlabSettings = useMemo<GitLabSettings | null>(() => {
    if (!board?.settings_json) return null;
    try {
      const parsed = JSON.parse(board.settings_json);
      return parsed?.gitlab ?? null;
    } catch {
      return null;
    }
  }, [board?.settings_json]);

  if (!board) return null;

  async function handleRename() {
    if (editName.trim() && editName.trim() !== board!.name) {
      try {
        await updateBoard(board!.id, { name: editName.trim() });
      } catch {
        addToast('Failed to rename board', 'error');
      }
    }
    setEditingName(false);
  }

  async function handleDescriptionSave() {
    if (editDesc.trim() !== board!.description) {
      try {
        await updateBoard(board!.id, { description: editDesc.trim() });
      } catch {
        addToast('Failed to update description', 'error');
      }
    }
    setEditingDesc(false);
  }

  async function handleAddColumn() {
    try {
      const col = await createColumn(board!.id, { name: 'New Column' });
      addColumn(col);
    } catch {
      addToast('Failed to add column', 'error');
    }
  }

  async function handleJiraSync() {
    setSyncing(true);
    try {
      const result = await syncBoard(board!.id);
      addToast(`Jira sync queued (task ${result.task_id})`, 'success');
    } catch {
      addToast('Jira sync failed', 'error');
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-divider">
      {/* Left side: board name + description */}
      <div className="flex flex-col gap-0.5 min-w-0">
        {editingName ? (
          <input
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRename();
              if (e.key === 'Escape') setEditingName(false);
            }}
            onBlur={handleRename}
            className="bg-transparent text-lg font-bold text-text-primary outline-none border-b border-accent"
            autoFocus
          />
        ) : (
          <h1
            className="text-lg font-bold text-text-primary cursor-pointer hover:text-accent transition-colors truncate"
            onDoubleClick={() => {
              setEditName(board.name);
              setEditingName(true);
            }}
            title="Double-click to rename"
          >
            {board.name}
          </h1>
        )}

        {editingDesc ? (
          <input
            value={editDesc}
            onChange={(e) => setEditDesc(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleDescriptionSave();
              if (e.key === 'Escape') setEditingDesc(false);
            }}
            onBlur={handleDescriptionSave}
            placeholder="Add a board description..."
            className="bg-transparent text-xs text-text-secondary outline-none border-b border-accent/50 max-w-[400px]"
            autoFocus
          />
        ) : (
          <p
            className="text-xs text-text-muted cursor-pointer hover:text-text-secondary transition-colors truncate max-w-[400px]"
            onDoubleClick={() => {
              setEditDesc(board.description || '');
              setEditingDesc(true);
            }}
            title="Double-click to edit description"
          >
            {board.description || 'No description'}
          </p>
        )}
      </div>

      {/* Right side: essential actions + more menu */}
      <div className="flex items-center gap-1.5">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSearchOpen(true)}
          title="Search cards"
        >
          <Search size={14} />
          <span className="text-text-muted text-[10px] ml-0.5 hidden sm:inline">Cmd+K</span>
        </Button>

        <Button variant="ghost" size="sm" onClick={handleAddColumn} title="Add column">
          <Plus size={14} />
          <span className="hidden sm:inline">Column</span>
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => openModal('generate-cards')}
          title="Generate task cards with AI"
        >
          <Sparkles size={14} />
          <span className="hidden sm:inline">Generate</span>
        </Button>

        {/* More menu: Jira sync, GitLab, Members, Settings */}
        <Dropdown
          trigger={
            <Button variant="ghost" size="sm" aria-label="More actions">
              <MoreHorizontal size={14} />
            </Button>
          }
          align="right"
        >
          {board.jira_sync_enabled && (
            <DropdownItem
              onClick={handleJiraSync}
            >
              <span className="inline-flex items-center gap-2">
                <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} />
                {syncing ? 'Syncing...' : 'Jira Sync'}
              </span>
            </DropdownItem>
          )}
          {gitlabSettings ? (
            <DropdownItem onClick={() => openModal('gitlab-project-picker')}>
              <span className="inline-flex items-center gap-2">
                <Gitlab size={13} className="text-orange-400" />
                GitLab Settings
              </span>
            </DropdownItem>
          ) : (
            <DropdownItem onClick={() => openModal('gitlab-project-picker')}>
              <span className="inline-flex items-center gap-2">
                <Gitlab size={13} />
                Link GitLab
              </span>
            </DropdownItem>
          )}
          <DropdownItem onClick={() => openModal('board-members')}>
            <span className="inline-flex items-center gap-2">
              <Users size={13} />
              Members
            </span>
          </DropdownItem>
          <DropdownItem onClick={() => openModal('workspace-settings')}>
            <span className="inline-flex items-center gap-2">
              <FolderOpen size={13} />
              Workspace
            </span>
          </DropdownItem>
          <DropdownItem onClick={() => openModal('jira-settings')}>
            <span className="inline-flex items-center gap-2">
              <Settings size={13} />
              Board Settings
            </span>
          </DropdownItem>
        </Dropdown>
      </div>
    </div>
  );
}

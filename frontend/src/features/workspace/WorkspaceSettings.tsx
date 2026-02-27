import { useState, useEffect, useMemo } from 'react';
import { FolderOpen, GitBranch, RotateCcw, Home } from 'lucide-react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { useAgentStore } from '@/stores/agentStore.ts';
import { updateBoardSettings } from '@/api/boards.ts';
import { get } from '@/api/client.ts';

type WorkspaceMode = 'local' | 'gitlab';

interface WorkspaceConfig {
  local_path: string;
  gitlab_project: string;
}

interface UserPreferences {
  default_working_dir?: string;
}

const EMPTY_CONFIG: WorkspaceConfig = {
  local_path: '',
  gitlab_project: '',
};

export function WorkspaceSettings() {
  const { activeModal, closeModal, addToast } = useUIStore();
  const board = useBoardStore((s) => s.currentBoard);
  const agentState = useAgentStore((s) => s.agentState);
  const agentWs = useAgentStore((s) => s._ws);
  const open = activeModal === 'workspace-settings';

  const [mode, setMode] = useState<WorkspaceMode>('local');
  const [localPath, setLocalPath] = useState('');
  const [gitlabProject, setGitlabProject] = useState('');
  const [saving, setSaving] = useState(false);
  const [defaultDir, setDefaultDir] = useState<string | null>(null);

  // Parse current workspace config from board settings_json
  const currentConfig = useMemo<WorkspaceConfig>(() => {
    if (!board?.settings_json) return EMPTY_CONFIG;
    try {
      const parsed = JSON.parse(board.settings_json);
      return parsed?.workspace ?? EMPTY_CONFIG;
    } catch {
      return EMPTY_CONFIG;
    }
  }, [board?.settings_json]);

  const isConfigured = Boolean(currentConfig.local_path || currentConfig.gitlab_project);

  // Populate form when modal opens + fetch user preferences
  useEffect(() => {
    if (!open) return;
    setLocalPath(currentConfig.local_path || '');
    setGitlabProject(currentConfig.gitlab_project || '');
    // Determine initial mode from current config
    if (currentConfig.gitlab_project) {
      setMode('gitlab');
    } else {
      setMode('local');
    }
    // Fetch user default working dir preference
    get<UserPreferences>('/auth/users/me/preferences')
      .then((prefs) => {
        setDefaultDir(prefs?.default_working_dir ?? null);
      })
      .catch(() => {
        setDefaultDir(null);
      });
  }, [open, currentConfig]);

  async function handleBrowse() {
    if (!agentWs || agentWs.readyState !== WebSocket.OPEN) return;
    const requestId = crypto.randomUUID();

    const result = await new Promise<string | null>((resolve) => {
      const timeout = setTimeout(() => {
        agentWs.removeEventListener('message', handler);
        resolve(null);
      }, 120000);

      function handler(event: MessageEvent) {
        try {
          const data = JSON.parse(String(event.data));
          if (data.type === 'directory_picked' && data.request_id === requestId) {
            clearTimeout(timeout);
            agentWs!.removeEventListener('message', handler);
            resolve(data.cancelled ? null : data.path);
          }
        } catch {
          // Ignore parse errors
        }
      }

      agentWs.addEventListener('message', handler);
      agentWs.send(
        JSON.stringify({
          type: 'pick_directory',
          request_id: requestId,
          initial_dir: localPath || undefined,
        }),
      );
    });

    if (result) setLocalPath(result);
  }

  async function handleSave() {
    if (!board) return;

    const workspace: WorkspaceConfig = {
      local_path: mode === 'local' ? localPath.trim() : '',
      gitlab_project: mode === 'gitlab' ? gitlabProject.trim() : '',
    };

    // Validate that the active field has a value
    if (mode === 'local' && !workspace.local_path) {
      addToast('Please enter a local directory path', 'error');
      return;
    }
    if (mode === 'gitlab' && !workspace.gitlab_project) {
      addToast('Please enter a GitLab project path', 'error');
      return;
    }

    setSaving(true);
    try {
      await updateBoardSettings(board.id, { workspace });
      addToast('Workspace settings saved', 'success');
      closeModal();
    } catch {
      addToast('Failed to save workspace settings', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    if (!board) return;
    setSaving(true);
    try {
      await updateBoardSettings(board.id, { workspace: EMPTY_CONFIG });
      setLocalPath('');
      setGitlabProject('');
      addToast('Workspace settings cleared', 'success');
      closeModal();
    } catch {
      addToast('Failed to clear workspace settings', 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={closeModal} title="Workspace Settings">
      <div className="space-y-5">
        {/* Status indicator */}
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${isConfigured ? 'bg-success' : 'bg-text-muted'}`}
          />
          <span className="text-text-secondary">
            {isConfigured
              ? currentConfig.local_path
                ? `Configured: ${currentConfig.local_path}`
                : `Configured: ${currentConfig.gitlab_project}`
              : 'Not configured'}
          </span>
        </div>

        {/* Mode selector */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-text-secondary">Workspace Type</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setMode('local')}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg border text-sm transition-all cursor-pointer ${
                mode === 'local'
                  ? 'border-accent/60 bg-accent/10 text-text-primary'
                  : 'border-divider bg-transparent text-text-secondary hover:border-text-muted hover:bg-white/[0.02]'
              }`}
            >
              <FolderOpen size={15} className={mode === 'local' ? 'text-accent' : ''} />
              <span className="font-medium">Local Directory</span>
            </button>
            <button
              type="button"
              onClick={() => setMode('gitlab')}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg border text-sm transition-all cursor-pointer ${
                mode === 'gitlab'
                  ? 'border-accent/60 bg-accent/10 text-text-primary'
                  : 'border-divider bg-transparent text-text-secondary hover:border-text-muted hover:bg-white/[0.02]'
              }`}
            >
              <GitBranch size={15} className={mode === 'gitlab' ? 'text-accent' : ''} />
              <span className="font-medium">GitLab Repository</span>
            </button>
          </div>
        </div>

        {/* Mode-specific fields */}
        {mode === 'local' ? (
          <div>
            <div className="flex gap-2">
              <div className="flex-1">
                <Input
                  label="Directory Path"
                  placeholder="/Users/you/Projects/my-app"
                  value={localPath}
                  onChange={(e) => setLocalPath(e.target.value)}
                />
              </div>
              <div className="pt-5">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleBrowse}
                  disabled={agentState !== 'active'}
                  title={
                    agentState !== 'active'
                      ? 'Agent must be running to browse'
                      : 'Open directory picker'
                  }
                >
                  <FolderOpen size={14} />
                </Button>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-1.5">
              <p className="text-xs text-text-muted">
                Path must exist on the machine running the worker
              </p>
              {defaultDir && defaultDir !== localPath && (
                <button
                  type="button"
                  onClick={() => setLocalPath(defaultDir)}
                  className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-hover transition-colors"
                  title={`Use default: ${defaultDir}`}
                >
                  <Home size={11} />
                  Use default
                </button>
              )}
            </div>
          </div>
        ) : (
          <div>
            <Input
              label="GitLab Project Path"
              placeholder="group/project-name"
              value={gitlabProject}
              onChange={(e) => setGitlabProject(e.target.value)}
            />
            <p className="text-xs text-text-muted mt-1.5">
              The worker will clone/pull this repository automatically
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between pt-1">
          <div>
            {isConfigured && (
              <Button variant="ghost" size="sm" onClick={handleClear} loading={saving}>
                <RotateCcw size={13} />
                Clear
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={closeModal}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleSave} loading={saving}>
              Save
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

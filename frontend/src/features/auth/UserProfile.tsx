import { useState, useEffect } from 'react';
import { FolderOpen, ExternalLink } from 'lucide-react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { Avatar } from '@/components/ui/Avatar.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useAuthStore } from '@/stores/authStore.ts';
import { useAgentStore } from '@/stores/agentStore.ts';
import { get, patch } from '@/api/client.ts';

interface UserPreferences {
  default_working_dir?: string;
}

export function UserProfile() {
  const { activeModal, closeModal, addToast, openModal } = useUIStore();
  const user = useAuthStore((s) => s.user);
  const updateUser = useAuthStore((s) => s.updateUser);
  const agentState = useAgentStore((s) => s.agentState);
  const agentWs = useAgentStore((s) => s._ws);
  const open = activeModal === 'user-profile';

  const [displayName, setDisplayName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [defaultWorkingDir, setDefaultWorkingDir] = useState('');
  const [saving, setSaving] = useState(false);
  const [loadingPrefs, setLoadingPrefs] = useState(false);

  useEffect(() => {
    if (!user || !open) return;
    setDisplayName(user.display_name);
    setAvatarUrl(user.avatar_url);

    // Load user preferences
    setLoadingPrefs(true);
    get<UserPreferences>('/auth/users/me/preferences')
      .then((prefs) => {
        setDefaultWorkingDir(prefs?.default_working_dir ?? '');
      })
      .catch(() => {
        setDefaultWorkingDir('');
      })
      .finally(() => {
        setLoadingPrefs(false);
      });
  }, [user, open]);

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
          initial_dir: defaultWorkingDir || undefined,
        }),
      );
    });

    if (result) setDefaultWorkingDir(result);
  }

  async function handleSave() {
    if (!displayName.trim()) {
      addToast('Display name is required', 'error');
      return;
    }

    setSaving(true);
    try {
      await patch('/auth/users/me/profile', {
        display_name: displayName.trim(),
        avatar_url: avatarUrl.trim(),
        preferences: {
          default_working_dir: defaultWorkingDir.trim() || undefined,
        },
      });
      updateUser({
        display_name: displayName.trim(),
        avatar_url: avatarUrl.trim(),
      });
      addToast('Profile updated', 'success');
      closeModal();
    } catch {
      addToast('Failed to update profile', 'error');
    } finally {
      setSaving(false);
    }
  }

  if (!user) return null;

  return (
    <Modal open={open} onClose={closeModal} title="Profile">
      <div className="space-y-5">
        {/* Avatar preview */}
        <div className="flex items-center gap-4">
          <Avatar
            name={displayName || user.display_name}
            url={avatarUrl || undefined}
            size="lg"
          />
          <div>
            <p className="text-sm font-medium text-text-primary">{user.display_name}</p>
            <p className="text-xs text-text-muted">@{user.username}</p>
          </div>
        </div>

        {/* Profile fields */}
        <Input
          label="Display Name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <Input
          label="Avatar URL"
          placeholder="https://example.com/avatar.jpg"
          value={avatarUrl}
          onChange={(e) => setAvatarUrl(e.target.value)}
        />

        {/* Integrations */}
        <div className="border-t border-divider pt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-3">
            Integrations
          </h4>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => {
                closeModal();
                openModal('gitlab-settings');
              }}
              className="flex items-center gap-2 text-sm text-accent hover:text-accent-hover transition-colors"
            >
              <ExternalLink size={13} />
              Configure GitLab credentials
            </button>
            <button
              type="button"
              onClick={() => {
                closeModal();
                openModal('jira-settings');
              }}
              className="flex items-center gap-2 text-sm text-accent hover:text-accent-hover transition-colors"
            >
              <ExternalLink size={13} />
              Configure Jira credentials
            </button>
          </div>
        </div>

        {/* Default Working Directory */}
        <div className="border-t border-divider pt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-3">
            Default Working Directory
          </h4>
          <p className="text-xs text-text-muted mb-3">
            Used when no workspace is configured for a board
          </p>
          <div className="flex gap-2">
            <div className="flex-1">
              <Input
                placeholder="/Users/you/Projects"
                value={defaultWorkingDir}
                onChange={(e) => setDefaultWorkingDir(e.target.value)}
                disabled={loadingPrefs}
              />
            </div>
            <div>
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
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" size="sm" onClick={closeModal}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={handleSave} loading={saving}>
            Save Changes
          </Button>
        </div>
      </div>
    </Modal>
  );
}

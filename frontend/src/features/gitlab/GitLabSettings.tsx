import { useState, useEffect } from 'react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { saveGitLabCredentials, testGitLabConnection, getGitLabStatus } from '@/api/gitlab.ts';

export function GitLabSettings() {
  const { activeModal, closeModal, addToast } = useUIStore();
  const open = activeModal === 'gitlab-settings';

  const [server, setServer] = useState('https://gitlab.com');
  const [token, setToken] = useState('');
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [status, setStatus] = useState<{ configured: boolean; server: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    // Reset form state when opening
    setToken('');
    setTestResult(null);
    // Fetch current status
    getGitLabStatus()
      .then((s) => {
        setStatus(s);
        if (s.server) setServer(s.server);
      })
      .catch(() => {
        setStatus(null);
      });
  }, [open]);

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testGitLabConnection();
      setTestResult(res.success ? `Connected as ${res.username}` : (res.error || 'Connection failed'));
    } catch {
      setTestResult('Connection failed');
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!server.trim() || !token.trim()) {
      addToast('Server URL and token are required', 'error');
      return;
    }
    setSaving(true);
    try {
      await saveGitLabCredentials(server.trim(), token.trim());
      addToast('GitLab credentials saved', 'success');
      closeModal();
    } catch {
      addToast('Failed to save credentials', 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={closeModal} title="GitLab Configuration">
      <div className="space-y-4">
        {status && (
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full ${status.configured ? 'bg-success' : 'bg-text-muted'}`}
            />
            <span className="text-text-secondary">
              {status.configured ? `Configured (${status.server})` : 'Not configured'}
            </span>
          </div>
        )}

        <Input
          label="Server URL"
          placeholder="https://gitlab.com"
          value={server}
          onChange={(e) => setServer(e.target.value)}
        />
        <Input
          label="Personal Access Token"
          type="password"
          placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />

        {testResult && (
          <p className={`text-xs ${testResult.includes('Connected') ? 'text-success' : 'text-error'}`}>
            {testResult}
          </p>
        )}

        <div className="flex gap-2 justify-end pt-2">
          <Button variant="ghost" size="sm" onClick={handleTest} loading={testing}>
            Test Connection
          </Button>
          <Button variant="primary" size="sm" onClick={handleSave} loading={saving}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}

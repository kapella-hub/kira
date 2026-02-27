import { useState } from 'react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { updateJiraCredentials, testJiraConnection } from '@/api/jira.ts';

export function JiraSettings() {
  const { activeModal, closeModal, addToast } = useUIStore();
  const open = activeModal === 'jira-settings';

  const [server, setServer] = useState('');
  const [username, setUsername] = useState('');
  const [token, setToken] = useState('');
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testJiraConnection();
      setTestResult(res.success ? `Connected as ${res.user}` : 'Connection failed');
    } catch {
      setTestResult('Connection failed');
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateJiraCredentials({ server, username, token });
      addToast('Jira credentials saved', 'success');
      closeModal();
    } catch {
      addToast('Failed to save credentials', 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={closeModal} title="Jira Configuration">
      <div className="space-y-4">
        <Input
          label="Server URL"
          placeholder="https://yourcompany.atlassian.net"
          value={server}
          onChange={(e) => setServer(e.target.value)}
        />
        <Input
          label="Username / Email"
          placeholder="user@company.com"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <Input
          label="API Token"
          type="password"
          placeholder="Your Jira API token"
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

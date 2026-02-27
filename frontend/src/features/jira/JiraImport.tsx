import { useState } from 'react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { importFromJira } from '@/api/jira.ts';

export function JiraImport() {
  const { activeModal, closeModal, addToast } = useUIStore();
  const { columns } = useBoardStore();
  const board = useBoardStore((s) => s.currentBoard);
  const open = activeModal === 'jira-import';

  const [jql, setJql] = useState('');
  const [targetColumn, setTargetColumn] = useState('');
  const [importing, setImporting] = useState(false);

  async function handleImport() {
    if (!jql.trim() || !targetColumn || !board) return;
    setImporting(true);
    try {
      const result = await importFromJira({
        jql: jql.trim(),
        board_id: board.id,
        column_id: targetColumn,
      });
      addToast(`Jira import queued (task ${result.task_id})`, 'success');
      closeModal();
    } catch {
      addToast('Failed to import from Jira', 'error');
    } finally {
      setImporting(false);
    }
  }

  return (
    <Modal open={open} onClose={closeModal} title="Import from Jira">
      <div className="space-y-4">
        <Input
          label="JQL Query"
          placeholder='project = PROJ AND sprint in openSprints()'
          value={jql}
          onChange={(e) => setJql(e.target.value)}
        />

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary">Target Column</label>
          <select
            value={targetColumn}
            onChange={(e) => setTargetColumn(e.target.value)}
            className="glass-input rounded-lg px-3 py-2 text-sm text-text-primary"
          >
            <option value="">Select a column</option>
            {columns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex justify-end pt-2">
          <Button
            variant="primary"
            size="sm"
            onClick={handleImport}
            loading={importing}
            disabled={!jql.trim() || !targetColumn}
          >
            Import
          </Button>
        </div>
      </div>
    </Modal>
  );
}

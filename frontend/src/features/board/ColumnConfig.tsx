import { useState, useEffect } from 'react';
import { Bot, Save, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/Button.tsx';
import { useBoardStore } from '@/stores/boardStore.ts';
import { useUIStore } from '@/stores/uiStore.ts';
import { updateColumn } from '@/api/boards.ts';
import clsx from 'clsx';

const AGENT_TYPES = [
  { value: '', label: 'None' },
  { value: 'architect', label: 'Architect', description: 'Design solution architecture' },
  { value: 'coder', label: 'Coder', description: 'Implement the solution' },
  { value: 'reviewer', label: 'Reviewer', description: 'Review implementation' },
  { value: 'debugger', label: 'Debugger', description: 'Debug and diagnose issues' },
  { value: 'researcher', label: 'Researcher', description: 'Research and analyze' },
  { value: 'documenter', label: 'Documenter', description: 'Write documentation' },
];

export function ColumnConfig() {
  const { activeModal, modalData, closeModal, addToast } = useUIStore();
  const { columns, updateColumn: updateColStore } = useBoardStore();

  const open = activeModal === 'column-config';
  const columnId = (modalData as { columnId: string } | null)?.columnId;
  const column = columns.find((c) => c.id === columnId);

  const [agentType, setAgentType] = useState('');
  const [autoRun, setAutoRun] = useState(false);
  const [onSuccessColumnId, setOnSuccessColumnId] = useState('');
  const [onFailureColumnId, setOnFailureColumnId] = useState('');
  const [maxLoopCount, setMaxLoopCount] = useState(1);
  const [promptTemplate, setPromptTemplate] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (column) {
      setAgentType(column.agent_type || '');
      setAutoRun(column.auto_run || false);
      setOnSuccessColumnId(column.on_success_column_id || '');
      setOnFailureColumnId(column.on_failure_column_id || '');
      setMaxLoopCount(column.max_loop_count || 1);
      setPromptTemplate(column.prompt_template || '');
    }
  }, [column]);

  const otherColumns = columns.filter((c) => c.id !== columnId);

  async function handleSave() {
    if (!columnId) return;
    setSaving(true);
    try {
      const updates = {
        agent_type: agentType,
        auto_run: autoRun,
        on_success_column_id: onSuccessColumnId,
        on_failure_column_id: onFailureColumnId,
        max_loop_count: maxLoopCount,
        prompt_template: promptTemplate,
      };
      await updateColumn(columnId, updates);
      updateColStore(columnId, updates);
      addToast('Column automation saved', 'success');
      closeModal();
    } catch {
      addToast('Failed to save column settings', 'error');
    } finally {
      setSaving(false);
    }
  }

  if (!column) return null;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-40 bg-black/30"
            onClick={closeModal}
          />
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 400, damping: 40 }}
            className="fixed right-0 top-0 bottom-0 z-50 w-[400px] glass-surface border-l border-divider flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-divider shrink-0">
              <div className="flex items-center gap-2">
                <Bot size={16} className="text-accent" />
                <h2 className="text-base font-semibold text-text-primary">
                  Column Automation
                </h2>
              </div>
              <button
                onClick={closeModal}
                className="p-1 rounded-md hover:bg-white/5 text-text-secondary hover:text-text-primary transition-colors"
                aria-label="Close panel"
              >
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-6">
              {/* Column indicator */}
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg glass">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: column.color }} />
                <span className="text-sm font-medium text-text-primary">{column.name}</span>
              </div>

              {/* Agent Type */}
              <div>
                <label className="text-xs font-medium text-text-secondary mb-2 block">
                  Agent Type
                </label>
                <div className="grid gap-1.5">
                  {AGENT_TYPES.map((agent) => (
                    <button
                      key={agent.value}
                      onClick={() => setAgentType(agent.value)}
                      className={clsx(
                        'flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all',
                        agentType === agent.value
                          ? 'glass border-accent/40 bg-accent/5'
                          : 'glass glass-hover',
                      )}
                    >
                      {agent.value && (
                        <Bot size={14} className={clsx(
                          agentType === agent.value ? 'text-accent' : 'text-text-muted',
                        )} />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className={clsx(
                          'text-sm font-medium',
                          agentType === agent.value ? 'text-text-primary' : 'text-text-secondary',
                        )}>
                          {agent.label}
                        </p>
                        {agent.description && (
                          <p className="text-[10px] text-text-muted">{agent.description}</p>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Only show remaining fields if agent is selected */}
              {agentType && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="space-y-6"
                >
                  {/* Auto-run toggle */}
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-xs font-medium text-text-secondary block">
                        Auto-run on drop
                      </label>
                      <p className="text-[10px] text-text-muted mt-0.5">
                        Automatically start agent when a card is dragged into this column
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={autoRun}
                        onChange={(e) => setAutoRun(e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 rounded-full bg-white/10 peer-checked:bg-accent/60 transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-transform peer-checked:after:translate-x-4" />
                    </label>
                  </div>

                  {/* On success column */}
                  <div>
                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                      On success, move to
                    </label>
                    <select
                      value={onSuccessColumnId}
                      onChange={(e) => setOnSuccessColumnId(e.target.value)}
                      className="w-full glass-input rounded-lg px-3 py-2 text-sm text-text-primary"
                    >
                      <option value="">Stay in column</option>
                      {otherColumns.map((col) => (
                        <option key={col.id} value={col.id}>{col.name}</option>
                      ))}
                    </select>
                  </div>

                  {/* On failure column */}
                  <div>
                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                      On failure, move to
                    </label>
                    <select
                      value={onFailureColumnId}
                      onChange={(e) => setOnFailureColumnId(e.target.value)}
                      className="w-full glass-input rounded-lg px-3 py-2 text-sm text-text-primary"
                    >
                      <option value="">Stay in column</option>
                      {otherColumns.map((col) => (
                        <option key={col.id} value={col.id}>{col.name}</option>
                      ))}
                    </select>
                  </div>

                  {/* Max loop count */}
                  <div>
                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                      Max loop count
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={maxLoopCount}
                      onChange={(e) => setMaxLoopCount(parseInt(e.target.value) || 1)}
                      className="w-20 glass-input rounded-lg px-3 py-2 text-sm text-text-primary"
                    />
                    <p className="text-[10px] text-text-muted mt-1">
                      Max retries if the agent loops back to this column
                    </p>
                  </div>

                  {/* Prompt template */}
                  <div>
                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                      Prompt template
                    </label>
                    <textarea
                      value={promptTemplate}
                      onChange={(e) => setPromptTemplate(e.target.value)}
                      rows={5}
                      className="w-full glass-input rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted resize-none font-mono"
                      placeholder={`{card_title}\n\n{card_description}\n\nAdditional instructions...`}
                    />
                    <p className="text-[10px] text-text-muted mt-1">
                      Available variables: {'{card_title}'}, {'{card_description}'}, {'{previous_output}'}
                    </p>
                  </div>
                </motion.div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 p-4 border-t border-divider shrink-0">
              <Button variant="ghost" size="sm" onClick={closeModal}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" loading={saving} onClick={handleSave}>
                <Save size={13} />
                Save
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

import { useState, useRef, useEffect } from 'react';
import { Sparkles, Loader2, ChevronDown } from 'lucide-react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { generateCards } from '@/api/boards.ts';

const EXAMPLE_PROMPTS = [
  'Add authentication with login, registration, and password reset',
  'Add unit tests for the API endpoints',
  'Set up CI/CD pipeline with linting, testing, and deployment',
];

interface GenerateCardsModalProps {
  open: boolean;
  onClose: () => void;
  boardId: string;
}

export function GenerateCardsModal({ open, onClose, boardId }: GenerateCardsModalProps) {
  const { addToast } = useUIStore();
  const board = useBoardStore((s) => s.currentBoard);
  const columns = board?.columns || [];

  const [prompt, setPrompt] = useState('');
  const [selectedColumnId, setSelectedColumnId] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Pick a sensible default column when modal opens or columns change
  useEffect(() => {
    if (open && columns.length > 0 && !selectedColumnId) {
      // Prefer a column named "Plan", "Backlog", or "To Do" (case-insensitive)
      const preferred = columns.find((c) =>
        /^(plan|backlog|to\s?do)$/i.test(c.name.trim()),
      );
      setSelectedColumnId(preferred?.id || columns[0].id);
    }
  }, [open, columns, selectedColumnId]);

  // Focus textarea when modal opens; reset state on close
  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => textareaRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
    setPrompt('');
    setSelectedColumnId('');
    setError('');
    setGenerating(false);
  }, [open]);

  function handleExampleClick(example: string) {
    setPrompt(example);
    textareaRef.current?.focus();
  }

  async function handleGenerate() {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      setError('Please describe the tasks you want to generate');
      return;
    }
    if (trimmedPrompt.length < 10) {
      setError('Please provide a more detailed description');
      return;
    }

    setError('');
    setGenerating(true);

    const { setPlanTask } = useBoardStore.getState();

    try {
      const result = await generateCards(boardId, trimmedPrompt, selectedColumnId || undefined);
      setPlanTask({
        taskId: result.task_id,
        status: 'pending',
        progressText: 'Generating tasks...',
      });
      onClose();
    } catch {
      setError('Failed to generate cards. Please try again.');
      addToast('Failed to generate cards', 'error');
    } finally {
      setGenerating(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !generating) {
      e.preventDefault();
      handleGenerate();
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Generate Tasks" width="max-w-xl">
      <div className="space-y-5">
        {/* Description */}
        <p className="text-sm text-text-muted">
          Describe what you want to build and AI will create task cards.
        </p>

        {/* Prompt textarea */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="generate-cards-prompt" className="text-xs font-medium text-text-secondary">
            Prompt
          </label>
          <textarea
            ref={textareaRef}
            id="generate-cards-prompt"
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              if (error) setError('');
            }}
            onKeyDown={handleKeyDown}
            rows={4}
            disabled={generating}
            placeholder="Describe the tasks you want to create..."
            className={[
              'glass-input rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder:text-text-muted',
              'resize-none transition-all duration-150',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              error ? 'border-error/50 focus:border-error' : '',
            ].join(' ')}
          />
          {error && <p className="text-xs text-error">{error}</p>}
        </div>

        {/* Column selector */}
        {columns.length > 1 && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="generate-cards-column" className="text-xs font-medium text-text-secondary">
              Add cards to
            </label>
            <div className="relative">
              <select
                id="generate-cards-column"
                value={selectedColumnId}
                onChange={(e) => setSelectedColumnId(e.target.value)}
                disabled={generating}
                className={[
                  'glass-input w-full rounded-lg px-3 py-2 text-sm text-text-primary',
                  'appearance-none cursor-pointer',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                ].join(' ')}
              >
                {columns.map((col) => (
                  <option key={col.id} value={col.id}>
                    {col.name}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
              />
            </div>
          </div>
        )}

        {/* Example prompts */}
        {!generating && (
          <div className="space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Examples
            </p>
            <div className="space-y-1.5">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => handleExampleClick(example)}
                  className="w-full text-left px-3 py-2 rounded-lg text-xs text-text-secondary hover:text-text-primary glass glass-hover transition-all cursor-pointer"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Generating state */}
        {generating && (
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg glass">
            <Loader2 size={16} className="text-accent animate-spin" />
            <div>
              <p className="text-sm font-medium text-text-primary">Generating tasks...</p>
              <p className="text-xs text-text-secondary mt-0.5">
                AI is creating task cards from your description
              </p>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between pt-1">
          <span className="text-[10px] text-text-muted">
            {!generating && 'Press Cmd+Enter to generate'}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose} disabled={generating}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleGenerate}
              loading={generating}
              disabled={!prompt.trim() || generating}
            >
              <Sparkles size={13} />
              Generate
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

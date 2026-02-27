import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Sparkles, Loader2 } from 'lucide-react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { generateBoard, generateBoardPlan } from '@/api/boards.ts';

const EXAMPLE_PROMPTS = [
  'Build a user authentication system with JWT, refresh tokens, and RBAC',
  'Create a REST API for a blog with posts, comments, and tags',
  'Implement a real-time chat application with WebSocket',
];

interface GenerateBoardModalProps {
  open: boolean;
  onClose: () => void;
  boardId?: string;
}

export function GenerateBoardModal({ open, onClose, boardId }: GenerateBoardModalProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useUIStore();

  const [prompt, setPrompt] = useState('');
  const [name, setName] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Focus textarea when modal opens
  useEffect(() => {
    if (open) {
      // Small delay to let the modal animate in
      const timer = setTimeout(() => textareaRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
    // Reset state when modal closes
    setPrompt('');
    setName('');
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
      setError('Please describe what you want to build');
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
      if (boardId) {
        // Generate plan for existing board
        const result = await generateBoardPlan(boardId, trimmedPrompt);
        setPlanTask({ taskId: result.task_id, status: 'pending', progressText: 'Starting plan generation...' });
        addToast('Board plan is being generated.', 'success');
        onClose();
      } else {
        // Create new board + generate plan
        const trimmedName = name.trim() || undefined;
        const result = await generateBoard({ prompt: trimmedPrompt, name: trimmedName });
        setPlanTask({ taskId: result.task_id, status: 'pending', progressText: 'Starting plan generation...' });
        await queryClient.invalidateQueries({ queryKey: ['boards'] });
        onClose();
        navigate(`/boards/${result.board_id}`);
      }
    } catch {
      setError('Failed to generate board. Please try again.');
      addToast('Board generation failed', 'error');
    } finally {
      setGenerating(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd/Ctrl + Enter to submit
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !generating) {
      e.preventDefault();
      handleGenerate();
    }
  }

  const title = boardId ? 'Generate Plan' : 'Generate Board from Prompt';

  return (
    <Modal open={open} onClose={onClose} title={title} width="max-w-xl">
      <div className="space-y-5">
        {/* Description */}
        <p className="text-sm text-text-secondary">
          {boardId
            ? 'Describe what you want to add to this board. AI will create columns and cards based on your description.'
            : 'Describe your project or feature request and AI will create a board with columns and cards for you.'}
        </p>

        {/* Prompt textarea */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="generate-prompt" className="text-xs font-medium text-text-secondary">
            Prompt
          </label>
          <textarea
            ref={textareaRef}
            id="generate-prompt"
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              if (error) setError('');
            }}
            onKeyDown={handleKeyDown}
            rows={5}
            disabled={generating}
            placeholder="Describe your project or feature request..."
            className={[
              'glass-input rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder:text-text-muted',
              'resize-none transition-all duration-150',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              error ? 'border-error/50 focus:border-error' : '',
            ].join(' ')}
          />
          {error && <p className="text-xs text-error">{error}</p>}
        </div>

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

        {/* Board name (only for new boards) */}
        {!boardId && (
          <Input
            label="Board Name (optional)"
            placeholder="AI will suggest a name if left empty"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={generating}
          />
        )}

        {/* Generating state */}
        {generating && (
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg glass">
            <Loader2 size={16} className="text-accent animate-spin" />
            <div>
              <p className="text-sm font-medium text-text-primary">Planning your board...</p>
              <p className="text-xs text-text-secondary mt-0.5">
                AI is decomposing your request into columns and cards
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

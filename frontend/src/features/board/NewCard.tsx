import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus } from 'lucide-react';
import { createCard } from '@/api/cards.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { useUIStore } from '@/stores/uiStore.ts';

interface NewCardProps {
  columnId: string;
}

export function NewCard({ columnId }: NewCardProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const addCard = useBoardStore((s) => s.addCard);
  const addToast = useUIStore((s) => s.addToast);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function handleCreate() {
    if (!title.trim() || loading) return;
    setLoading(true);
    try {
      const card = await createCard({ column_id: columnId, title: title.trim() });
      addCard(card);
      setTitle('');
      inputRef.current?.focus();
    } catch {
      addToast('Failed to create card', 'error');
    } finally {
      setLoading(false);
    }
  }

  function handleCancel() {
    setOpen(false);
    setTitle('');
  }

  return (
    <div>
      <AnimatePresence mode="wait">
        {open ? (
          <motion.div
            key="form"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.15 }}
          >
            <div className="p-1">
              <input
                ref={inputRef}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate();
                  if (e.key === 'Escape') handleCancel();
                }}
                placeholder="Card title..."
                className="w-full glass-input rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
              />
              <div className="flex items-center justify-between mt-1.5">
                <div className="flex gap-1.5">
                  <button
                    onClick={handleCreate}
                    disabled={loading || !title.trim()}
                    className="text-xs px-2.5 py-1 rounded-md bg-accent/80 hover:bg-accent text-white transition-colors disabled:opacity-40"
                  >
                    {loading ? 'Adding...' : 'Add'}
                  </button>
                  <button
                    onClick={handleCancel}
                    className="text-xs px-2.5 py-1 rounded-md hover:bg-white/5 text-text-secondary transition-colors"
                  >
                    Cancel
                  </button>
                </div>
                <span className="text-[10px] text-text-muted">
                  Enter to add, Esc to cancel
                </span>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.button
            key="trigger"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            onClick={() => setOpen(true)}
            className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-text-muted hover:text-text-secondary hover:bg-white/3 transition-colors"
          >
            <Plus size={13} />
            Add a card...
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}

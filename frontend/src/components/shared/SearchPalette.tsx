import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, CornerDownLeft } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { searchCards, type SearchResult } from '@/api/cards.ts';
import { PriorityBadge } from '@/components/ui/Badge.tsx';
import type { Priority } from '@/types/board.ts';
import clsx from 'clsx';

export function SearchPalette() {
  const { searchOpen, setSearchOpen } = useUIStore();
  const board = useBoardStore((s) => s.currentBoard);
  const openSlideOver = useUIStore((s) => s.openSlideOver);

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchOpen) {
      setQuery('');
      setResults([]);
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [searchOpen]);

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setResults([]);
        return;
      }
      setLoading(true);
      try {
        const r = await searchCards(q, board?.id);
        setResults(r);
        setSelected(0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [board?.id],
  );

  useEffect(() => {
    const timer = setTimeout(() => doSearch(query), 250);
    return () => clearTimeout(timer);
  }, [query, doSearch]);

  function handleSelect(id: string) {
    openSlideOver(id);
    setSearchOpen(false);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === 'Enter' && results[selected]) {
      handleSelect(results[selected].id);
    } else if (e.key === 'Escape') {
      setSearchOpen(false);
    }
  }

  return (
    <AnimatePresence>
      {searchOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.1 }}
          className="fixed inset-0 z-[60] flex items-start justify-center pt-[20vh] bg-overlay/50 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSearchOpen(false);
          }}
        >
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-lg glass rounded-xl shadow-2xl overflow-hidden"
          >
            <div className="flex items-center gap-3 px-4 py-3 border-b border-divider">
              <Search size={16} className="text-text-muted shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search cards..."
                className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
              />
              <kbd className="text-[10px] text-text-muted px-1.5 py-0.5 rounded bg-white/5">esc</kbd>
            </div>

            <div className="max-h-[300px] overflow-y-auto">
              {loading && (
                <div className="p-4 space-y-2">
                  <div className="skeleton h-10 w-full rounded" />
                  <div className="skeleton h-10 w-full rounded" />
                </div>
              )}

              {!loading && results.length === 0 && query.trim() && (
                <div className="py-8 text-center">
                  <p className="text-sm text-text-muted">No cards found</p>
                </div>
              )}

              {!loading &&
                results.map((r, i) => (
                  <button
                    key={r.id}
                    onClick={() => handleSelect(r.id)}
                    className={clsx(
                      'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors',
                      i === selected ? 'bg-accent/10' : 'hover:bg-white/3',
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-text-primary truncate">{r.title}</p>
                      <p className="text-[10px] text-text-muted">{r.column_name}</p>
                    </div>
                    <PriorityBadge priority={r.priority as Priority} />
                    {i === selected && <CornerDownLeft size={12} className="text-text-muted shrink-0" />}
                  </button>
                ))}
            </div>

            {!loading && results.length > 0 && (
              <div className="flex items-center gap-4 px-4 py-2 border-t border-divider text-[10px] text-text-muted">
                <span>
                  <kbd className="px-1 py-0.5 rounded bg-white/5 mr-0.5">&uarr;</kbd>
                  <kbd className="px-1 py-0.5 rounded bg-white/5">
                    &darr;
                  </kbd>{' '}
                  Navigate
                </span>
                <span>
                  <kbd className="px-1 py-0.5 rounded bg-white/5">&crarr;</kbd> Open
                </span>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

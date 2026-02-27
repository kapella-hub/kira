import { useEffect, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';
import { useUIStore, type Toast as ToastType } from '@/stores/uiStore.ts';
import clsx from 'clsx';

const TOAST_DURATION_MS = 4000;

const icons: Record<ToastType['type'], typeof Info> = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
};

const borderStyles: Record<ToastType['type'], string> = {
  success: 'border-success/30',
  error: 'border-error/30',
  info: 'border-accent/30',
};

const iconStyles: Record<ToastType['type'], string> = {
  success: 'text-success',
  error: 'text-error',
  info: 'text-accent',
};

const progressStyles: Record<ToastType['type'], string> = {
  success: 'bg-success/60',
  error: 'bg-error/60',
  info: 'bg-accent/60',
};

function ToastItem({ toast }: { toast: ToastType }) {
  const removeToast = useUIStore((s) => s.removeToast);
  const Icon = icons[toast.type];
  const [progress, setProgress] = useState(100);
  const pausedRef = useRef(false);
  const elapsedRef = useRef(0);
  const lastTickRef = useRef(Date.now());

  const dismiss = useCallback(() => {
    removeToast(toast.id);
  }, [removeToast, toast.id]);

  // Progress countdown using requestAnimationFrame
  useEffect(() => {
    let rafId: number;
    lastTickRef.current = Date.now();

    function tick() {
      const now = Date.now();
      if (!pausedRef.current) {
        elapsedRef.current += now - lastTickRef.current;
      }
      lastTickRef.current = now;

      const remaining = Math.max(0, 100 - (elapsedRef.current / TOAST_DURATION_MS) * 100);
      setProgress(remaining);

      if (remaining > 0) {
        rafId = requestAnimationFrame(tick);
      }
    }

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 60, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 60, scale: 0.95 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className={clsx(
        'glass rounded-lg min-w-[280px] max-w-[380px] overflow-hidden cursor-pointer select-none',
        borderStyles[toast.type],
      )}
      onClick={dismiss}
      onMouseEnter={() => {
        pausedRef.current = true;
      }}
      onMouseLeave={() => {
        pausedRef.current = false;
        lastTickRef.current = Date.now();
      }}
      role="alert"
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <Icon size={16} className={clsx('shrink-0', iconStyles[toast.type])} />
        <span className="text-sm text-text-primary flex-1">{toast.message}</span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            dismiss();
          }}
          className="p-0.5 rounded hover:bg-white/5 text-text-secondary shrink-0"
          aria-label="Dismiss notification"
        >
          <X size={14} />
        </button>
      </div>

      {/* Auto-dismiss progress bar */}
      <div className="h-[2px] w-full bg-white/5">
        <div
          className={clsx('h-full', progressStyles[toast.type])}
          style={{ width: `${progress}%` }}
        />
      </div>
    </motion.div>
  );
}

export function ToastContainer() {
  const toasts = useUIStore((s) => s.toasts);

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem toast={t} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  );
}

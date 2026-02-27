import { useEffect } from 'react';
import { useUIStore } from '@/stores/uiStore.ts';

export function useKeyboard() {
  const { setSearchOpen, slideOverCardId, closeSlideOver, closeModal, activeModal } = useUIStore();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // Cmd/Ctrl+K: toggle search palette
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
        return;
      }

      // Escape: close things in order
      if (e.key === 'Escape') {
        if (activeModal) {
          closeModal();
        } else if (slideOverCardId) {
          closeSlideOver();
        } else {
          setSearchOpen(false);
        }
      }
    }

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setSearchOpen, slideOverCardId, closeSlideOver, closeModal, activeModal]);
}

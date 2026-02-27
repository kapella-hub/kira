import { create } from 'zustand';
import type { AuthConfig } from '@/types/user.ts';
import type { User } from '@/types/user.ts';

function loadUser(): User | null {
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

interface AuthState {
  user: User | null;
  token: string | null;
  authConfig: AuthConfig | null;
  setAuth: (user: User, token: string) => void;
  updateUser: (updates: Partial<User>) => void;
  setAuthConfig: (config: AuthConfig) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: loadUser(),
  token: localStorage.getItem('token'),
  authConfig: null,

  setAuth: (user, token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    set({ user, token });
  },

  updateUser: (updates) => {
    const current = get().user;
    if (!current) return;
    const updated = { ...current, ...updates };
    localStorage.setItem('user', JSON.stringify(updated));
    set({ user: updated });
  },

  setAuthConfig: (config) => {
    set({ authConfig: config });
  },

  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    set({ user: null, token: null });
  },

  isAuthenticated: () => !!get().token,
}));

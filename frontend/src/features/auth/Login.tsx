import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Zap, ArrowRight, Shield, Loader2 } from 'lucide-react';
import { login, getAuthConfig } from '@/api/auth.ts';
import { useAuthStore } from '@/stores/authStore.ts';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';

const DEMO_COLORS = [
  'bg-indigo-500/30',
  'bg-emerald-500/30',
  'bg-amber-500/30',
];

function getInitial(name: string): string {
  return name.charAt(0).toUpperCase();
}

export function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingUser, setLoadingUser] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [configLoading, setConfigLoading] = useState(true);
  const { setAuth, authConfig, setAuthConfig } = useAuthStore();
  const navigate = useNavigate();

  const isCentAuth = authConfig?.auth_mode === 'centauth';
  const demoUsers = authConfig?.demo_users ?? [];

  useEffect(() => {
    let cancelled = false;
    getAuthConfig()
      .then((config) => {
        if (!cancelled) {
          setAuthConfig(config);
          setConfigLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setConfigLoading(false);
      });
    return () => { cancelled = true; };
  }, [setAuthConfig]);

  async function handleLogin(name: string, pw?: string) {
    setLoading(true);
    setLoadingUser(name);
    setError('');
    try {
      const res = await login(name, pw);
      setAuth(res.user, res.token);
      navigate('/');
    } catch {
      setError(
        isCentAuth
          ? 'Invalid credentials. Check your username and password.'
          : 'Failed to sign in. Is the server running?'
      );
    } finally {
      setLoading(false);
      setLoadingUser(null);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg relative overflow-hidden">
      {/* Animated background gradient */}
      <div
        className="absolute inset-0 animate-gradient opacity-30"
        style={{
          background:
            'linear-gradient(135deg, #0a0a0f 0%, #1a1040 25%, #0a0a0f 50%, #0f2027 75%, #0a0a0f 100%)',
          backgroundSize: '400% 400%',
        }}
      />
      {/* Radial glow behind card */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(129,140,248,0.08)_0%,transparent_70%)]" />

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="relative glass rounded-2xl p-8 w-full max-w-sm shadow-2xl"
      >
        {/* Branding */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-accent/20 flex items-center justify-center mb-4 shadow-[0_0_24px_rgba(129,140,248,0.15)]">
            <Zap size={24} className="text-accent" />
          </div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Kira</h1>
          <p className="text-xs text-text-muted mt-1 tracking-wide uppercase">
            AI-Powered Kanban Board
          </p>
        </div>

        {configLoading ? (
          <div className="flex flex-col items-center gap-3 py-8">
            <Loader2 size={20} className="text-text-muted animate-spin" />
            <p className="text-xs text-text-muted">Connecting to server...</p>
          </div>
        ) : (
          <>
            {/* Auth mode badge */}
            {isCentAuth && (
              <div className="flex items-center justify-center gap-1.5 mb-5">
                <Shield size={12} className="text-accent" />
                <span className="text-[10px] font-semibold uppercase tracking-wider text-accent">
                  SSO Authentication
                </span>
              </div>
            )}

            {/* Sign in form */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (username.trim()) handleLogin(username.trim(), password);
              }}
              className="flex flex-col gap-3"
            >
              <Input
                placeholder={isCentAuth ? 'Username' : 'Enter your name'}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                aria-label="Username"
              />
              {isCentAuth && (
                <Input
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-label="Password"
                />
              )}
              {error && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-error"
                >
                  {error}
                </motion.p>
              )}
              <Button
                type="submit"
                variant="primary"
                loading={loading && loadingUser === username.trim()}
                disabled={!username.trim() || (isCentAuth && !password) || loading}
                className="w-full"
              >
                <span>Sign In</span>
                <ArrowRight size={14} />
              </Button>
            </form>

            {/* Demo users section (mock mode only) */}
            {demoUsers.length > 0 && (
              <>
                <div className="flex items-center gap-3 my-6">
                  <div className="flex-1 h-px bg-divider" />
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    Quick access
                  </span>
                  <div className="flex-1 h-px bg-divider" />
                </div>

                <div className="flex gap-2">
                  {demoUsers.map((name, i) => (
                    <motion.button
                      key={name}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => handleLogin(name)}
                      disabled={loading}
                      className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-text-secondary glass glass-hover transition-all disabled:opacity-40"
                    >
                      <span
                        className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-semibold text-text-primary ${DEMO_COLORS[i % DEMO_COLORS.length]}`}
                      >
                        {getInitial(name)}
                      </span>
                      <span className="capitalize">{name}</span>
                      {loading && loadingUser === name && (
                        <svg className="animate-spin h-3 w-3 ml-auto" viewBox="0 0 24 24" fill="none">
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                          />
                        </svg>
                      )}
                    </motion.button>
                  ))}
                </div>
              </>
            )}

            {/* Footer note */}
            <p className="text-[10px] text-text-muted text-center mt-6">
              {isCentAuth
                ? 'Sign in with your corporate credentials'
                : 'New users are created automatically on first sign in.'}
            </p>
          </>
        )}
      </motion.div>
    </div>
  );
}

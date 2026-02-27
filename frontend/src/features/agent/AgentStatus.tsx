import { useState, useEffect, useRef, useCallback } from 'react';
import { Cpu, Copy, Check, Download } from 'lucide-react';
import { useAgentStore } from '@/stores/agentStore.ts';
import type { AgentState } from '@/stores/agentStore.ts';
import { get } from '@/api/client.ts';
import clsx from 'clsx';

interface AgentVersionInfo {
  version: string;
  install_url: string;
}

interface StateConfig {
  color: string;
  label: string;
  pulse: boolean;
}

const STATE_CONFIG: Record<AgentState, StateConfig> = {
  disconnected: { color: 'bg-text-muted', label: 'Agent offline', pulse: false },
  connecting: { color: 'bg-amber-400', label: 'Connecting...', pulse: true },
  dormant: { color: 'bg-amber-400', label: 'Agent idle', pulse: false },
  activating: { color: 'bg-amber-400', label: 'Activating...', pulse: true },
  active: { color: 'bg-success', label: 'Agent active', pulse: false },
  deactivating: { color: 'bg-amber-400', label: 'Deactivating...', pulse: true },
};

const AUTODOWNLOAD_KEY = 'kira-agent-autodownload';

export function AgentStatus() {
  const agentState = useAgentStore((s) => s.agentState);
  const runningTasks = useAgentStore((s) => s.runningTasks);
  const error = useAgentStore((s) => s.error);
  const upgradeAvailable = useAgentStore((s) => s.upgradeAvailable);
  const [showTooltip, setShowTooltip] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedUpgrade, setCopiedUpgrade] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const config = STATE_CONFIG[agentState];
  const isDisconnected = agentState === 'disconnected';
  const isActive = agentState === 'active';

  // Fetch the real server URL from the backend (avoids localhost:5173 in dev)
  const [serverUrl, setServerUrl] = useState('');
  useEffect(() => {
    if (!isDisconnected) return;
    get<AgentVersionInfo>('/agent/version')
      .then((info) => setServerUrl(info.install_url))
      .catch(() => {});
  }, [isDisconnected]);

  const installCmd = serverUrl
    ? `curl -sSL ${serverUrl}/api/agent/install.sh | bash`
    : '';
  const downloadUrl = '/api/agent/install.command';

  const upgradeCmd = upgradeAvailable
    ? `curl -sSL ${upgradeAvailable.installUrl}/api/agent/install.sh | bash`
    : '';

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(installCmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [installCmd]);

  const handleCopyUpgrade = useCallback(async () => {
    if (!upgradeCmd) return;
    await navigator.clipboard.writeText(upgradeCmd);
    setCopiedUpgrade(true);
    setTimeout(() => setCopiedUpgrade(false), 2000);
  }, [upgradeCmd]);

  // Close tooltip on outside click
  useEffect(() => {
    if (!showTooltip) return;
    function handler(e: MouseEvent) {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node)) {
        setShowTooltip(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showTooltip]);

  // Auto-download on first tooltip open when agent is disconnected
  useEffect(() => {
    if (!showTooltip || !isDisconnected) return;
    if (sessionStorage.getItem(AUTODOWNLOAD_KEY)) return;

    const timer = setTimeout(() => {
      sessionStorage.setItem(AUTODOWNLOAD_KEY, '1');
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }, 1000);

    return () => clearTimeout(timer);
  }, [showTooltip, isDisconnected, downloadUrl]);

  // Derive display label
  const displayLabel =
    isActive && runningTasks > 0
      ? `${runningTasks} task${runningTasks > 1 ? 's' : ''}`
      : config.label;

  return (
    <div className="relative" ref={tooltipRef}>
      {/* Compact status button */}
      <button
        onClick={() => setShowTooltip((s) => !s)}
        className={clsx(
          'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors',
          'glass glass-hover cursor-pointer',
        )}
        aria-label={displayLabel}
      >
        <span className="relative flex h-2 w-2">
          {config.pulse && (
            <span
              className={clsx(
                'animate-ping absolute inline-flex h-full w-full rounded-full opacity-50',
                config.color,
              )}
            />
          )}
          {isActive && runningTasks > 0 && !config.pulse && (
            <span
              className={clsx(
                'animate-ping absolute inline-flex h-full w-full rounded-full opacity-50',
                config.color,
              )}
            />
          )}
          <span
            className={clsx('relative inline-flex rounded-full h-2 w-2', config.color)}
          />
        </span>
        <Cpu size={12} className="text-text-secondary" />
        <span className="text-text-secondary hidden sm:inline">{displayLabel}</span>
        {/* Upgrade indicator dot */}
        {upgradeAvailable && (
          <span className="relative flex h-1.5 w-1.5 ml-0.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-50" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-amber-400" />
          </span>
        )}
      </button>

      {/* Tooltip dropdown */}
      {showTooltip && (
        <div className="absolute right-0 mt-1 z-50 w-80 rounded-lg glass shadow-xl py-2 px-3">
          <div className="flex items-center gap-2 pb-2 border-b border-divider">
            <Cpu size={13} className={isDisconnected ? 'text-text-muted' : 'text-accent'} />
            <span className="text-xs font-medium text-text-primary">Local Agent</span>
          </div>

          <div className="space-y-1.5 pt-2 text-[11px]">
            <div className="flex justify-between">
              <span className="text-text-muted">Status</span>
              <span className={isDisconnected ? 'text-text-muted' : 'text-text-primary'}>
                {config.label}
              </span>
            </div>

            {isActive && (
              <div className="flex justify-between">
                <span className="text-text-muted">Tasks</span>
                <span className="text-text-primary">{runningTasks} running</span>
              </div>
            )}

            {error && (
              <div className="mt-1.5 px-2 py-1.5 rounded bg-error/10 text-error text-[10px]">
                {error}
              </div>
            )}
          </div>

          {/* Upgrade available banner */}
          {upgradeAvailable && (
            <div className="mt-3 pt-2 border-t border-divider space-y-2">
              <div className="flex items-center gap-1.5">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-amber-400" />
                <span className="text-[11px] font-medium text-amber-400">
                  Update available: v{upgradeAvailable.currentVersion} → v{upgradeAvailable.serverVersion}
                </span>
              </div>
              <div className="relative group">
                <code className="block px-2.5 py-2 pr-8 rounded bg-white/[0.04] text-[10px] text-text-secondary font-mono break-all leading-relaxed select-all">
                  {upgradeCmd}
                </code>
                <button
                  onClick={handleCopyUpgrade}
                  className="absolute top-1.5 right-1.5 p-1 rounded glass-hover text-text-muted hover:text-text-primary transition-colors"
                  title="Copy to clipboard"
                >
                  {copiedUpgrade ? <Check size={11} className="text-success" /> : <Copy size={11} />}
                </button>
              </div>
            </div>
          )}

          {isDisconnected && (
            <div className="mt-3 pt-2 border-t border-divider space-y-2.5">
              <p className="text-[10px] text-text-muted">
                The local agent runs AI tasks using your machine's credentials.
                Install it once — it auto-starts on login.
              </p>

              {/* Curl command (primary) */}
              <div className="relative group">
                <code className="block px-2.5 py-2 pr-8 rounded bg-white/[0.04] text-[10px] text-text-secondary font-mono break-all leading-relaxed select-all">
                  {installCmd}
                </code>
                <button
                  onClick={handleCopy}
                  className="absolute top-1.5 right-1.5 p-1 rounded glass-hover text-text-muted hover:text-text-primary transition-colors"
                  title="Copy to clipboard"
                >
                  {copied ? <Check size={11} className="text-success" /> : <Copy size={11} />}
                </button>
              </div>

              {/* Divider with "or" */}
              <div className="flex items-center gap-2">
                <div className="flex-1 border-t border-divider" />
                <span className="text-[9px] text-text-muted uppercase tracking-wider">or download</span>
                <div className="flex-1 border-t border-divider" />
              </div>

              {/* One-click download (fallback) */}
              <div className="flex items-center gap-2">
                <a
                  href={downloadUrl}
                  className="flex items-center justify-center gap-2 flex-1 px-3 py-2 rounded-md bg-accent/20 hover:bg-accent/30 text-accent text-[11px] font-medium transition-colors"
                >
                  <Download size={13} />
                  Download Installer
                </a>
              </div>
              <p className="text-[9px] text-text-muted">
                macOS: right-click → Open if blocked
              </p>

              <p className="text-[9px] text-text-muted">
                Requires Python 3.12+ · macOS or Linux · Installs to ~/.kira/
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

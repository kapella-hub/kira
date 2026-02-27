import { Gitlab, Settings, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import type { GitLabSettings } from '@/types/gitlab.ts';

interface GitLabBadgeProps {
  settings: GitLabSettings | null;
}

export function GitLabBadge({ settings }: GitLabBadgeProps) {
  const { openModal } = useUIStore();

  if (!settings) {
    return (
      <Button variant="ghost" size="sm" onClick={() => openModal('gitlab-project-picker')}>
        <Gitlab size={14} />
        Link GitLab
      </Button>
    );
  }

  return (
    <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg glass text-xs">
      <Gitlab size={12} className="text-orange-400 shrink-0" />
      <a
        href={settings.project_url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-text-primary hover:text-accent transition-colors truncate max-w-[200px] inline-flex items-center gap-1"
      >
        {settings.project_path}
        <ExternalLink size={10} className="shrink-0 text-text-muted" />
      </a>
      <button
        onClick={() => openModal('gitlab-project-picker')}
        className="p-0.5 rounded hover:bg-white/5 text-text-muted hover:text-text-primary transition-colors"
        aria-label="Change GitLab project"
      >
        <Settings size={11} />
      </button>
    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import { Search, ExternalLink } from 'lucide-react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import {
  fetchGitLabProjects,
  fetchGitLabNamespaces,
  linkGitLabProject,
  createGitLabProject,
} from '@/api/gitlab.ts';
import type { GitLabProject, GitLabNamespace } from '@/types/gitlab.ts';

type Tab = 'existing' | 'new';

export function GitLabProjectPicker() {
  const { activeModal, closeModal, addToast } = useUIStore();
  const board = useBoardStore((s) => s.currentBoard);
  const open = activeModal === 'gitlab-project-picker';

  const [tab, setTab] = useState<Tab>('existing');

  // -- Existing project tab --
  const [searchQuery, setSearchQuery] = useState('');
  const [projects, setProjects] = useState<GitLabProject[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [selectedProject, setSelectedProject] = useState<GitLabProject | null>(null);
  const [autoPushExisting, setAutoPushExisting] = useState(false);
  const [pushOnCompleteExisting, setPushOnCompleteExisting] = useState(true);
  const [linking, setLinking] = useState(false);

  // -- New project tab --
  const [newName, setNewName] = useState('');
  const [namespaces, setNamespaces] = useState<GitLabNamespace[]>([]);
  const [loadingNamespaces, setLoadingNamespaces] = useState(false);
  const [selectedNamespace, setSelectedNamespace] = useState<number | ''>('');
  const [visibility, setVisibility] = useState<'private' | 'internal' | 'public'>('private');
  const [description, setDescription] = useState('');
  const [autoPushNew, setAutoPushNew] = useState(false);
  const [pushOnCompleteNew, setPushOnCompleteNew] = useState(true);
  const [creating, setCreating] = useState(false);

  const loadProjects = useCallback(async (search: string) => {
    setLoadingProjects(true);
    try {
      const data = await fetchGitLabProjects(search || undefined);
      setProjects(data);
    } catch {
      setProjects([]);
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  // Load projects on open and debounced search
  useEffect(() => {
    if (!open) return;
    setSelectedProject(null);
    setSearchQuery('');
    setNewName('');
    setDescription('');
    setSelectedNamespace('');
    loadProjects('');
  }, [open, loadProjects]);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      loadProjects(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, open, loadProjects]);

  // Load namespaces when switching to "new" tab
  useEffect(() => {
    if (!open || tab !== 'new') return;
    if (namespaces.length > 0) return;
    setLoadingNamespaces(true);
    fetchGitLabNamespaces()
      .then((data) => {
        setNamespaces(data);
        if (data.length > 0 && selectedNamespace === '') {
          setSelectedNamespace(data[0].id);
        }
      })
      .catch(() => setNamespaces([]))
      .finally(() => setLoadingNamespaces(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, tab]);

  async function handleLink() {
    if (!selectedProject || !board) return;
    setLinking(true);
    try {
      await linkGitLabProject({
        project_id: selectedProject.id,
        project_path: selectedProject.path_with_namespace,
        project_url: selectedProject.web_url,
        default_branch: selectedProject.default_branch,
        auto_push: autoPushExisting,
        push_on_complete: pushOnCompleteExisting,
      });
      addToast(`Linked to ${selectedProject.path_with_namespace}`, 'success');
      closeModal();
    } catch {
      addToast('Failed to link project', 'error');
    } finally {
      setLinking(false);
    }
  }

  async function handleCreate() {
    if (!newName.trim() || !selectedNamespace || !board) return;
    setCreating(true);
    try {
      const result = await createGitLabProject({
        name: newName.trim(),
        namespace_id: selectedNamespace as number,
        visibility,
        description: description.trim() || undefined,
        auto_push: autoPushNew,
        push_on_complete: pushOnCompleteNew,
      });
      addToast(`Project creation queued (task ${result.task_id})`, 'success');
      closeModal();
    } catch {
      addToast('Failed to create project', 'error');
    } finally {
      setCreating(false);
    }
  }

  return (
    <Modal open={open} onClose={closeModal} title="GitLab Project" width="max-w-xl">
      <div className="space-y-4">
        {/* Tabs */}
        <div className="flex gap-1 p-0.5 rounded-lg bg-white/[0.03]">
          <button
            onClick={() => setTab('existing')}
            className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              tab === 'existing'
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
            }`}
          >
            Existing Project
          </button>
          <button
            onClick={() => setTab('new')}
            className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              tab === 'new'
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
            }`}
          >
            New Project
          </button>
        </div>

        {tab === 'existing' && (
          <div className="space-y-3">
            {/* Search */}
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search projects..."
                className="glass-input w-full rounded-lg pl-9 pr-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
              />
            </div>

            {/* Project list */}
            <div className="max-h-60 overflow-y-auto space-y-1 rounded-lg">
              {loadingProjects && projects.length === 0 && (
                <div className="space-y-2 p-1">
                  <div className="skeleton h-12 w-full rounded-lg" />
                  <div className="skeleton h-12 w-full rounded-lg" />
                  <div className="skeleton h-12 w-full rounded-lg" />
                </div>
              )}

              {!loadingProjects && projects.length === 0 && (
                <p className="text-xs text-text-muted text-center py-6">
                  {searchQuery ? 'No projects match your search' : 'No projects found'}
                </p>
              )}

              {projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setSelectedProject(p)}
                  className={`w-full text-left p-3 rounded-lg transition-all ${
                    selectedProject?.id === p.id
                      ? 'bg-accent/10 border border-accent/30'
                      : 'hover:bg-white/5 border border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">{p.name}</p>
                      <p className="text-xs text-text-secondary truncate">{p.path_with_namespace}</p>
                    </div>
                    <a
                      href={p.web_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="p-1 rounded hover:bg-white/5 text-text-muted hover:text-text-primary transition-colors shrink-0"
                      aria-label={`Open ${p.name} in new tab`}
                    >
                      <ExternalLink size={12} />
                    </a>
                  </div>
                </button>
              ))}
            </div>

            {/* Git Push Automation */}
            <div className="border-t border-divider pt-3 mt-1">
              <p className="text-xs font-medium text-text-secondary mb-2">Git Push Automation</p>
              <div className="space-y-2.5">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoPushExisting}
                    onChange={(e) => setAutoPushExisting(e.target.checked)}
                    className="rounded border-divider bg-white/5 text-accent focus:ring-accent/40 mt-0.5"
                  />
                  <div>
                    <span className="text-xs text-text-primary">Push after each code step</span>
                    <p className="text-[10px] text-text-muted leading-tight">
                      Pushes changes to a branch after every code generation task
                    </p>
                  </div>
                </label>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pushOnCompleteExisting}
                    onChange={(e) => setPushOnCompleteExisting(e.target.checked)}
                    className="rounded border-divider bg-white/5 text-accent focus:ring-accent/40 mt-0.5"
                  />
                  <div>
                    <span className="text-xs text-text-primary">Push & create MR when pipeline completes</span>
                    <p className="text-[10px] text-text-muted leading-tight">
                      Creates a merge request when the card reaches Done
                    </p>
                  </div>
                </label>
              </div>
            </div>

            {/* Link button */}
            <div className="flex justify-end pt-1">
              <Button
                variant="primary"
                size="sm"
                onClick={handleLink}
                loading={linking}
                disabled={!selectedProject}
              >
                Link Project
              </Button>
            </div>
          </div>
        )}

        {tab === 'new' && (
          <div className="space-y-3">
            <Input
              label="Project Name"
              placeholder="my-project"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />

            {/* Namespace selector */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-secondary">Namespace</label>
              {loadingNamespaces ? (
                <div className="skeleton h-9 w-full rounded-lg" />
              ) : (
                <select
                  value={selectedNamespace}
                  onChange={(e) => setSelectedNamespace(Number(e.target.value))}
                  className="glass-input rounded-lg px-3 py-2 text-sm text-text-primary"
                >
                  <option value="">Select a namespace</option>
                  {namespaces.map((ns) => (
                    <option key={ns.id} value={ns.id}>
                      {ns.name} ({ns.kind})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Visibility selector */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-secondary">Visibility</label>
              <div className="flex gap-1.5">
                {(['private', 'internal', 'public'] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setVisibility(v)}
                    className={`flex-1 px-2.5 py-1.5 text-xs font-medium rounded-lg border transition-all capitalize ${
                      visibility === v
                        ? 'bg-accent/10 border-accent/30 text-accent'
                        : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-white/5'
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>

            <Input
              label="Description (optional)"
              placeholder="A brief description of the project"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />

            {/* Git Push Automation */}
            <div className="border-t border-divider pt-3 mt-1">
              <p className="text-xs font-medium text-text-secondary mb-2">Git Push Automation</p>
              <div className="space-y-2.5">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoPushNew}
                    onChange={(e) => setAutoPushNew(e.target.checked)}
                    className="rounded border-divider bg-white/5 text-accent focus:ring-accent/40 mt-0.5"
                  />
                  <div>
                    <span className="text-xs text-text-primary">Push after each code step</span>
                    <p className="text-[10px] text-text-muted leading-tight">
                      Pushes changes to a branch after every code generation task
                    </p>
                  </div>
                </label>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pushOnCompleteNew}
                    onChange={(e) => setPushOnCompleteNew(e.target.checked)}
                    className="rounded border-divider bg-white/5 text-accent focus:ring-accent/40 mt-0.5"
                  />
                  <div>
                    <span className="text-xs text-text-primary">Push & create MR when pipeline completes</span>
                    <p className="text-[10px] text-text-muted leading-tight">
                      Creates a merge request when the card reaches Done
                    </p>
                  </div>
                </label>
              </div>
            </div>

            {/* Create button */}
            <div className="flex justify-end pt-1">
              <Button
                variant="primary"
                size="sm"
                onClick={handleCreate}
                loading={creating}
                disabled={!newName.trim() || !selectedNamespace}
              >
                Create & Link
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

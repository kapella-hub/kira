import { Search, LogOut, UserCircle } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore.ts';
import { useUIStore } from '@/stores/uiStore.ts';
import { Avatar } from '@/components/ui/Avatar.tsx';
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown.tsx';
import { WorkerStatus } from '@/features/board/WorkerStatus.tsx';
import { AgentStatus } from '@/features/agent/AgentStatus.tsx';
import { useNavigate } from 'react-router-dom';

export function Header() {
  const { user, logout } = useAuthStore();
  const { setSearchOpen, openModal } = useUIStore();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate('/login');
  }

  return (
    <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-divider glass-surface">
      <div />
      <div className="flex items-center gap-3">
        <AgentStatus />
        <WorkerStatus />

        <button
          onClick={() => setSearchOpen(true)}
          className="flex items-center gap-2 px-2.5 py-1 rounded-md glass glass-hover text-text-secondary text-xs"
        >
          <Search size={13} />
          <span className="hidden sm:inline">Search</span>
          <kbd className="hidden sm:inline ml-1 px-1 py-0.5 rounded bg-white/5 text-[10px] text-text-muted">
            {'\u2318'}K
          </kbd>
        </button>

        {user && (
          <Dropdown
            align="right"
            trigger={
              <button className="flex items-center gap-2 cursor-pointer">
                <Avatar name={user.display_name} size="sm" />
                <span className="text-xs text-text-secondary hidden sm:inline">{user.display_name}</span>
              </button>
            }
          >
            <div className="px-3 py-2 border-b border-divider">
              <p className="text-xs font-medium text-text-primary">{user.display_name}</p>
              <p className="text-[10px] text-text-muted">@{user.username}</p>
            </div>
            <DropdownItem onClick={() => openModal('user-profile')}>
              <span className="flex items-center gap-2">
                <UserCircle size={13} /> Profile
              </span>
            </DropdownItem>
            <DropdownItem onClick={handleLogout}>
              <span className="flex items-center gap-2">
                <LogOut size={13} /> Sign out
              </span>
            </DropdownItem>
          </Dropdown>
        )}
      </div>
    </header>
  );
}

import { useState } from 'react';
import { UserPlus, X, Shield, Eye, User } from 'lucide-react';
import { Modal } from '@/components/ui/Modal.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { Avatar } from '@/components/ui/Avatar.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import clsx from 'clsx';

interface Member {
  user_id: string;
  username: string;
  display_name: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
}

const roleIcons = {
  owner: Shield,
  admin: Shield,
  member: User,
  viewer: Eye,
};

const roleColors = {
  owner: 'text-accent',
  admin: 'text-warning',
  member: 'text-text-secondary',
  viewer: 'text-text-muted',
};

// Mock members for now until backend provides real data
const MOCK_MEMBERS: Member[] = [
  { user_id: '1', username: 'alice', display_name: 'Alice', role: 'owner' },
  { user_id: '2', username: 'bob', display_name: 'Bob', role: 'member' },
  { user_id: '3', username: 'charlie', display_name: 'Charlie', role: 'viewer' },
];

export function BoardMembers() {
  const { activeModal, closeModal, addToast } = useUIStore();
  const open = activeModal === 'board-members';

  const [members] = useState<Member[]>(MOCK_MEMBERS);
  const [inviteUsername, setInviteUsername] = useState('');

  function handleInvite() {
    if (!inviteUsername.trim()) return;
    addToast(`Invited ${inviteUsername}`, 'success');
    setInviteUsername('');
  }

  function handleRemove(member: Member) {
    addToast(`Removed ${member.display_name}`, 'info');
  }

  return (
    <Modal open={open} onClose={closeModal} title="Board Members">
      <div className="space-y-4">
        {/* Invite */}
        <div className="flex gap-2">
          <Input
            placeholder="Username to invite..."
            value={inviteUsername}
            onChange={(e) => setInviteUsername(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleInvite();
            }}
            className="flex-1"
          />
          <Button variant="primary" size="sm" onClick={handleInvite} disabled={!inviteUsername.trim()}>
            <UserPlus size={13} />
            Invite
          </Button>
        </div>

        {/* Member list */}
        <div className="space-y-1">
          {members.map((member) => {
            const RoleIcon = roleIcons[member.role];
            return (
              <div
                key={member.user_id}
                className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/3 transition-colors"
              >
                <Avatar name={member.display_name} size="sm" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">{member.display_name}</p>
                  <p className="text-[10px] text-text-muted">@{member.username}</p>
                </div>
                <div className={clsx('flex items-center gap-1 text-xs', roleColors[member.role])}>
                  <RoleIcon size={12} />
                  <span className="capitalize">{member.role}</span>
                </div>
                {member.role !== 'owner' && (
                  <button
                    onClick={() => handleRemove(member)}
                    className="p-1 rounded hover:bg-white/5 text-text-muted hover:text-error transition-colors"
                    aria-label={`Remove ${member.display_name}`}
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Modal>
  );
}

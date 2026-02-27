import { type ReactNode } from 'react';
import { Sidebar } from './Sidebar.tsx';
import { Header } from './Header.tsx';
import { useKeyboard } from '@/hooks/useKeyboard.ts';
import { useAgentConnection } from '@/hooks/useAgentConnection.ts';

export function Layout({ children }: { children: ReactNode }) {
  useKeyboard();
  useAgentConnection();

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}

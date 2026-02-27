import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';
import { useAuthStore } from '@/stores/authStore.ts';
import { useUIStore } from '@/stores/uiStore.ts';
import { Layout } from '@/components/layout/Layout.tsx';
import { ToastContainer } from '@/components/ui/Toast.tsx';
import { SearchPalette } from '@/components/shared/SearchPalette.tsx';
import { Login } from '@/features/auth/Login.tsx';
import { Board } from '@/features/board/Board.tsx';
import { JiraSettings } from '@/features/jira/JiraSettings.tsx';
import { JiraImport } from '@/features/jira/JiraImport.tsx';
import { GitLabSettings } from '@/features/gitlab/GitLabSettings.tsx';
import { GitLabProjectPicker } from '@/features/gitlab/GitLabProjectPicker.tsx';
import { UserProfile } from '@/features/auth/UserProfile.tsx';
import { BoardMembers } from '@/features/board/BoardMembers.tsx';
import { ColumnConfig } from '@/features/board/ColumnConfig.tsx';
import { GenerateBoardModal } from '@/features/board/GenerateBoardModal.tsx';
import { GenerateCardsModal } from '@/features/board/GenerateCardsModal.tsx';
import { WorkspaceSettings } from '@/features/workspace/WorkspaceSettings.tsx';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function ProtectedRoute({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function BoardShell() {
  const { id } = useParams<{ id: string }>();
  const { activeModal, closeModal } = useUIStore();

  // "generate-board" = create new board, "generate-board-plan" = plan for current board
  const generateModalOpen = activeModal === 'generate-board' || activeModal === 'generate-board-plan';
  const generateBoardId = activeModal === 'generate-board-plan' ? id : undefined;

  return (
    <Layout>
      <Board />
      {/* Global modals */}
      <JiraSettings />
      <JiraImport />
      <GitLabSettings />
      <GitLabProjectPicker />
      <ColumnConfig />
      <UserProfile />
      <BoardMembers />
      <WorkspaceSettings />
      <SearchPalette />
      <GenerateBoardModal
        open={generateModalOpen}
        onClose={closeModal}
        boardId={generateBoardId}
      />
      <GenerateCardsModal
        open={activeModal === 'generate-cards'}
        onClose={closeModal}
        boardId={id || ''}
      />
    </Layout>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/boards/:id"
            element={
              <ProtectedRoute>
                <BoardShell />
              </ProtectedRoute>
            }
          />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <BoardShell />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <ToastContainer />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

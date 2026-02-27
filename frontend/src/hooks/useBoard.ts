import { useQuery } from '@tanstack/react-query';
import { fetchBoard, fetchBoards } from '@/api/boards.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { useEffect } from 'react';

export function useBoards() {
  const setBoards = useBoardStore((s) => s.setBoards);
  const query = useQuery({
    queryKey: ['boards'],
    queryFn: fetchBoards,
  });

  useEffect(() => {
    if (query.data) {
      setBoards(query.data);
    }
  }, [query.data, setBoards]);

  return query;
}

export function useBoardData(boardId: string | undefined) {
  const setCurrentBoard = useBoardStore((s) => s.setCurrentBoard);
  const query = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => fetchBoard(boardId!),
    enabled: !!boardId,
  });

  useEffect(() => {
    if (query.data) {
      setCurrentBoard(query.data);
    }
  }, [query.data, setCurrentBoard]);

  return query;
}

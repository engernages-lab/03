import { create } from "zustand";
import type { DualNotationResponse, EditOperation, MusicDocument } from "../lib/types";

const HISTORY_LIMIT = 50;

/**
 * Document editor state.
 *
 * The backend document is the single source of truth: every edit is applied
 * server-side and the response replaces the local copy.  Undo/redo therefore
 * keeps *document snapshots* - restoring any snapshot rebuilds both notations,
 * so the grid and jianpu views can never diverge.
 */
export interface DocumentState {
  document: MusicDocument | null;
  view: DualNotationResponse | null;
  past: MusicDocument[];
  future: MusicDocument[];
  pending: boolean;
  lastError: string | null;
}

export interface DocumentActions {
  load: (view: DualNotationResponse) => void;
  applyEditResult: (view: DualNotationResponse) => void;
  setPending: (pending: boolean) => void;
  setError: (message: string | null) => void;
  undo: () => MusicDocument | null;
  redo: () => MusicDocument | null;
  canUndo: () => boolean;
  canRedo: () => boolean;
  reset: () => void;
  setDocumentLocal: (document: MusicDocument) => void;
}

export const useDocumentStore = create<DocumentState & DocumentActions>((set, get) => ({
  document: null,
  view: null,
  past: [],
  future: [],
  pending: false,
  lastError: null,

  load: (view) =>
    set({
      document: view.document,
      view,
      past: [],
      future: [],
      pending: false,
      lastError: null,
    }),

  applyEditResult: (view) =>
    set((state) => {
      const previous = state.document;
      if (!previous) {
        return { document: view.document, view, past: [], future: [] };
      }
      const past = [...state.past, previous].slice(-HISTORY_LIMIT);
      return {
        document: view.document,
        view,
        past,
        future: [],
        pending: false,
        lastError: null,
      };
    }),

  setPending: (pending) => set({ pending }),
  setError: (message) => set({ lastError: message, pending: false }),

  undo: () => {
    const { past, document, future } = get();
    if (past.length === 0 || !document) return null;
    const previous = past[past.length - 1];
    set({
      document: previous,
      past: past.slice(0, -1),
      future: [document, ...future].slice(0, HISTORY_LIMIT),
      lastError: null,
    });
    return previous;
  },

  redo: () => {
    const { future, document, past } = get();
    if (future.length === 0 || !document) return null;
    const next = future[0];
    set({
      document: next,
      future: future.slice(1),
      past: [...past, document].slice(-HISTORY_LIMIT),
      lastError: null,
    });
    return next;
  },

  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,

  reset: () =>
    set({ document: null, view: null, past: [], future: [], pending: false, lastError: null }),

  setDocumentLocal: (document) => set({ document }),
}));

/** Build a single-operation edit payload (kept here so pages stay declarative). */
export function single(op: EditOperation): EditOperation[] {
  return [op];
}

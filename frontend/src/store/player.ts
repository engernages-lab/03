import { create } from "zustand";
import type { UnifiedTrack } from "../lib/types";

export type RepeatMode = "off" | "one" | "all";

export interface PlayerState {
  queue: UnifiedTrack[];
  index: number;
  isPlaying: boolean;
  volume: number;
  muted: boolean;
  repeat: RepeatMode;
  shuffle: boolean;
  shuffleOrder: number[];
  currentTime: number;
  duration: number;
  error: string | null;
}

export interface PlayerActions {
  setQueue: (tracks: UnifiedTrack[], startIndex?: number) => void;
  enqueue: (track: UnifiedTrack) => void;
  playIndex: (index: number) => void;
  toggle: () => void;
  pause: () => void;
  next: () => void;
  previous: () => void;
  setVolume: (volume: number) => void;
  toggleMute: () => void;
  toggleShuffle: () => void;
  cycleRepeat: () => void;
  setCurrentTime: (seconds: number) => void;
  setDuration: (seconds: number) => void;
  setError: (message: string | null) => void;
  clear: () => void;
  current: () => UnifiedTrack | null;
}

export const DEFAULT_VOLUME = 0.8;

/** Deterministic-friendly shuffle order (``rng`` injectable for tests). */
export function buildShuffleOrder(
  length: number,
  current = 0,
  rng: () => number = Math.random,
): number[] {
  const order = Array.from({ length }, (_, index) => index);
  for (let i = order.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  if (current >= 0 && current < length) {
    const position = order.indexOf(current);
    if (position > 0) {
      [order[0], order[position]] = [order[position], order[0]];
    }
  }
  return order;
}

/** Index of the next track, or ``null`` when playback should stop. */
export function computeNextIndex(state: PlayerState): number | null {
  const { queue, index, repeat, shuffle, shuffleOrder } = state;
  if (queue.length === 0) return null;
  if (repeat === "one") return index;

  if (shuffle && shuffleOrder.length === queue.length) {
    const position = shuffleOrder.indexOf(index);
    const nextPosition = position + 1;
    if (nextPosition < shuffleOrder.length) return shuffleOrder[nextPosition];
    return repeat === "all" ? shuffleOrder[0] : null;
  }

  const nextIndex = index + 1;
  if (nextIndex < queue.length) return nextIndex;
  return repeat === "all" ? 0 : null;
}

export function computePreviousIndex(state: PlayerState): number | null {
  const { queue, index, repeat, shuffle, shuffleOrder, currentTime } = state;
  if (queue.length === 0) return null;
  // Restart the track when more than 3 seconds have played.
  if (currentTime > 3) return index;

  if (shuffle && shuffleOrder.length === queue.length) {
    const position = shuffleOrder.indexOf(index);
    if (position > 0) return shuffleOrder[position - 1];
    return repeat === "all" ? shuffleOrder[shuffleOrder.length - 1] : index;
  }

  if (index > 0) return index - 1;
  return repeat === "all" ? queue.length - 1 : 0;
}

export function cycleRepeatMode(mode: RepeatMode): RepeatMode {
  if (mode === "off") return "all";
  if (mode === "all") return "one";
  return "off";
}

export const usePlayerStore = create<PlayerState & PlayerActions>((set, get) => ({
  queue: [],
  index: -1,
  isPlaying: false,
  volume: DEFAULT_VOLUME,
  muted: false,
  repeat: "off",
  shuffle: false,
  shuffleOrder: [],
  currentTime: 0,
  duration: 0,
  error: null,

  setQueue: (tracks, startIndex = 0) =>
    set((state) => ({
      queue: tracks,
      index: tracks.length ? Math.min(Math.max(startIndex, 0), tracks.length - 1) : -1,
      isPlaying: tracks.length > 0,
      shuffleOrder: state.shuffle ? buildShuffleOrder(tracks.length, startIndex) : [],
      currentTime: 0,
      duration: tracks[startIndex]?.duration ?? 0,
      error: null,
    })),

  enqueue: (track) =>
    set((state) => {
      const queue = [...state.queue, track];
      return {
        queue,
        index: state.index === -1 ? 0 : state.index,
        shuffleOrder: state.shuffle ? buildShuffleOrder(queue.length, state.index) : [],
      };
    }),

  playIndex: (index) =>
    set((state) => {
      if (index < 0 || index >= state.queue.length) return state;
      return {
        index,
        isPlaying: true,
        currentTime: 0,
        duration: state.queue[index]?.duration ?? 0,
        error: null,
      };
    }),

  toggle: () => set((state) => (state.queue.length ? { isPlaying: !state.isPlaying } : state)),
  pause: () => set({ isPlaying: false }),

  next: () =>
    set((state) => {
      const target = computeNextIndex(state);
      if (target === null) return { isPlaying: false, currentTime: 0 };
      return {
        index: target,
        isPlaying: true,
        currentTime: 0,
        duration: state.queue[target]?.duration ?? 0,
      };
    }),

  previous: () =>
    set((state) => {
      const target = computePreviousIndex(state);
      if (target === null) return state;
      return {
        index: target,
        isPlaying: true,
        currentTime: 0,
        duration: state.queue[target]?.duration ?? 0,
      };
    }),

  setVolume: (volume) =>
    set({ volume: Math.min(1, Math.max(0, volume)), muted: volume > 0 ? false : get().muted }),
  toggleMute: () => set((state) => ({ muted: !state.muted })),

  toggleShuffle: () =>
    set((state) => {
      const shuffle = !state.shuffle;
      return {
        shuffle,
        shuffleOrder: shuffle ? buildShuffleOrder(state.queue.length, state.index) : [],
      };
    }),

  cycleRepeat: () => set((state) => ({ repeat: cycleRepeatMode(state.repeat) })),
  setCurrentTime: (seconds) => set({ currentTime: Math.max(0, seconds) }),
  setDuration: (seconds) => set({ duration: Math.max(0, seconds) }),
  setError: (message) => set({ error: message, isPlaying: false }),

  clear: () =>
    set({
      queue: [],
      index: -1,
      isPlaying: false,
      currentTime: 0,
      duration: 0,
      shuffleOrder: [],
      error: null,
    }),

  current: () => {
    const { queue, index } = get();
    return index >= 0 && index < queue.length ? queue[index] : null;
  },
}));

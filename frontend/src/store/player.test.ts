import { beforeEach, describe, expect, it } from "vitest";
import {
  buildShuffleOrder,
  computeNextIndex,
  computePreviousIndex,
  cycleRepeatMode,
  usePlayerStore,
  type PlayerState,
} from "./player";
import type { UnifiedTrack } from "../lib/types";

function track(id: string, duration = 180): UnifiedTrack {
  return {
    track_id: id,
    source_id: "local",
    source_provider: "local",
    external_track_id: `ext-${id}`,
    title: `Track ${id}`,
    artist: "Tester",
    album: "Album",
    duration,
    artwork: null,
    source_url: null,
    availability: "streamable",
    metadata: {},
    canonical_group_id: null,
    stream_url: `/api/v1/audio/assets/${id}/stream`,
    is_local: true,
    play_count: 0,
    is_favorite: false,
  };
}

function baseState(overrides: Partial<PlayerState> = {}): PlayerState {
  return {
    queue: [track("a"), track("b"), track("c")],
    index: 0,
    isPlaying: false,
    volume: 0.8,
    muted: false,
    repeat: "off",
    shuffle: false,
    shuffleOrder: [],
    currentTime: 0,
    duration: 180,
    error: null,
    ...overrides,
  };
}

describe("computeNextIndex", () => {
  it("advances through the queue", () => {
    expect(computeNextIndex(baseState())).toBe(1);
    expect(computeNextIndex(baseState({ index: 1 }))).toBe(2);
  });

  it("stops at the end when repeat is off", () => {
    expect(computeNextIndex(baseState({ index: 2 }))).toBeNull();
  });

  it("wraps when repeat is all", () => {
    expect(computeNextIndex(baseState({ index: 2, repeat: "all" }))).toBe(0);
  });

  it("repeats the same track when repeat is one", () => {
    expect(computeNextIndex(baseState({ index: 1, repeat: "one" }))).toBe(1);
  });

  it("follows the shuffle order", () => {
    const state = baseState({ shuffle: true, shuffleOrder: [0, 2, 1], index: 2 });
    expect(computeNextIndex(state)).toBe(1);
    expect(computeNextIndex({ ...state, index: 1 })).toBeNull();
    expect(computeNextIndex({ ...state, index: 1, repeat: "all" })).toBe(0);
  });

  it("returns null for an empty queue", () => {
    expect(computeNextIndex(baseState({ queue: [] }))).toBeNull();
  });
});

describe("computePreviousIndex", () => {
  it("goes back one track", () => {
    expect(computePreviousIndex(baseState({ index: 2 }))).toBe(1);
  });

  it("restarts the current track after 3 seconds", () => {
    expect(computePreviousIndex(baseState({ index: 2, currentTime: 10 }))).toBe(2);
  });

  it("stays on the first track when repeat is off", () => {
    expect(computePreviousIndex(baseState({ index: 0 }))).toBe(0);
  });

  it("wraps to the end when repeat is all", () => {
    expect(computePreviousIndex(baseState({ index: 0, repeat: "all" }))).toBe(2);
  });
});

describe("buildShuffleOrder", () => {
  it("contains every index once and starts with the current track", () => {
    const order = buildShuffleOrder(5, 3, () => 0.42);
    expect(order).toHaveLength(5);
    expect([...order].sort()).toEqual([0, 1, 2, 3, 4]);
    expect(order[0]).toBe(3);
  });
});

describe("cycleRepeatMode", () => {
  it("cycles off -> all -> one -> off", () => {
    expect(cycleRepeatMode("off")).toBe("all");
    expect(cycleRepeatMode("all")).toBe("one");
    expect(cycleRepeatMode("one")).toBe("off");
  });
});

describe("player store", () => {
  beforeEach(() => {
    usePlayerStore.getState().clear();
  });

  it("loads a queue and starts playing at the requested index", () => {
    usePlayerStore.getState().setQueue([track("a"), track("b")], 1);
    const state = usePlayerStore.getState();
    expect(state.index).toBe(1);
    expect(state.isPlaying).toBe(true);
    expect(state.current()?.track_id).toBe("b");
  });

  it("next() moves on and stops at the end", () => {
    const store = usePlayerStore.getState();
    store.setQueue([track("a"), track("b")]);
    usePlayerStore.getState().next();
    expect(usePlayerStore.getState().index).toBe(1);
    usePlayerStore.getState().next();
    expect(usePlayerStore.getState().isPlaying).toBe(false);
    expect(usePlayerStore.getState().index).toBe(1);
  });

  it("previous() rewinds within the track when time > 3s", () => {
    usePlayerStore.getState().setQueue([track("a"), track("b")], 1);
    usePlayerStore.getState().setCurrentTime(12);
    usePlayerStore.getState().previous();
    expect(usePlayerStore.getState().index).toBe(1);
    expect(usePlayerStore.getState().currentTime).toBe(0);
  });

  it("clamps volume and clears mute when raised", () => {
    usePlayerStore.getState().setVolume(2);
    expect(usePlayerStore.getState().volume).toBe(1);
    usePlayerStore.getState().setVolume(0);
    expect(usePlayerStore.getState().volume).toBe(0);
    usePlayerStore.getState().toggleMute();
    expect(usePlayerStore.getState().muted).toBe(true);
    usePlayerStore.getState().setVolume(0.5);
    expect(usePlayerStore.getState().muted).toBe(false);
  });

  it("keeps an empty queue inert", () => {
    usePlayerStore.getState().toggle();
    expect(usePlayerStore.getState().isPlaying).toBe(false);
    usePlayerStore.getState().next();
    expect(usePlayerStore.getState().isPlaying).toBe(false);
  });

  it("rebuilds the shuffle order when tracks are enqueued", () => {
    const store = usePlayerStore.getState();
    store.setQueue([track("a")]);
    usePlayerStore.getState().toggleShuffle();
    usePlayerStore.getState().enqueue(track("b"));
    const state = usePlayerStore.getState();
    expect(state.shuffleOrder).toHaveLength(2);
    expect([...state.shuffleOrder].sort()).toEqual([0, 1]);
  });
});

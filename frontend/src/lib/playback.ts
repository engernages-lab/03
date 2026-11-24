import { useCallback } from "react";
import { usePlayerStore } from "../store/player";
import type { UnifiedTrack } from "./types";

/** Bridge between API track lists and the player queue. */
export function usePlayQueue() {
  const setQueue = usePlayerStore((state) => state.setQueue);

  const playTracks = useCallback(
    (tracks: UnifiedTrack[], index = 0) => {
      if (!tracks.length) return;
      setQueue(tracks, index);
    },
    [setQueue],
  );

  const playTrack = useCallback(
    (track: UnifiedTrack, tracks?: UnifiedTrack[]) => {
      const list = tracks?.length ? tracks : [track];
      const index = Math.max(
        0,
        list.findIndex((item) => item.track_id === track.track_id),
      );
      setQueue(list, index);
    },
    [setQueue],
  );

  return { playTracks, playTrack };
}

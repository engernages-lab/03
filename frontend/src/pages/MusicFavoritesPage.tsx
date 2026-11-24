import { Heart } from "lucide-react";
import { useMemo } from "react";
import { useFavorites, useToggleFavorite } from "../lib/resources";
import { usePlayQueue } from "../lib/playback";
import { usePlayerStore } from "../store/player";
import { TrackRow } from "../components/music/TrackRow";
import { EmptyState, Skeleton } from "../components/ui/Feedback";

export function MusicFavoritesPage() {
  const favorites = useFavorites();
  const toggleFavorite = useToggleFavorite();
  const { playTrack } = usePlayQueue();
  const current = usePlayerStore((state) => state.queue[state.index] ?? null);
  const isPlaying = usePlayerStore((state) => state.isPlaying);

  const ids = useMemo(
    () => new Set((favorites.data?.items ?? []).map((item) => item.track_id)),
    [favorites.data],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-key-rose/15 text-key-rose">
          <Heart size={18} fill="currentColor" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-white">我的收藏</h2>
          <p className="text-[11px] text-studio-500">{favorites.data?.total ?? 0} 首曲目</p>
        </div>
      </div>

      <div className="panel">
        {favorites.isLoading &&
          Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="m-3 h-12" />)}
        {favorites.data?.items.length === 0 && (
          <EmptyState
            icon={<Heart size={22} />}
            title="还没有收藏"
            description="在音乐资料库里点击 ♥ 收藏喜欢的曲目。"
          />
        )}
        {favorites.data?.items.map((track, index) => (
          <TrackRow
            key={track.track_id}
            track={{ ...track, is_favorite: true }}
            index={index}
            isCurrent={current?.track_id === track.track_id}
            isPlaying={isPlaying}
            onPlay={(item) => playTrack(item, favorites.data?.items)}
            onToggleFavorite={(item) => toggleFavorite.mutate({ trackId: item.track_id, favorite: ids.has(item.track_id) })}
          />
        ))}
      </div>
    </div>
  );
}

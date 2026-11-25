import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type {
  AudioAsset,
  AlbumSummary,
  ArtistSummary,
  DocumentSummary,
  DualNotationResponse,
  EditOperation,
  EditResult,
  EligibilityResult,
  GridViewModel,
  HistoryEntry,
  JianpuViewModel,
  KeyboardLayout,
  LayoutPreview,
  LibraryStats,
  MidiInspectResult,
  MusicDocument,
  MusicSource,
  Page,
  PlaylistSummary,
  ProviderInfo,
  StreamInfo,
  TranscriptionJob,
  TranscriptionCapabilities,
  TranscriptionModels,
  UnifiedTrack,
  WaveformResponse,
} from "./types";

// ------------------------------------------------------------ documents ---

export function useDocuments(params: { q?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: () => api.get<Page<DocumentSummary>>("/documents", params),
  });
}

export function useDocument(documentId?: string) {
  return useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.get<MusicDocument>(`/documents/${documentId}`),
    enabled: Boolean(documentId),
  });
}

export function useDualNotation(documentId?: string, layoutId?: string, divisions = 4) {
  return useQuery({
    queryKey: ["notation", documentId, layoutId ?? "doc", divisions],
    queryFn: () =>
      api.get<DualNotationResponse>(`/notation/${documentId}/both`, {
        layout_id: layoutId,
        divisions,
      }),
    enabled: Boolean(documentId),
  });
}

export function useGridNotation(documentId?: string, layoutId?: string, divisions = 4) {
  return useQuery({
    queryKey: ["grid", documentId, layoutId ?? "doc", divisions],
    queryFn: () =>
      api.get<GridViewModel>(`/notation/${documentId}/grid`, { layout_id: layoutId, divisions }),
    enabled: Boolean(documentId),
  });
}

export function useJianpuNotation(documentId?: string, layoutId?: string, keySignature?: string) {
  return useQuery({
    queryKey: ["jianpu", documentId, layoutId ?? "doc", keySignature ?? "doc"],
    queryFn: () =>
      api.get<JianpuViewModel>(`/notation/${documentId}/jianpu`, {
        layout_id: layoutId,
        key_signature: keySignature,
      }),
    enabled: Boolean(documentId),
  });
}

export function useCreateDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post<MusicDocument>("/documents", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useApplyEdits(documentId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (operations: EditOperation[]) =>
      api.post<EditResult>(`/documents/${documentId}/edits`, { operations }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["notation", documentId] });
      client.invalidateQueries({ queryKey: ["documents"] });
      client.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}

export function useReplaceDocument(documentId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (document: MusicDocument) =>
      api.put<MusicDocument>(`/documents/${documentId}`, document),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notation", documentId] }),
  });
}

export function useDeleteDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => api.del<void>(`/documents/${documentId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useDuplicateDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => api.post<MusicDocument>(`/documents/${documentId}/duplicate`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }),
  });
}

// ------------------------------------------------------------- keyboard ---

export function useLayouts() {
  return useQuery({
    queryKey: ["layouts"],
    queryFn: () => api.get<{ items: KeyboardLayout[]; total: number }>("/keyboard-layouts"),
  });
}

export function useLayout(layoutId?: string) {
  return useQuery({
    queryKey: ["layout", layoutId],
    queryFn: () => api.get<KeyboardLayout>(`/keyboard-layouts/${layoutId}`),
    enabled: Boolean(layoutId),
  });
}

export function useLayoutPreview(layoutId?: string) {
  return useQuery({
    queryKey: ["layout-preview", layoutId],
    queryFn: () => api.get<LayoutPreview>(`/keyboard-layouts/${layoutId}/preview`),
    enabled: Boolean(layoutId),
  });
}

export function useSaveLayout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (layout: KeyboardLayout) => api.put<KeyboardLayout>(`/keyboard-layouts/${layout.layout_id}`, layout),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["layouts"] });
      client.invalidateQueries({ queryKey: ["layout"] });
    },
  });
}

export function useCreateLayout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (layout: KeyboardLayout) => api.post<KeyboardLayout>("/keyboard-layouts", layout),
    onSuccess: () => client.invalidateQueries({ queryKey: ["layouts"] }),
  });
}

export function useDeleteLayout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (layoutId: string) => api.del<void>(`/keyboard-layouts/${layoutId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["layouts"] }),
  });
}

export function useDuplicateLayout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ layoutId, name }: { layoutId: string; name?: string }) =>
      api.post<KeyboardLayout>(`/keyboard-layouts/${layoutId}/duplicate`, { name }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["layouts"] }),
  });
}

// -------------------------------------------------------------- sources ---

export function useProviders() {
  return useQuery({
    queryKey: ["providers"],
    queryFn: () => api.get<{ items: ProviderInfo[]; creatable: string[] }>("/sources/providers"),
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => api.get<MusicSource[]>("/sources"),
  });
}

export function useCreateSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post<MusicSource>("/sources", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["sources"] }),
  });
}

export function useTestSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) =>
      api.post<{ ok: boolean; status: string; message: string; details: Record<string, unknown> }>(
        `/sources/${sourceId}/test`,
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["sources"] }),
  });
}

export function useSyncSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) =>
      api.post<{ ok: boolean; message: string; total?: number }>(`/sources/${sourceId}/sync`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["tracks"] });
      client.invalidateQueries({ queryKey: ["sources"] });
      client.invalidateQueries({ queryKey: ["library-stats"] });
    },
  });
}

export function useDeleteSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => api.del<void>(`/sources/${sourceId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["sources"] }),
  });
}

export function useSourcePermissions(sourceId?: string) {
  return useQuery({
    queryKey: ["source-permissions", sourceId],
    queryFn: () => api.get<Record<string, boolean>>(`/sources/${sourceId}/permissions`),
    enabled: Boolean(sourceId),
  });
}

export function useUpdateSourcePermissions(sourceId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, boolean>) =>
      api.put<Record<string, boolean>>(`/sources/${sourceId}/permissions`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["source-permissions", sourceId] });
      client.invalidateQueries({ queryKey: ["eligibility"] });
    },
  });
}

// -------------------------------------------------------------- library ---

export function useTracks(params: { q?: string; source_id?: string; limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ["tracks", params],
    queryFn: () => api.get<Page<UnifiedTrack>>("/library/tracks", params),
  });
}

export function useImportTrack() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => api.upload<UnifiedTrack>("/library/import", form),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["tracks"] });
      client.invalidateQueries({ queryKey: ["library-stats"] });
    },
  });
}

export function useLibraryStats() {
  return useQuery({
    queryKey: ["library-stats"],
    queryFn: () => api.get<LibraryStats>("/library/stats"),
  });
}

export function useFavorites() {
  return useQuery({
    queryKey: ["favorites"],
    queryFn: () => api.get<Page<UnifiedTrack>>("/library/favorites"),
  });
}

export function useToggleFavorite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ trackId, favorite }: { trackId: string; favorite: boolean }) =>
      favorite
        ? api.del<void>(`/library/favorites/${trackId}`)
        : api.post<void>(`/library/favorites/${trackId}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["favorites"] });
      client.invalidateQueries({ queryKey: ["tracks"] });
    },
  });
}

export function usePlaylists() {
  return useQuery({
    queryKey: ["playlists"],
    queryFn: () => api.get<{ items: PlaylistSummary[]; total: number }>("/library/playlists"),
  });
}

export function useCreatePlaylist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; description?: string }) =>
      api.post<PlaylistSummary>("/library/playlists", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["playlists"] }),
  });
}

export function usePlaylistTracks(playlistId?: string) {
  return useQuery({
    queryKey: ["playlist-tracks", playlistId],
    queryFn: () => api.get<Page<UnifiedTrack>>(`/library/playlists/${playlistId}/tracks`),
    enabled: Boolean(playlistId),
  });
}

export function useAddToPlaylist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ playlistId, trackId }: { playlistId: string; trackId: string }) =>
      api.post<void>(`/library/playlists/${playlistId}/tracks/${trackId}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["playlist-tracks"] });
      client.invalidateQueries({ queryKey: ["playlists"] });
    },
  });
}

export function useRemoveFromPlaylist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ playlistId, trackId }: { playlistId: string; trackId: string }) =>
      api.del<void>(`/library/playlists/${playlistId}/tracks/${trackId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["playlist-tracks"] }),
  });
}

export function useDeletePlaylist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (playlistId: string) => api.del<void>(`/library/playlists/${playlistId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["playlists"] }),
  });
}

export function useHistory(limit = 50) {
  return useQuery({
    queryKey: ["history", limit],
    queryFn: () => api.get<{ items: HistoryEntry[]; total: number }>("/library/history", { limit }),
  });
}

export function useRecordHistory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { track_id: string; position?: number; completed?: boolean }) =>
      api.post<{ history_id: number }>("/library/history", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["history"] }),
  });
}

export function useAlbums() {
  return useQuery({
    queryKey: ["albums"],
    queryFn: () => api.get<{ items: AlbumSummary[]; total: number }>("/library/albums"),
  });
}

export function useArtists() {
  return useQuery({
    queryKey: ["artists"],
    queryFn: () => api.get<{ items: ArtistSummary[]; total: number }>("/library/artists"),
  });
}

// ------------------------------------------------------------ eligibility --

export function useEligibility(trackId?: string, confirmRights = false) {
  return useQuery({
    queryKey: ["eligibility", trackId, confirmRights],
    queryFn: () =>
      api.get<EligibilityResult>(`/eligibility/${trackId}`, { confirm_rights: confirmRights }),
    enabled: Boolean(trackId),
  });
}

// -------------------------------------------------------------- playback ---

export function useStreamInfo(trackId?: string) {
  return useQuery({
    queryKey: ["stream", trackId],
    queryFn: () => api.get<StreamInfo>(`/playback/stream/${trackId}`),
    enabled: Boolean(trackId),
    staleTime: 5 * 60 * 1000,
  });
}

// --------------------------------------------------------- transcription ---

export function useTranscriptionModels() {
  return useQuery({
    queryKey: ["transcription-models"],
    queryFn: () => api.get<TranscriptionModels>("/transcription/models"),
  });
}

export function useTranscriptionJobs() {
  return useQuery({
    queryKey: ["transcription-jobs"],
    queryFn: () => api.get<{ items: TranscriptionJob[]; total: number }>("/transcription/jobs"),
    refetchInterval: 4000,
  });
}

export function useCreateTranscriptionJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { asset_id?: string; track_id?: string; confirm_rights?: boolean }) =>
      api.post<TranscriptionJob>("/transcription/jobs", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["transcription-jobs"] }),
  });
}

export function useRunTranscriptionJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.post<TranscriptionJob>(`/transcription/jobs/${jobId}/run`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["transcription-jobs"] }),
  });
}

export function useCancelTranscriptionJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.post<TranscriptionJob>(`/transcription/jobs/${jobId}/cancel`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["transcription-jobs"] }),
  });
}

export function useTranscriptionCapabilities() {
  return useQuery({
    queryKey: ["transcription-capabilities"],
    queryFn: () => api.get<TranscriptionCapabilities>("/transcription/capabilities"),
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------- audio ----

export function useUploadAudio() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => api.upload<AudioAsset>("/audio/upload", form),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["audio-assets"] });
      client.invalidateQueries({ queryKey: ["library-stats"] });
    },
  });
}

export function useWaveform(assetId?: string, buckets = 400) {
  return useQuery({
    queryKey: ["waveform", assetId, buckets],
    queryFn: () => api.get<WaveformResponse>(`/audio/assets/${assetId}/waveform`, { buckets }),
    enabled: Boolean(assetId),
  });
}

// ----------------------------------------------------------------- midi ----

export function useInspectMidi() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<MidiInspectResult>("/midi/inspect", form);
    },
  });
}

export function useImportMidi() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, title, layoutId }: { file: File; title?: string; layoutId?: string }) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<MusicDocument>("/midi/import", form, {
        title,
        layout_id: layoutId,
      });
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

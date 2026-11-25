/** Shared API types. Mirrors backend Pydantic schemas (app/schemas, app/api/v1). */

export interface CapabilityFlag {
  available: boolean;
  version?: string | null;
  path?: string | null;
}

export interface Capabilities {
  python: string;
  platform: string;
  ffmpeg: CapabilityFlag;
  librosa: CapabilityFlag;
  soundfile: CapabilityFlag;
  mido: CapabilityFlag;
  pretty_midi: CapabilityFlag;
  music21: CapabilityFlag;
  mutagen: CapabilityFlag;
}

export type CapabilityKey =
  | "ffmpeg"
  | "librosa"
  | "soundfile"
  | "mido"
  | "pretty_midi"
  | "music21"
  | "mutagen";

export interface HealthResponse {
  status: string;
  name: string;
  version: string;
  stage: string;
  environment: string;
  timestamp: string;
  capabilities: Capabilities;
}

export interface ReadinessResponse {
  status: "ready" | "degraded";
  checks: Record<string, { ok: boolean; optional?: boolean; error?: string }>;
  timestamp: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// ---------------------------------------------------------------- keyboard --

export interface KeyDefinition {
  key_id: string;
  label: string;
  index: number;
  row: number;
  col: number;
  midi_pitch: number | null;
  semitone_offset: number | null;
  color: string;
  octave: number | null;
}

export interface KeyboardLayout {
  layout_id: string;
  name: string;
  description: string;
  root_note: number;
  key_count: number;
  octave_span: number;
  keys: KeyDefinition[];
  is_builtin: boolean;
}

export interface LayoutPreviewKey {
  key_id: string;
  label: string;
  index: number;
  row: number;
  col: number;
  color: string;
  pitch: number | null;
  pitch_name: string | null;
  octave: number | null;
}

export interface LayoutPreview {
  layout: KeyboardLayout;
  keys: LayoutPreviewKey[];
  pitch_map: Record<string, string>;
}

// ------------------------------------------------------------- document ----

export interface TimeSignature {
  numerator: number;
  denominator: number;
}

export interface MusicTrack {
  track_id: string;
  name: string;
  instrument: string;
  channel: number | null;
  index: number;
  color: string;
  muted: boolean;
}

export type EventKind = "note" | "rest";

export interface NoteEvent {
  event_id: string;
  pitch: number | null;
  start_time: number;
  duration: number;
  velocity: number;
  track_id: string;
  measure: number;
  beat: number;
  mapped_key: string | null;
  kind: EventKind;
  chord_id: string | null;
  tie_group: string | null;
  confidence?: number | null;
}

export interface GridSettings {
  divisions: number;
  show_key_names: boolean;
  show_velocity: boolean;
  color_mode: "key" | "pitch" | "velocity";
}

export interface JianpuSettings {
  show_key_labels: boolean;
  octave_style: "dots" | "primes";
  max_notes_per_line: number;
  accidental_style: "sharp" | "flat";
}

export interface NotationSettings {
  grid: GridSettings;
  jianpu: JianpuSettings;
}

export interface SourceMetadata {
  kind:
    | "manual"
    | "midi"
    | "local_file"
    | "subsonic"
    | "apple_music"
    | "spotify"
    | "netease"
    | "qqmusic"
    | "transcription";
  filename?: string | null;
  provider?: string | null;
  provider_track_id?: string | null;
  imported_at?: string | null;
  notes?: string | null;
}

export interface MusicDocument {
  schema_version: number;
  document_id: string;
  title: string;
  artist: string;
  tempo: number;
  time_signature: TimeSignature;
  key_signature: string;
  duration: number;
  tracks: MusicTrack[];
  events: NoteEvent[];
  keyboard_layout: KeyboardLayout;
  notation_settings: NotationSettings;
  source_metadata: SourceMetadata;
  created_at: string;
  updated_at: string;
}

export interface DocumentSummary {
  document_id: string;
  title: string;
  artist: string;
  tempo: number;
  time_signature: string;
  key_signature: string;
  duration: number;
  tracks: number;
  events: number;
  measures: number;
  layout_id: string;
  layout_name: string;
  source_kind: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentFinding {
  level: "info" | "warning" | "error";
  code: string;
  message?: string;
  [key: string]: unknown;
}

// -------------------------------------------------------------- notation ---

export type CellState = "empty" | "note" | "rest" | "continuation";

export interface GridCell {
  measure: number;
  slot: number;
  state: CellState;
  start_time: number;
  duration: number;
  event_id: string | null;
  chord_id: string | null;
  span: number;
  velocity: number;
  pitch: number | null;
  label: string | null;
  color: string | null;
}

export interface GridRow {
  key_id: string;
  label: string;
  index: number;
  color: string;
  pitch: number | null;
  pitch_name: string | null;
  cells: GridCell[];
}

export interface GridMeasure {
  measure: number;
  start_beat: number;
  beats: number;
  slots: number;
  start_slot: number;
}

export interface UnmappedNote {
  event_id: string;
  pitch: number;
  pitch_name: string;
  start_time: number;
  duration: number;
  measure: number;
  reason: string;
}

export interface GridViewModel {
  document_id: string;
  title: string;
  artist: string;
  layout_id: string;
  layout_name: string;
  tempo: number;
  time_signature: string;
  key_signature: string;
  divisions: number;
  slots_per_measure: number;
  measures: GridMeasure[];
  rows: GridRow[];
  rest_row: GridRow | null;
  unmapped: UnmappedNote[];
  stats: {
    notes: number;
    rests: number;
    chords: number;
    measures: number;
    slots: number;
    unmapped: number;
  };
}

export interface JianpuNote {
  event_id: string;
  pitch: number | null;
  token: string;
  degree: number | null;
  accidental: string | null;
  octave: number;
  duration_label: string;
  dots: number;
  approximate: boolean;
  tie: "start" | "continue" | "stop" | null;
  is_rest: boolean;
  chord_id: string | null;
  chord_size: number;
  chord_index: number;
  is_chord_head: boolean;
  mapped_key: string | null;
  key_label: string | null;
  width: number;
  start_time: number;
  duration: number;
  beat_in_measure: number;
}

export interface JianpuMeasure {
  measure: number;
  start_beat: number;
  beats: number;
  system_index: number;
  notes: JianpuNote[];
}

export interface JianpuViewModel {
  document_id: string;
  title: string;
  artist: string;
  key_signature: string;
  tonic: string;
  mode: string;
  tempo: number;
  time_signature: string;
  layout_id: string;
  layout_name: string;
  max_notes_per_line: number;
  measures: JianpuMeasure[];
  key_labels: Record<string, string>;
  stats: {
    notes: number;
    rests: number;
    chords: number;
    measures: number;
    accidentals: number;
    ties: number;
    unmapped: number;
    approximate_durations: number;
  };
}

export interface DualNotationResponse {
  document: MusicDocument;
  grid: GridViewModel;
  jianpu: JianpuViewModel;
  findings: DocumentFinding[];
}

export type EditOperation =
  | { op: "add_note"; pitch: number; start_time: number; duration: number; track_id?: string; velocity?: number }
  | { op: "add_rest"; start_time: number; duration: number; track_id?: string }
  | { op: "update_note"; event_id: string; patch: Record<string, unknown> }
  | { op: "delete_note"; event_id: string }
  | { op: "move_note"; event_id: string; key_id: string }
  | { op: "transpose"; semitones: number; track_id?: string }
  | { op: "quantize"; divisions?: number; track_id?: string }
  | { op: "set_tempo"; tempo: number }
  | { op: "set_time_signature"; numerator: number; denominator: number }
  | { op: "add_track"; track_name: string }
  | { op: "delete_track"; track_id: string }
  | { op: "set_layout"; layout: KeyboardLayout };

export interface EditResult {
  document: MusicDocument;
  applied: number;
  touched_event_ids: string[];
}

// ---------------------------------------------------------------- music ----

export type Provider =
  | "local"
  | "subsonic"
  | "apple_music"
  | "spotify"
  | "netease"
  | "qqmusic"
  | "unknown";

export interface SourceCapabilityReport {
  metadata: boolean;
  playback: boolean;
  audio_read: boolean;
  ai_processing: boolean;
  model_training: boolean;
  playlists: boolean;
  search: boolean;
  favorites: boolean;
  requires_auth: boolean;
  policy_note: string;
}

export interface MusicSource {
  source_id: string;
  provider: Provider;
  display_name: string;
  status: string;
  connected_at: string | null;
  last_error: string | null;
  capabilities: SourceCapabilityReport;
  policy_note: string;
  account_name: string | null;
  is_local: boolean;
}

export interface ProviderInfo {
  provider: Provider;
  display_name: string;
  description: string;
  auth: string;
  docs: string[];
  can_import: boolean;
  capabilities: SourceCapabilityReport;
  policy_note: string;
}

export interface UnifiedTrack {
  track_id: string;
  source_id: string;
  source_provider: Provider;
  external_track_id: string;
  title: string;
  artist: string;
  album: string;
  duration: number;
  artwork: string | null;
  source_url: string | null;
  availability: string;
  metadata: Record<string, unknown>;
  canonical_group_id: string | null;
  stream_url: string | null;
  is_local: boolean;
  play_count: number;
  is_favorite: boolean;
}

export interface PlaylistSummary {
  playlist_id: string;
  name: string;
  description: string | null;
  artwork: string | null;
  track_count: number;
  source_id: string;
  is_user_owned: boolean;
  created_at: string;
}

export interface HistoryEntry {
  history_id: number;
  played_at: string;
  position: number;
  completed: boolean;
  track: UnifiedTrack;
}

export interface LibraryStats {
  tracks: number;
  sources: number;
  playlists: number;
  favorites: number;
  transcription_jobs: number;
  total_duration: number;
}

export interface AlbumSummary {
  album: string;
  artist: string;
  artwork: string | null;
  track_count: number;
  duration: number;
  source_ids: string[];
}

export interface ArtistSummary {
  artist: string;
  track_count: number;
  album_count: number;
}

export interface AudioAsset {
  asset_id: string;
  filename: string;
  title: string | null;
  artist: string | null;
  mime: string;
  ext: string;
  size_bytes: number;
  duration: number;
  sample_rate: number;
  channels: number;
  bitrate: number | null;
  codec: string | null;
  checksum_sha256: string;
  artwork_url: string | null;
  stream_url: string;
  source_id: string | null;
  created_at: string;
}

export interface WaveformResponse {
  asset_id: string;
  buckets: number;
  duration: number;
  peaks: number[];
}

// -------------------------------------------------------------- eligibility

export type EligibilityStatus =
  | "ELIGIBLE"
  | "INELIGIBLE"
  | "REQUIRES_USER_UPLOAD"
  | "REQUIRES_PERMISSION"
  | "PROVIDER_RESTRICTED"
  | "UNKNOWN";

export interface TranscriptionPermissions {
  metadata_access: boolean;
  playback_access: boolean;
  audio_read_access: boolean;
  ai_processing_permission: boolean;
  model_training_permission: boolean;
}

export interface EligibilityResult {
  track_id: string;
  provider: Provider;
  status: EligibilityStatus;
  permissions: TranscriptionPermissions;
  reasons: string[];
  policy_note: string;
  ai_allowed: boolean;
}

export interface StreamInfo {
  track_id: string;
  provider: Provider;
  mode: "direct" | "proxy" | "provider_sdk";
  url?: string | null;
  info: Record<string, unknown>;
  title: string;
  duration: number;
}

// ------------------------------------------------------------ transcription

export interface AnalysisResult {
  sample_rate: number;
  duration: number;
  rms: number;
  peak: number;
  onsets: number;
  bpm: number | null;
  beat_count: number;
  method: string;
  warnings: string[];
}

export interface TranscriptionJob {
  job_id: string;
  document_id: string | null;
  asset_id: string | null;
  track_id: string | null;
  source_kind: string;
  status:
    | "queued"
    | "validating"
    | "preprocessing"
    | "analyzing"
    | "analysis_only"
    | "completed"
    | "failed"
    | "cancelled";
  progress: number;
  method: string | null;
  confidence: number;
  events_produced: number;
  analysis: AnalysisResult | null;
  warnings: string[];
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface NoteExtractionModel {
  available: boolean;
  reason: string | null;
  code: string | null;
  model_id: string;
  name: string;
  version: string;
  license: string;
  runtime: string | null;
  polyphonic: boolean;
  capabilities: {
    monophonic_melody: boolean;
    polyphonic: boolean;
    piano: boolean;
    multi_instrument: boolean;
    velocity: boolean;
    confidence: boolean;
  };
}

export interface TranscriptionModels {
  note_extraction: NoteExtractionModel;
  signal_analysis: { available: boolean; method: string; produces_notes: boolean };
  midi_import: { available: boolean; produces_notes: boolean };
}

export interface TranscriptionCapabilities {
  audio_formats: string[];
  midi_formats: string[];
  max_upload_mb: number;
  max_duration_seconds: number;
  note_extraction: NoteExtractionModel;
  stages: string[];
  terminal_states: string[];
  produces_notes: boolean;
  pipeline: { audio: string; midi: string };
}

export interface MidiInspectResult {
  tempo: number;
  time_signature: string;
  ticks_per_beat: number;
  midi_format: number;
  tracks: number;
  channels: number[];
  notes: number;
  duration_seconds: number;
  pitch_range: [number, number];
  track_names: Record<string, string>;
  warnings: string[];
  filename?: string;
}

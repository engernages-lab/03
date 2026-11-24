import { beforeEach, describe, expect, it } from "vitest";
import { useDocumentStore } from "./document";
import type { DualNotationResponse, MusicDocument } from "../lib/types";

function doc(id: string, title: string): MusicDocument {
  return {
    schema_version: 1,
    document_id: id,
    title,
    artist: "Tester",
    tempo: 120,
    time_signature: { numerator: 4, denominator: 4 },
    key_signature: "C",
    duration: 2,
    tracks: [
      { track_id: "t1", name: "主旋律", instrument: "piano", channel: null, index: 0, color: "#3ddc97", muted: false },
    ],
    events: [],
    keyboard_layout: {
      layout_id: "builtin:7-key-c-major",
      name: "默认七键",
      description: "",
      root_note: 60,
      key_count: 0,
      octave_span: 1,
      keys: [],
      is_builtin: true,
    },
    notation_settings: {
      grid: { divisions: 4, show_key_names: true, show_velocity: false, color_mode: "key" },
      jianpu: { show_key_labels: true, octave_style: "dots", max_notes_per_line: 16, accidental_style: "sharp" },
    },
    source_metadata: { kind: "manual" },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function view(document: MusicDocument): DualNotationResponse {
  return {
    document,
    grid: {
      document_id: document.document_id,
      title: document.title,
      artist: document.artist,
      layout_id: "builtin:7-key-c-major",
      layout_name: "默认七键",
      tempo: document.tempo,
      time_signature: "4/4",
      key_signature: "C",
      divisions: 4,
      slots_per_measure: 16,
      measures: [],
      rows: [],
      rest_row: null,
      unmapped: [],
      stats: { notes: 0, rests: 0, chords: 0, measures: 1, slots: 16, unmapped: 0 },
    },
    jianpu: {
      document_id: document.document_id,
      title: document.title,
      artist: document.artist,
      key_signature: "C",
      tonic: "C",
      mode: "major",
      tempo: document.tempo,
      time_signature: "4/4",
      layout_id: "builtin:7-key-c-major",
      layout_name: "默认七键",
      max_notes_per_line: 16,
      measures: [],
      key_labels: {},
      stats: {
        notes: 0,
        rests: 0,
        chords: 0,
        measures: 1,
        accidentals: 0,
        ties: 0,
        unmapped: 0,
        approximate_durations: 0,
      },
    },
    findings: [],
  };
}

describe("document store", () => {
  beforeEach(() => {
    useDocumentStore.getState().reset();
  });

  it("loads a document and clears history", () => {
    useDocumentStore.getState().load(view(doc("d1", "第一版")));
    const state = useDocumentStore.getState();
    expect(state.document?.title).toBe("第一版");
    expect(state.canUndo()).toBe(false);
    expect(state.canRedo()).toBe(false);
  });

  it("records edits and supports undo/redo", () => {
    const store = useDocumentStore.getState();
    store.load(view(doc("d1", "v1")));
    store.applyEditResult(view(doc("d1", "v2")));
    store.applyEditResult(view(doc("d1", "v3")));

    expect(useDocumentStore.getState().document?.title).toBe("v3");
    expect(useDocumentStore.getState().canUndo()).toBe(true);

    const undone = useDocumentStore.getState().undo();
    expect(undone?.title).toBe("v2");
    expect(useDocumentStore.getState().document?.title).toBe("v2");
    expect(useDocumentStore.getState().canRedo()).toBe(true);

    const redone = useDocumentStore.getState().redo();
    expect(redone?.title).toBe("v3");
    expect(useDocumentStore.getState().canRedo()).toBe(false);
  });

  it("clears the redo stack after a new edit", () => {
    const store = useDocumentStore.getState();
    store.load(view(doc("d1", "v1")));
    store.applyEditResult(view(doc("d1", "v2")));
    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().canRedo()).toBe(true);

    useDocumentStore.getState().applyEditResult(view(doc("d1", "v3")));
    expect(useDocumentStore.getState().canRedo()).toBe(false);
  });

  it("returns null when there is nothing to undo", () => {
    useDocumentStore.getState().load(view(doc("d1", "only")));
    expect(useDocumentStore.getState().undo()).toBeNull();
    expect(useDocumentStore.getState().redo()).toBeNull();
  });

  it("caps the history at 50 entries", () => {
    const store = useDocumentStore.getState();
    store.load(view(doc("d1", "v0")));
    for (let index = 1; index <= 60; index += 1) {
      useDocumentStore.getState().applyEditResult(view(doc("d1", `v${index}`)));
    }
    expect(useDocumentStore.getState().past.length).toBe(50);
  });

  it("exposes the current view for both notations", () => {
    useDocumentStore.getState().load(view(doc("d1", "同步")));
    const state = useDocumentStore.getState();
    expect(state.view?.grid.document_id).toBe("d1");
    expect(state.view?.jianpu.document_id).toBe("d1");
  });
});

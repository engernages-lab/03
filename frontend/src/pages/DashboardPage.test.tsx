import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { DashboardPage } from "./DashboardPage";

const HEALTH = {
  status: "ok",
  name: "PocketScore AI",
  version: "1.0.0a1",
  stage: "V1.0-A",
  environment: "test",
  timestamp: new Date().toISOString(),
  capabilities: {
    python: "3.9.13",
    platform: "Windows",
    ffmpeg: { available: true, version: "ffmpeg version 4.2.2" },
    librosa: { available: true, version: "0.10.2" },
    soundfile: { available: true, version: "0.12.1" },
    mido: { available: true, version: "installed" },
    pretty_midi: { available: true, version: "0.2.10" },
    music21: { available: true, version: "8.3.0" },
    mutagen: { available: true, version: "installed" },
  },
};

const READY = {
  status: "ready",
  checks: { database: { ok: true }, ffmpeg: { ok: true }, midi: { ok: true } },
  timestamp: new Date().toISOString(),
};

const STATS = {
  tracks: 3,
  sources: 1,
  playlists: 0,
  favorites: 1,
  transcription_jobs: 0,
  total_duration: 540,
};

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Route each request to the payload its endpoint returns. */
function stubApi(health: unknown = HEALTH, ready: unknown = READY) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown = health;
      if (url.includes("/health/ready")) body = ready;
      else if (url.includes("/library/stats")) body = STATS;
      else if (url.includes("/sources")) body = [];
      else if (url.includes("/health")) body = health;
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
  );
}

describe("DashboardPage", () => {
  it("renders live runtime status and capabilities from the API", async () => {
    stubApi();
    renderDashboard();

    await waitFor(() => expect(screen.getByText(/V1\.0-A/)).toBeInTheDocument());
    expect(screen.getByText(/1\.0\.0a1/)).toBeInTheDocument();
    // capability matrix renders a row per dependency
    expect(screen.getByText("FFmpeg")).toBeInTheDocument();
    expect(screen.getByText("librosa")).toBeInTheDocument();
    expect(screen.getAllByText("可用").length).toBeGreaterThanOrEqual(6);
  });

  it("shows an actionable message when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("无法连接后端 API")).toBeInTheDocument(),
    );
    expect(screen.getByText(/uvicorn app\.main:app/)).toBeInTheDocument();
  });
});

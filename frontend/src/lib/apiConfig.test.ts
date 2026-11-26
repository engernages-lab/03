import { afterEach, describe, expect, it, vi } from "vitest";

/** The API config is evaluated against window.location, so each case sets it. */
async function loadApi(host: string) {
  vi.resetModules();
  vi.stubGlobal("location", { ...window.location, hostname: host, origin: `https://${host}` });
  return import("./api");
}

describe("API configuration", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("treats a same-origin deployment as configured", async () => {
    const api = await loadApi("pocketscore.example.com");
    expect(api.API_CONFIG.mode).toBe("same-origin");
    expect(api.API_CONFIG.isMisconfigured).toBe(false);
  });

  it("flags a GitHub Pages build with no API origin as misconfigured", async () => {
    const api = await loadApi("engernages-lab.github.io");
    expect(api.API_CONFIG.mode).toBe("misconfigured");
    expect(api.API_CONFIG.isMisconfigured).toBe(true);
    expect(api.API_CONFIG.message).toContain("VITE_API_BASE_URL");
  });

  it("uses an absolute base URL when one was injected", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.pocketscore.example.com");
    const api = await loadApi("engernages-lab.github.io");
    expect(api.API_CONFIG.mode).toBe("absolute");
    expect(api.API_BASE).toBe("https://api.pocketscore.example.com");
    expect(api.API_V1).toBe("https://api.pocketscore.example.com/api/v1");
    expect(api.API_CONFIG.message).toBeNull();
  });

  it("never silently pretends a misconfigured build works", async () => {
    const api = await loadApi("engernages-lab.github.io");
    // the message is explicit; no mock fallback exists in the client
    expect(api.API_CONFIG.message).toBeTruthy();
    expect(api.API_CONFIG.message).not.toMatch(/mock|演示数据/i);
  });
});

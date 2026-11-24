import { describe, expect, it, vi, afterEach } from "vitest";
import { ApiError, api, buildUrl, staticUrl } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("buildUrl", () => {
  it("mounts the v1 prefix and serialises query parameters", () => {
    const url = buildUrl("/library/tracks", { limit: 20, offset: 0, q: "beethoven", empty: "" });
    expect(url).toContain("/api/v1/library/tracks");
    const parsed = new URL(url);
    expect(parsed.searchParams.get("limit")).toBe("20");
    expect(parsed.searchParams.get("q")).toBe("beethoven");
    expect(parsed.searchParams.has("empty")).toBe(false);
  });

  it("skips null and undefined values", () => {
    const parsed = new URL(buildUrl("/x", { a: undefined, b: null, c: false }));
    expect(parsed.searchParams.has("a")).toBe(false);
    expect(parsed.searchParams.has("b")).toBe(false);
    expect(parsed.searchParams.get("c")).toBe("false");
  });
});

describe("staticUrl", () => {
  it("passes absolute urls through and prefixes relative ones", () => {
    expect(staticUrl("https://cdn.example/a.png")).toBe("https://cdn.example/a.png");
    expect(staticUrl("/static/art/a.png")).toBe("/static/art/a.png");
    expect(staticUrl(null)).toBeUndefined();
  });
});

describe("api error handling", () => {
  it("unwraps the backend error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "NOT_FOUND", message: "MusicDocument not found", request_id: "abc" },
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(api.get("/documents/missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      code: "NOT_FOUND",
      message: "MusicDocument not found",
      requestId: "abc",
    });
  });

  it("maps transport failures to a network ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    try {
      await api.get("/health");
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).status).toBe(0);
      expect((error as ApiError).code).toBe("NETWORK_ERROR");
    }
  });

  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api.del("/documents/x")).resolves.toBeUndefined();
  });
});

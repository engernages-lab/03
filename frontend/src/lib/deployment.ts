/** Deployment-shape detection used to explain degraded modes honestly. */

/**
 * True when the SPA is served as a static site (GitHub Pages) instead of the
 * single-container deployment that also serves `/api`. In that case the UI must
 * say that no API is attached rather than pretending requests failed randomly.
 */
export function isStaticPagesPreview(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return host.endsWith("github.io") || host.endsWith("githubusercontent.com");
}

export function apiBaseOverride(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
}

/** True when a public API URL was injected at build time. */
export function hasConfiguredApi(): boolean {
  return apiBaseOverride().trim().length > 0;
}

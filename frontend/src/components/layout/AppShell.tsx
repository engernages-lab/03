import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { PlayerBar } from "./PlayerBar";
import { navItemFor } from "../../lib/nav";
import { API_CONFIG } from "../../lib/api";

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const item = navItemFor(location.pathname);

  return (
    <div className="flex h-screen overflow-hidden bg-studio-950">
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={item?.label ?? "PocketScore AI"}
          subtitle={item && !item.ready ? `计划于 ${item.hint} 阶段开放` : undefined}
          onMenu={() => setMobileOpen(true)}
        />
        <main className="min-h-0 flex-1 overflow-y-auto">
          {API_CONFIG.isMisconfigured && (
            <div
              data-testid="api-config-banner"
              className="border-b border-key-amber/40 bg-key-amber/10 px-4 py-2 text-[11px] text-key-amber sm:px-6"
            >
              {API_CONFIG.message}
            </div>
          )}
          <div className="mx-auto w-full max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </div>
        </main>
        <PlayerBar />
      </div>
    </div>
  );
}

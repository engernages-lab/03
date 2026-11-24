import { NavLink, useLocation } from "react-router-dom";
import clsx from "clsx";
import { AudioLines, ChevronsLeft, X } from "lucide-react";
import { NAV_GROUPS } from "../../lib/nav";
import { useHealth } from "../../lib/hooks";
import { Badge, Dot } from "../ui/Badge";

export function Sidebar({
  mobileOpen,
  onClose,
}: {
  mobileOpen: boolean;
  onClose: () => void;
}) {
  const { data: health, isError, isLoading } = useHealth();
  const location = useLocation();

  const statusTone = isError ? "danger" : health ? "success" : "warning";
  const statusText = isLoading ? "连接中" : isError ? "后端离线" : health ? "已连接" : "未知";

  return (
    <>
      <div
        className={clsx(
          "fixed inset-0 z-30 bg-black/60 backdrop-blur-sm transition-opacity lg:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={clsx(
          "z-40 flex h-full w-[248px] shrink-0 flex-col border-r border-studio-800 bg-studio-900/95",
          "fixed inset-y-0 left-0 transition-transform duration-200 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          <div className="flex items-center gap-2.5">
            <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-accent to-key-cyan text-studio-950 shadow-glow">
              <AudioLines size={18} strokeWidth={2.6} />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold tracking-tight text-white">PocketScore</p>
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-studio-400">
                AI · {health?.stage ?? "V1.0-A"}
              </p>
            </div>
          </div>
          <button className="btn-icon lg:hidden" onClick={onClose} aria-label="关闭导航">
            <X size={16} />
          </button>
        </div>

        <nav className="flex-1 space-y-5 overflow-y-auto px-2.5 pb-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.title}>
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-studio-500">
                {group.title}
              </p>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = location.pathname === item.to;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={onClose}
                      className={clsx("nav-link", active && "nav-link-active", !item.ready && "opacity-60")}
                      title={item.ready ? item.label : `${item.label} · 计划于 ${item.hint} 阶段开放`}
                    >
                      <Icon size={16} className="shrink-0" />
                      <span className="flex-1 truncate">{item.label}</span>
                      {!item.ready && item.hint && (
                        <span className="rounded bg-studio-800 px-1.5 py-0.5 font-mono text-[9px] text-studio-500">
                          {item.hint}
                        </span>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-studio-800 px-3 py-3">
          <div className="flex items-center justify-between rounded-lg bg-studio-950/60 px-3 py-2">
            <span className="flex items-center gap-2 text-xs text-studio-300">
              <Dot tone={statusTone} pulse={!isError} />
              API {statusText}
            </span>
            <Badge tone={statusTone === "success" ? "success" : statusTone === "danger" ? "danger" : "warning"}>
              {health?.environment ?? "dev"}
            </Badge>
          </div>
          <p className="mt-2 flex items-center gap-1 px-1 font-mono text-[10px] text-studio-600">
            <ChevronsLeft size={10} /> v{health?.version ?? "1.0.0a1"}
          </p>
        </div>
      </aside>
    </>
  );
}

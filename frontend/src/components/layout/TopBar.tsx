import { Menu, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useHealth } from "../../lib/hooks";
import { Dot } from "../ui/Badge";

export function TopBar({
  title,
  subtitle,
  onMenu,
  actions,
}: {
  title: string;
  subtitle?: string;
  onMenu: () => void;
  actions?: React.ReactNode;
}) {
  const queryClient = useQueryClient();
  const { isFetching } = useHealth();

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b border-studio-800 bg-studio-950/85 px-4 backdrop-blur sm:px-6">
      <button className="btn-icon lg:hidden" onClick={onMenu} aria-label="打开导航">
        <Menu size={16} />
      </button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="truncate text-[11px] text-studio-500">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">
        {actions}
        <button
          className="btn-icon"
          onClick={() => queryClient.invalidateQueries()}
          title="刷新数据"
          aria-label="刷新数据"
        >
          <RefreshCw size={15} className={clsx(isFetching && "animate-spin")} />
        </button>
        <span className="hidden items-center gap-1.5 rounded-lg border border-studio-800 bg-studio-900 px-2.5 py-1.5 text-[11px] text-studio-400 sm:flex">
          <Dot tone="success" />
          工作站就绪
        </span>
      </div>
    </header>
  );
}

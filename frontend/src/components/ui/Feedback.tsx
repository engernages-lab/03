import clsx from "clsx";

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2 text-sm text-studio-400", className)}>
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-studio-600 border-t-accent"
        role="status"
        aria-label={label ?? "加载中"}
      />
      {label && <span>{label}</span>}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-studio-800/80", className)} />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      {icon && <div className="rounded-2xl border border-studio-800 bg-studio-900 p-4 text-studio-400">{icon}</div>}
      <div className="space-y-1">
        <p className="text-sm font-semibold text-studio-100">{title}</p>
        {description && <p className="max-w-md text-xs leading-relaxed text-studio-400">{description}</p>}
      </div>
      {action}
    </div>
  );
}

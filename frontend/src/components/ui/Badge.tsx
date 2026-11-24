import clsx from "clsx";
import type { ReactNode } from "react";

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "violet";

const TONES: Record<Tone, string> = {
  neutral: "border-studio-700 bg-studio-800/70 text-studio-300",
  success: "border-accent/30 bg-accent/10 text-accent",
  warning: "border-key-amber/30 bg-key-amber/10 text-key-amber",
  danger: "border-key-rose/30 bg-key-rose/10 text-key-rose",
  info: "border-key-cyan/30 bg-key-cyan/10 text-key-cyan",
  violet: "border-key-violet/30 bg-key-violet/10 text-key-violet",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium leading-5",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral", pulse = false }: { tone?: Tone; pulse?: boolean }) {
  const color: Record<Tone, string> = {
    neutral: "bg-studio-500",
    success: "bg-accent",
    warning: "bg-key-amber",
    danger: "bg-key-rose",
    info: "bg-key-cyan",
    violet: "bg-key-violet",
  };
  return (
    <span className="relative flex h-2 w-2">
      {pulse && <span className={clsx("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", color[tone])} />}
      <span className={clsx("relative inline-flex h-2 w-2 rounded-full", color[tone])} />
    </span>
  );
}

import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, Construction } from "lucide-react";

export function ComingSoonPage({ stage, title }: { stage: string; title: string }) {
  const location = useLocation();
  const isMissing = stage === "V1.0-A";

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="rounded-2xl border border-studio-800 bg-studio-900 p-5 text-key-amber">
        <Construction size={26} />
      </div>
      <div className="space-y-1.5">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <p className="max-w-lg text-sm leading-relaxed text-studio-400">
          {isMissing
            ? `没有匹配到路由 ${location.pathname}。请从左侧导航进入已开放的模块。`
            : `该模块在开发计划中属于 ${stage} 阶段，当前尚未交付。为避免展示假数据，此页面只说明状态，不提供占位内容。`}
        </p>
      </div>
      <Link to="/dashboard" className="btn-ghost">
        <ArrowLeft size={15} /> 返回工作台
      </Link>
    </div>
  );
}

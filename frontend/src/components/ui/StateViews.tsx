import React from "react";
import { AlertTriangle, Info, RefreshCw, Layers, ShieldAlert } from "lucide-react";

export function LoadingView({
  label = "Querying authoritative marine services...",
  variant = "default",
}: {
  label?: string;
  variant?: "default" | "graphite";
}) {
  if (variant === "graphite") {
    return (
      <div className="flex flex-col items-center justify-center py-10 px-4 text-center space-y-3 font-sans">
        <div className="w-6 h-6 rounded-full border-2 border-white/20 border-t-white animate-spin" />
        <span className="text-xs text-[#9ca3af] font-normal">{label}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-10 px-4 text-center space-y-3">
      <div className="w-8 h-8 rounded-full border-2 border-ocean-teal/20 border-t-ocean-teal-light animate-spin" />
      <span className="text-xs font-mono text-ocean-muted">{label}</span>
    </div>
  );
}

export function ErrorView({
  message,
  detail,
  onRetry,
  variant = "default",
}: {
  message: string;
  detail?: string;
  onRetry?: () => void;
  variant?: "default" | "graphite";
}) {
  if (variant === "graphite") {
    return (
      <div className="bg-[#221a1a] rounded-lg p-4 border border-[#3b2424] text-center space-y-2.5 font-sans">
        <div className="w-7 h-7 rounded-full bg-[#351e1e] text-[#dca3a3] mx-auto flex items-center justify-center">
          <AlertTriangle className="w-3.5 h-3.5" />
        </div>
        <div className="space-y-1">
          <p className="text-xs font-medium text-[#e0a8a8]">{message}</p>
          {detail && <p className="text-[11px] font-mono text-[#8c9096]">{detail}</p>}
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-md bg-[#1a1b1e] border border-[#2c2d31] text-xs text-[#d1d5db] hover:text-white transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="ocean-panel rounded-lg p-5 border-rose-500/20 text-center space-y-3">
      <div className="w-8 h-8 rounded-full bg-rose-500/10 text-rose-400 mx-auto flex items-center justify-center">
        <AlertTriangle className="w-4 h-4" />
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium text-rose-300">{message}</p>
        {detail && <p className="text-[11px] font-mono text-ocean-dim">{detail}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center space-x-1.5 px-3 py-1 rounded bg-ocean-surface border border-ocean-border text-xs text-ocean-text hover:text-white transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          <span>Retry</span>
        </button>
      )}
    </div>
  );
}

export function SourceUnavailableView({
  reason,
  subject,
  variant = "default",
}: {
  reason: string;
  subject?: string;
  variant?: "default" | "graphite";
}) {
  if (variant === "graphite") {
    return (
      <div className="bg-[#111214] rounded-lg p-3.5 border border-[#202124] text-left space-y-1.5 font-sans">
        <div className="flex items-center space-x-2 text-[#e5e7eb]">
          <Info className="w-3.5 h-3.5 text-[#9ca3af] shrink-0" />
          <span className="text-xs font-medium text-white">Source Status</span>
        </div>
        <p className="text-xs text-[#9ca3af] leading-relaxed">
          {reason}
        </p>
        {subject && (
          <p className="text-[11px] text-[#8e8e93] font-mono">
            Scope: {subject}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="ocean-panel-subtle rounded-lg p-4 border-ocean-border text-left space-y-2">
      <div className="flex items-center space-x-2 text-ocean-sand">
        <Info className="w-4 h-4 text-ocean-sand/80 shrink-0" />
        <span className="text-xs font-medium">Source Status</span>
      </div>
      <p className="text-xs text-ocean-muted leading-relaxed font-mono">
        {reason}
      </p>
      {subject && (
        <p className="text-[11px] text-ocean-dim">
          Scope: {subject}
        </p>
      )}
    </div>
  );
}

export function EmptyDataView({
  title = "No observations found",
  description = "No accepted observations match the requested coordinates, radius, or time window.",
  variant = "default",
}: {
  title?: string;
  description?: string;
  variant?: "default" | "graphite";
}) {
  if (variant === "graphite") {
    return (
      <div className="py-8 px-4 text-center space-y-2 text-[#9ca3af] font-sans">
        <div className="w-8 h-8 rounded-full bg-[#111214] border border-[#202124] text-[#8e8e93] mx-auto flex items-center justify-center">
          <Layers className="w-4 h-4" />
        </div>
        <p className="text-xs font-medium text-white">{title}</p>
        <p className="text-xs text-[#9ca3af] max-w-xs mx-auto leading-relaxed">
          {description}
        </p>
      </div>
    );
  }

  return (
    <div className="py-8 px-4 text-center space-y-2 text-ocean-muted">
      <div className="w-8 h-8 rounded-full bg-ocean-surface/60 text-ocean-dim mx-auto flex items-center justify-center">
        <Layers className="w-4 h-4" />
      </div>
      <p className="text-xs font-medium text-ocean-text">{title}</p>
      <p className="text-xs text-ocean-dim max-w-xs mx-auto leading-relaxed">
        {description}
      </p>
    </div>
  );
}

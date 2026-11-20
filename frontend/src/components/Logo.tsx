import { useId } from "react";
import clsx from "clsx";

export function LogoMark({ size = 34 }: { size?: number }) {
  const gradientId = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden>
      <defs>
        <linearGradient id={gradientId} x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stopColor="#38B000" />
          <stop offset="1" stopColor="#0086BD" />
        </linearGradient>
      </defs>
      <path
        d="M32 7 54 16v17.2C54 45.1 45.2 54.6 32 58 18.8 54.6 10 45.1 10 33.2V16L32 7Z"
        stroke={`url(#${gradientId})`}
        strokeWidth="2.6"
        strokeLinejoin="round"
        fill="rgba(0,168,232,0.10)"
      />
      <path
        d="M22 32.5 28.8 39.5 43 24"
        stroke={`url(#${gradientId})`}
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Brand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className={clsx("flex items-center gap-2.5", collapsed && "justify-center")}>
      <div className="relative">
        <div className="absolute inset-0 rounded-xl bg-mint-400/20 blur-lg" />
        <LogoMark />
      </div>
      {!collapsed && (
        <div className="leading-none">
          <p className="text-[15px] font-semibold tracking-tight text-white">
            Fraud<span className="text-mint-400">Lens</span>
          </p>
          <p className="mt-1 text-[8.5px] font-medium uppercase tracking-[0.24em] text-slate-500">
            Risk intelligence
          </p>
        </div>
      )}
    </div>
  );
}

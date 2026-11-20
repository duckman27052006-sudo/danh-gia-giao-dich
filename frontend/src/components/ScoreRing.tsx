import clsx from "clsx";

export function ScoreRing({
  score,
  size = 56,
  stroke = 4,
  showLabel = true,
  className,
}: {
  score: number;
  size?: number;
  stroke?: number;
  showLabel?: boolean;
  className?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(score, 100));
  const offset = circumference * (1 - clamped / 100);
  const color =
    clamped >= 78 ? "#E5484D" : clamped >= 55 ? "#E8A33D" : clamped >= 35 ? "#6CB6FF" : "#00A8E8";

  return (
    <div className={clsx("relative inline-flex items-center justify-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(4,60,90,0.10)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.2,0.7,0.3,1)", filter: `drop-shadow(0 0 6px ${color}55)` }}
        />
      </svg>
      {showLabel && (
        <span className="absolute font-mono text-[12px] font-medium tabular-nums text-white" style={{ fontSize: size <= 44 ? 11 : 13 }}>
          {clamped.toFixed(0)}
        </span>
      )}
    </div>
  );
}

import { useId, useState, type ReactNode } from "react";
import clsx from "clsx";
import { ChevronRight, type LucideIcon } from "lucide-react";

/**
 * Các khối giao diện dùng chung để giảm mật độ thông tin:
 * mỗi màn hình chỉ nên có vài khối "nổi" và phần chi tiết ẩn sau một cú bấm.
 */

/* ── tiêu đề khối ─────────────────────────────────────────────── */
export function PanelHeader({
  title,
  subtitle,
  actions,
  icon: Icon,
  badge,
  className,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  icon?: LucideIcon;
  badge?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex items-start justify-between gap-3 px-4 pt-4", className)}>
      <div className="flex min-w-0 items-start gap-2.5">
        {Icon && (
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[rgba(4,60,90,0.12)] bg-[#eef8fe] text-[#2f7288]">
            <Icon size={14} />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold text-white">
            {title}
            {badge && <span className="chip">{badge}</span>}
          </h2>
          {subtitle && <p className="mt-0.5 text-[10.5px] leading-snug text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
    </div>
  );
}

/* ── khối thu gọn được ─────────────────────────────────────────── */
export function Disclosure({
  title,
  subtitle,
  badge,
  actions,
  defaultOpen = false,
  children,
  className,
  bodyClassName,
  icon: Icon,
}: {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  actions?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  icon?: LucideIcon;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();

  return (
    <section className={clsx("panel overflow-hidden", className)}>
      <div className="flex items-start gap-2 px-4 py-3">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={bodyId}
          className="group flex min-w-0 flex-1 items-start gap-2.5 rounded-lg text-left outline-none transition focus-visible:ring-2 focus-visible:ring-azure-400/60"
        >
          <ChevronRight
            size={14}
            className={clsx("mt-1 shrink-0 text-slate-500 transition-transform duration-200", open && "rotate-90")}
          />
          {Icon && (
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[rgba(4,60,90,0.12)] bg-[#eef8fe] text-[#2f7288]">
              <Icon size={14} />
            </span>
          )}
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2 text-[12.5px] font-semibold text-white">
              {title}
              {badge && <span className="chip">{badge}</span>}
            </span>
            {subtitle && (
              <span className={clsx("mt-0.5 block text-[10.5px] leading-snug text-slate-500", !open && "truncate")}>
                {subtitle}
              </span>
            )}
          </span>
        </button>
        {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
      </div>
      {open && (
        <div id={bodyId} className={clsx("border-t border-[rgba(4,60,90,0.10)]", bodyClassName)}>
          {children}
        </div>
      )}
    </section>
  );
}

/* ── dải chỉ số gọn (thay 3–4 thẻ KPI to) ──────────────────────── */
export type StatTone = "neutral" | "good" | "warn" | "danger";

const TONE_DOT: Record<StatTone, string> = {
  neutral: "bg-azure-400",
  good: "bg-mint-400",
  warn: "bg-amber-400",
  danger: "bg-coral-400",
};

export function StatStrip({
  items,
  className,
}: {
  items: { label: string; value: ReactNode; hint?: ReactNode; tone?: StatTone; onClick?: () => void }[];
  className?: string;
}) {
  return (
    <div className={clsx("panel flex flex-wrap items-stretch", className)}>
      {items.map((item, index) => {
        const Wrapper = item.onClick ? "button" : "div";
        return (
          <Wrapper
            key={`${item.label}-${index}`}
            onClick={item.onClick}
            className={clsx(
              "flex min-w-[132px] flex-1 items-center gap-2.5 px-4 py-2.5 text-left",
              index > 0 && "border-l border-[rgba(4,60,90,0.10)]",
              item.onClick && "transition hover:bg-white/50",
            )}
          >
            <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", TONE_DOT[item.tone ?? "neutral"])} />
            <span className="min-w-0">
              <span className="block text-[9.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                {item.label}
              </span>
              <span className="mono block text-[15px] font-semibold leading-tight text-white">{item.value}</span>
            </span>
            {item.hint && <span className="ml-auto text-[10px] text-slate-500">{item.hint}</span>}
          </Wrapper>
        );
      })}
    </div>
  );
}

/* ── tab dạng viên thuốc ───────────────────────────────────────── */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className,
}: {
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={clsx("inline-flex flex-wrap items-center gap-1 rounded-xl bg-[rgba(4,60,90,0.055)] p-1 ring-1 ring-[rgba(4,60,90,0.10)]", className)}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-pressed={active}
            className={clsx(
              "rounded-lg px-2.5 py-1.5 text-[11.5px] font-medium transition",
              active ? "bg-white font-semibold text-[#04384d] shadow-sm ring-1 ring-[rgba(4,60,90,0.10)]" : "text-[#2f7288] hover:text-[#04384d]",
            )}
          >
            {option.label}
            {typeof option.count === "number" && (
              <span className="mono ml-1.5 text-[10.5px] text-slate-500">{option.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* ── danh sách nhãn → giá trị gọn ──────────────────────────────── */
export function DataList({
  items,
  columns = 3,
  className,
}: {
  items: { label: string; value: ReactNode; emphasis?: boolean }[];
  columns?: 2 | 3 | 4;
  className?: string;
}) {
  const grid = { 2: "sm:grid-cols-2", 3: "sm:grid-cols-3", 4: "sm:grid-cols-2 lg:grid-cols-4" }[columns];
  return (
    <dl className={clsx("grid gap-x-4 gap-y-3", grid, className)}>
      {items.map((item, index) => (
        <div key={`${item.label}-${index}`} className="min-w-0">
          <dt className="text-[9.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">{item.label}</dt>
          <dd
            className={clsx(
              "mt-0.5 truncate text-[12.5px]",
              item.emphasis ? "font-semibold text-white" : "text-[#14546c]",
            )}
            title={typeof item.value === "string" ? item.value : undefined}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* ── hàng chờ chốt chặn cho phần "xem thêm" ────────────────────── */
export function ShowMore({
  expanded,
  onClick,
  rest,
}: {
  expanded: boolean;
  onClick: () => void;
  rest: number;
}) {
  if (rest <= 0 && !expanded) return null;
  return (
    <button type="button" onClick={onClick} className="btn-ghost btn-sm">
      {expanded ? "Thu gọn" : `Xem thêm ${rest}`}
    </button>
  );
}


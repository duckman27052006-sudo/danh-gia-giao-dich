import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  ChevronRight,
  Clock,
  Cpu,
  Inbox,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  Users,
  Wallet,
} from "lucide-react";
import { Link } from "react-router-dom";
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import clsx from "clsx";
import { api } from "@/lib/api";
import {
  categoryLabel,
  compactVND,
  formatNumber,
  formatPercent,
  formatVND,
  RISK_BANDS,
  slaState,
  timeAgo,
} from "@/lib/format";
import type { CaseStats, DashboardData } from "@/lib/types";
import { EmptyState, ErrorState, PageHeader, StatCard } from "@/components/Ui";
import { ScoreRing } from "@/components/ScoreRing";
import { RiskBadge, PriorityBadge } from "@/components/Badges";
import { Avatar } from "@/components/Avatar";

const PIE_COLORS: Record<string, string> = { P1: "#E5484D", P2: "#E8A33D", P3: "#7C93A8" };

function chartDate(value: string) {
  return `${value.slice(8, 10)}/${value.slice(5, 7)}`;
}

function axisMoney(value: number) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(0)} tỷ`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(0)} tr`;
  return `${value}`;
}

function TrendTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  return (
    <div className="rounded-xl border border-white/10 bg-ink-850/95 px-3.5 py-2.5 shadow-panel backdrop-blur">
      <p className="mb-1.5 text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className="text-[11.5px] text-slate-300">
        Dòng tiền <span className="font-mono text-white">{formatVND(point.volume)}</span>
      </p>
      <p className="text-[11.5px] text-slate-300">
        Giao dịch <span className="font-mono text-white">{formatNumber(point.total)}</span>
      </p>
      <p className="text-[11.5px] text-coral-400">
        Gắn cờ <span className="font-mono">{formatNumber(point.flagged)}</span>
      </p>
      <p className="text-[11.5px] text-mint-300">
        Xác nhận gian lận <span className="font-mono">{formatNumber(point.confirmed)}</span>
      </p>
    </div>
  );
}

function PriorityDonut({ data, total, stats }: { data: { name: string; value: number }[]; total: number; stats?: CaseStats }) {
  const pie = data.length ? data : [{ name: "P3", value: 0 }];
  return (
    <div>
      <div className="relative mx-auto h-[168px] w-full max-w-[230px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pie} dataKey="value" nameKey="name" innerRadius={55} outerRadius={76} paddingAngle={3} stroke="none">
              {pie.map((entry) => (
                <Cell key={entry.name} fill={PIE_COLORS[entry.name] ?? "#7C93A8"} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <p className="font-mono text-[24px] font-medium text-white">{total}</p>
          <p className="text-[9.5px] uppercase tracking-[0.14em] text-slate-500">case đang mở</p>
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {data.map((item) => (
          <div key={item.name} className="flex items-center gap-2.5">
            <span className="h-2 w-2 rounded-full" style={{ background: PIE_COLORS[item.name] }} />
            <span className="flex-1 text-[11.5px] text-slate-400">{item.name}</span>
            <span className="font-mono text-[11.5px] text-slate-200">{item.value}</span>
            <span className="w-[52px] text-right text-[9.5px] text-slate-600">
              {total ? Math.round((item.value / total) * 100) : 0}%
            </span>
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
          <p className="flex items-center gap-1 text-[9.5px] text-slate-500">
            <Users size={10} /> Chưa phân công
          </p>
          <p className="mt-1 font-mono text-[14px] text-white">{stats?.unassigned ?? "—"}</p>
        </div>
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
          <p className="flex items-center gap-1 text-[9.5px] text-slate-500">
            <Clock size={10} /> Quá SLA
          </p>
          <p className="mt-1 font-mono text-[14px] text-coral-400">{stats?.overdue ?? "—"}</p>
        </div>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const [days, setDays] = useState(30);
  const dashboard = useQuery({
    queryKey: ["dashboard", days],
    queryFn: () => api<DashboardData>(`/dashboard?days=${days}`),
  });
  const stats = useQuery({
    queryKey: ["case-stats"],
    queryFn: () => api<CaseStats>("/cases/stats"),
  });

  const data = dashboard.data;
  const summary = data?.summary;
  const openCases = (stats.data?.by_status.open ?? 0) + (stats.data?.by_status.in_review ?? 0) + (stats.data?.by_status.awaiting_info ?? 0);
  const maxCategory = useMemo(
    () => Math.max(...(data?.categories.map((item) => item.extra ?? 0) ?? [1]), 1),
    [data],
  );

  if (dashboard.isError) {
    return <ErrorState message={dashboard.error.message} onRetry={() => dashboard.refetch()} />;
  }

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Trung tâm điều hành"
        title="Tổng quan rủi ro"
        subtitle="Theo dõi dòng tiền, cảnh báo gian lận và hiệu quả hàng chờ điều tra. Số liệu tổng hợp từ rule engine và model ML."
        actions={
          <>
            <div className="flex rounded-xl border border-white/10 bg-ink-900/60 p-0.5">
              {[7, 30, 90].map((value) => (
                <button
                  key={value}
                  onClick={() => setDays(value)}
                  className={clsx(
                    "rounded-[10px] px-2.5 py-1.5 text-[10.5px] font-medium transition",
                    days === value ? "bg-white/[0.09] text-white" : "text-slate-500 hover:text-slate-300",
                  )}
                >
                  {value} ngày
                </button>
              ))}
            </div>
            <button className="btn-ghost btn-sm" onClick={() => dashboard.refetch()} title="Tải lại">
              <RefreshCw size={13} className={dashboard.isFetching ? "animate-spin" : ""} />
              <span className="hidden sm:inline">Tải lại</span>
            </button>
          </>
        }
      />

      {!data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="panel h-[118px] p-5">
              <div className="skeleton h-2.5 w-24" />
              <div className="skeleton mt-4 h-7 w-32" />
              <div className="skeleton mt-3 h-2 w-40" />
            </div>
          ))}
        </div>
      ) : (
        <>
          {summary && (summary.unassigned_cases > 0 || (stats.data?.overdue ?? 0) > 0) && (
            <div className="mb-4 flex flex-col gap-3 rounded-xl border border-amber-400/20 bg-amber-500/[0.055] px-4 py-3 sm:flex-row sm:items-center">
              <div className="flex items-center gap-2.5 text-amber-400">
                <ShieldAlert size={15} />
                <p className="text-[11.5px] font-medium">Cần chú ý hôm nay</p>
              </div>
              <p className="flex-1 text-[11px] text-slate-400">
                <span className="font-mono text-amber-300">{summary.unassigned_cases}</span> case chưa phân công ·{" "}
                <span className="font-mono text-coral-400">{stats.data?.overdue ?? 0}</span> case quá hạn SLA ·{" "}
                <span className="font-mono text-white">{summary.p1_cases}</span> case P1 đang mở
              </p>
              <Link to="/queue?priority=P1" className="btn-ghost btn-sm shrink-0">
                Xử lý ngay <ArrowRight size={12} />
              </Link>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Tổng giá trị giao dịch"
              value={compactVND(summary?.total_volume ?? 0)}
              icon={Wallet}
              accent="mint"
              trend={{ value: summary?.delta_volume_pct ?? 0 }}
              hint={`${formatNumber(summary?.total_transactions ?? 0)} giao dịch`}
            />
            <StatCard
              label="Giao dịch bị gắn cờ"
              value={formatNumber(summary?.flagged_transactions ?? 0)}
              icon={ShieldAlert}
              accent="coral"
              hint={`${formatPercent(summary?.fraud_rate ?? 0)} trên tổng giao dịch`}
            />
            <StatCard
              label="Case đang mở"
              value={formatNumber(summary?.open_cases ?? 0)}
              icon={Inbox}
              accent="amber"
              hint={`${summary?.p1_cases ?? 0} P1 · ${summary?.unassigned_cases ?? 0} chưa phân công`}
            />
            <StatCard
              label="Độ chính xác cảnh báo"
              value={formatPercent(summary?.precision ?? 0)}
              icon={Target}
              accent="azure"
              hint={`${summary?.confirmed_fraud ?? 0} đúng / ${summary?.false_positive ?? 0} báo sai`}
            />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-12">
            <div className="panel p-5 xl:col-span-8">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[13px] font-medium text-white">Dòng tiền & cảnh báo</p>
                  <p className="mt-0.5 text-[10.5px] text-slate-500">
                    Cột là số giao dịch bị gắn cờ · vùng là tổng giá trị giao dịch theo ngày
                  </p>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <span className="h-1.5 w-3 rounded-full bg-sky-400/70" /> Dòng tiền
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-coral-400" /> Gắn cờ
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-mint-300" /> Xác nhận
                  </span>
                </div>
              </div>
              <div className="h-[286px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={data.trend} margin={{ top: 4, right: 4, left: -14, bottom: 0 }}>
                    <defs>
                      <linearGradient id="volume-fill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00A8E8" stopOpacity={0.34} />
                        <stop offset="100%" stopColor="#00A8E8" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(4,60,90,0.10)" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={chartDate}
                      interval={days > 30 ? 13 : days > 7 ? 4 : 0}
                      axisLine={false}
                      tickLine={false}
                      dy={8}
                    />
                    <YAxis yAxisId="volume" tickFormatter={axisMoney} axisLine={false} tickLine={false} width={58} />
                    <YAxis yAxisId="count" orientation="right" axisLine={false} tickLine={false} width={30} />
                    <Tooltip content={<TrendTooltip />} cursor={{ stroke: "rgba(255,255,255,0.12)" }} />
                    <Area
                      yAxisId="volume"
                      type="monotone"
                      dataKey="volume"
                      stroke="#00A8E8"
                      strokeWidth={1.6}
                      fill="url(#volume-fill)"
                      name="Dòng tiền"
                    />
                    <Bar yAxisId="count" dataKey="flagged" fill="#E5484D" opacity={0.75} barSize={days > 30 ? 4 : 7} radius={[2, 2, 0, 0]} name="Gắn cờ" />
                    <Line
                      yAxisId="count"
                      type="monotone"
                      dataKey="confirmed"
                      stroke="#38B000"
                      strokeWidth={1.4}
                      dot={false}
                      strokeDasharray="3 3"
                      name="Xác nhận"
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel p-5 xl:col-span-4">
              <div className="mb-1 flex items-center justify-between">
                <div>
                  <p className="text-[13px] font-medium text-white">Hàng chờ ưu tiên</p>
                  <p className="mt-0.5 text-[10.5px] text-slate-500">Case chưa đóng theo mức ưu tiên</p>
                </div>
                <Link to="/queue" className="link-muted text-[10.5px]">
                  Xem tất cả
                </Link>
              </div>
              <PriorityDonut data={data.priority_queue} total={openCases} stats={stats.data} />
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-12">
            <div className="panel p-5 xl:col-span-4">
              <p className="text-[13px] font-medium text-white">Phân bố điểm rủi ro</p>
              <p className="mt-0.5 text-[10.5px] text-slate-500">{formatNumber(summary?.total_transactions ?? 0)} giao dịch trong kỳ</p>
              <div className="mt-5 space-y-3.5">
                {[...data.score_bands]
                  .sort((a, b) => {
                    const order = ["critical", "high", "medium", "low"];
                    const keyOf = (label: string) =>
                      Object.entries(RISK_BANDS).find(([, config]) => config.label === label)?.[0] ?? "low";
                    return order.indexOf(keyOf(a.name)) - order.indexOf(keyOf(b.name));
                  })
                  .map((band) => {
                  const key = Object.entries(RISK_BANDS).find(([, config]) => config.label === band.name)?.[0] ?? "low";
                  const config = RISK_BANDS[key];
                  const total = data.score_bands.reduce((sum, item) => sum + item.value, 0) || 1;
                  return (
                    <div key={band.name}>
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="flex items-center gap-2 text-[11px] text-slate-400">
                          <span className={clsx("h-1.5 w-1.5 rounded-full", config.dot)} /> {band.name}
                        </span>
                        <span className="font-mono text-[10.5px] text-slate-500">
                          {formatNumber(band.value)} · {((band.value / total) * 100).toFixed(1).replace(".", ",")}%
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                        <div
                          className={clsx("h-full rounded-full", config.dot)}
                          style={{ width: `${Math.max((band.value / total) * 100, 1.5)}%`, opacity: 0.8 }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-5 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
                <p className="text-[10px] leading-relaxed text-slate-500">
                  Ngưỡng cảnh báo hiện tại: <span className="font-mono text-slate-300">≥55</span> · rủi ro cao{" "}
                  <span className="font-mono text-slate-300">≥78</span>. Cấu hình tại trang{" "}
                  <Link to="/settings" className="text-mint-300 hover:underline">
                    Cài đặt
                  </Link>
                  .
                </p>
              </div>
            </div>

            <div className="panel p-5 xl:col-span-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[13px] font-medium text-white">Ngành hàng bị gắn cờ</p>
                  <p className="mt-0.5 text-[10.5px] text-slate-500">Top ngành theo số cảnh báo</p>
                </div>
                <Activity size={14} className="text-slate-600" />
              </div>
              <div className="mt-5 space-y-3.5">
                {data.categories.slice(0, 6).map((category) => (
                  <div key={category.name}>
                    <div className="mb-1 flex items-center justify-between text-[11px]">
                      <span className="text-slate-400">{categoryLabel(category.name)}</span>
                      <span className="font-mono text-[10.5px] text-slate-500">
                        <span className="text-coral-400">{category.extra ?? 0}</span> / {formatNumber(category.value)}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-coral-500/80 to-amber-400/70"
                        style={{ width: `${Math.max(((category.extra ?? 0) / maxCategory) * 100, 2)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-5 text-[10px] leading-relaxed text-slate-600">
                Tỷ lệ cảnh báo cao ở crypto, thẻ quà tặng và cá cược — nhóm ngành thường bị lợi dụng để rút tiền.
              </p>
            </div>

            <div className="panel p-5 xl:col-span-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[13px] font-medium text-white">Rule hit nhiều nhất</p>
                  <p className="mt-0.5 text-[10.5px] text-slate-500">Tín hiệu đóng góp vào điểm rule</p>
                </div>
                <Link to="/rules" className="link-muted text-[10.5px]">
                  Quản lý
                </Link>
              </div>
              <div className="mt-4 space-y-2.5">
                {data.rules_performance.slice(0, 4).map((rule) => (
                  <div key={rule.id} className="flex items-center gap-3 rounded-lg border border-white/[0.05] bg-white/[0.018] px-3 py-2.5">
                    <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", rule.enabled ? "bg-mint-400" : "bg-slate-600")} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[11px] text-slate-300">{rule.name}</p>
                      <p className="mt-0.5 text-[9.5px] text-slate-600">+{rule.weight} điểm · {rule.severity}</p>
                    </div>
                    <span className="font-mono text-[11px] text-slate-400">{formatNumber(rule.hits)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <Cpu size={12} className="text-mint-400" />
                  <p className="text-[10px] text-slate-500">
                    Model <span className="font-mono text-slate-300">{summary?.model_version}</span> · AUC{" "}
                    <span className="font-mono text-slate-300">{summary?.model_auc}</span>
                  </p>
                </div>
                <span className="chip text-[9px]">{summary?.ai_provider}</span>
              </div>
            </div>
          </div>

          <div className="panel mt-4 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
              <div>
                <p className="text-[13px] font-medium text-white">Cảnh báo mới nhất</p>
                <p className="mt-0.5 text-[10.5px] text-slate-500">Case rủi ro cao đang chờ analyst xác minh</p>
              </div>
              <Link to="/queue" className="btn-ghost btn-sm">
                Toàn bộ hàng chờ <ChevronRight size={13} />
              </Link>
            </div>
            {data.recent_alerts.length === 0 ? (
              <EmptyState icon={Inbox} title="Không có cảnh báo mở" description="Hàng chờ đang sạch. Các case mới sẽ xuất hiện ở đây." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[880px] border-collapse">
                  <thead>
                    <tr className="border-y border-white/[0.05] bg-white/[0.012]">
                      <th className="th">Case</th>
                      <th className="th">Khách hàng / Merchant</th>
                      <th className="th">Giá trị</th>
                      <th className="th">Điểm rủi ro</th>
                      <th className="th">Ưu tiên</th>
                      <th className="th">SLA</th>
                      <th className="th">Phụ trách</th>
                      <th className="th" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_alerts.map((item) => {
                      const sla = slaState(item.sla_due_at, item.status);
                      return (
                        <tr key={item.id} className="table-row group">
                          <td className="td">
                            <Link to={`/cases/${item.id}`} className="font-mono text-[11px] text-mint-300 hover:text-mint-200">
                              {item.code}
                            </Link>
                            <p className="mt-0.5 text-[9.5px] text-slate-600">{timeAgo(item.created_at)}</p>
                          </td>
                          <td className="td">
                            <p className="text-[12px] font-medium text-slate-200">{item.transaction.customer_name}</p>
                            <p className="mt-0.5 text-[10px] text-slate-500">
                              {item.transaction.merchant_name} · {categoryLabel(item.transaction.merchant_category)}
                            </p>
                          </td>
                          <td className="td font-mono text-[12px] text-slate-100">{compactVND(item.transaction.amount)}</td>
                          <td className="td">
                            <div className="flex items-center gap-2.5">
                              <ScoreRing score={item.risk_score} size={34} stroke={3} />
                              <RiskBadge band={item.transaction.risk_band} />
                            </div>
                          </td>
                          <td className="td"><PriorityBadge priority={item.priority} /></td>
                          <td className="td">
                            <span
                              className={clsx(
                                "text-[10.5px]",
                                sla.tone === "bad" ? "text-coral-400" : sla.tone === "warn" ? "text-amber-400" : "text-slate-500",
                              )}
                            >
                              {sla.label}
                            </span>
                          </td>
                          <td className="td">
                            {item.assignee ? (
                              <span className="flex items-center gap-1.5">
                                <Avatar name={item.assignee.full_name} size="xs" />
                                <span className="max-w-[90px] truncate text-[10.5px] text-slate-400">{item.assignee.full_name}</span>
                              </span>
                            ) : (
                              <span className="text-[10.5px] text-slate-600">Chưa gán</span>
                            )}
                          </td>
                          <td className="td text-right">
                            <Link to={`/cases/${item.id}`} className="text-slate-600 transition group-hover:text-mint-300">
                              <ArrowUpRight size={14} />
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="mt-4 flex flex-col gap-3 rounded-xl border border-white/[0.06] bg-white/[0.018] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2.5">
              <Sparkles size={13} className="text-mint-400" />
              <p className="text-[10.5px] text-slate-500">
                AI chỉ tạo bản giải thích và ghi chú nháp. Mọi kết luận gian lận cần analyst xác nhận và lưu audit trail.
              </p>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-slate-600">
              <span className="flex items-center gap-1">
                <ArrowDownRight size={11} /> {formatPercent(summary?.fraud_rate ?? 0)} alert rate
              </span>
              <span className="h-3 w-px bg-white/10" />
              <span className="font-mono">{summary?.model_version}</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

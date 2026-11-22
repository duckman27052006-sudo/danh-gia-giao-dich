import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  CheckCircle2,
  Filter,
  Plus,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  categoryLabel,
  channelLabel,
  compactVND,
  formatDateTime,
  formatVND,
} from "@/lib/format";
import type { Page, RuleHit, Transaction } from "@/lib/types";
import { RiskBadge } from "@/components/Badges";
import { EmptyState, ErrorState, PageHeader, SkeletonRows } from "@/components/Ui";
import { Disclosure, Segmented } from "@/components/Patterns";
import { Pagination } from "@/components/Pagination";
import { ScoreRing } from "@/components/ScoreRing";
import { Modal } from "@/components/Modal";
import { SimulateDialog } from "@/components/SimulateDialog";
import { useToast } from "@/lib/toast";

const BAND_TABS = [
  { value: "all", label: "Tất cả" },
  { value: "low", label: "Thấp" },
  { value: "medium", label: "Trung bình" },
  { value: "high", label: "Cao" },
  { value: "critical", label: "Rất cao" },
];

function IngestForm({ onDone }: { onDone: (txn: Transaction) => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    customer_name: "Nguyễn Văn Demo",
    customer_id: "CUS-DEMO-001",
    amount: "850000",
    merchant_name: "Shopee Việt Nam",
    merchant_category: "ecommerce",
    channel: "online",
    card_country: "VN",
    ip_country: "VN",
    device_id: "dev-demo-001",
  });

  const create = useMutation({
    mutationFn: () =>
      api<Transaction>("/transactions", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          amount: Number(form.amount),
          merchant_country: form.card_country,
          external_id: `MANUAL-${Date.now()}`,
        }),
      }),
    onSuccess: (txn) => {
      toast.push(
        txn.is_flagged ? "Giao dịch vượt ngưỡng và đã vào hàng chờ." : "Giao dịch dưới ngưỡng cảnh báo.",
        txn.is_flagged ? "success" : "info",
        "Đã chấm điểm",
      );
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["cases"] });
      queryClient.invalidateQueries({ queryKey: ["case-stats"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onDone(txn);
    },
    onError: (error) => toast.push(error.message, "error", "Không nhập được giao dịch"),
  });

  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Tên khách hàng</label>
          <input className="field" value={form.customer_name} onChange={update("customer_name")} />
        </div>
        <div>
          <label className="label">Mã khách hàng</label>
          <input className="field font-mono" value={form.customer_id} onChange={update("customer_id")} />
        </div>
        <div>
          <label className="label">Số tiền (VND)</label>
          <input className="field font-mono" type="number" min={1000} value={form.amount} onChange={update("amount")} />
        </div>
        <div>
          <label className="label">Kênh</label>
          <select className="field" value={form.channel} onChange={update("channel")}>
            <option value="online">Online</option>
            <option value="pos">POS</option>
            <option value="transfer">Chuyển khoản</option>
            <option value="atm">ATM</option>
          </select>
        </div>
        <div className="col-span-2">
          <label className="label">Merchant</label>
          <input className="field" value={form.merchant_name} onChange={update("merchant_name")} />
        </div>
        <div>
          <label className="label">Ngành hàng</label>
          <select className="field" value={form.merchant_category} onChange={update("merchant_category")}>
            {Object.entries({
              ecommerce: "Thương mại điện tử",
              crypto: "Tiền mã hóa",
              gift_card: "Thẻ quà tặng",
              gambling: "Cá cược",
              electronics: "Điện tử",
              jewelry: "Trang sức",
              travel: "Du lịch",
              food: "Ẩm thực",
              grocery: "Tạp hóa",
              utilities: "Tiện ích",
              subscription: "Đăng ký",
              cash_advance: "Ứng tiền mặt",
            }).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Thiết bị</label>
          <input className="field font-mono" value={form.device_id} onChange={update("device_id")} />
        </div>
        <div>
          <label className="label">Quốc gia thẻ</label>
          <input className="field uppercase" maxLength={2} value={form.card_country} onChange={update("card_country")} />
        </div>
        <div>
          <label className="label">Quốc gia IP</label>
          <input className="field uppercase" maxLength={2} value={form.ip_country} onChange={update("ip_country")} />
        </div>
      </div>
      <p className="text-[10px] leading-relaxed text-slate-500">
        Hệ thống tự tính feature hành vi từ lịch sử 30 ngày của khách hàng, áp rule engine và model ML ngay khi nhập.
      </p>
      <button className="btn-primary w-full" onClick={() => create.mutate()} disabled={create.isPending || !form.customer_id || !form.merchant_name}>
        {create.isPending ? "Đang chấm điểm…" : "Chấm điểm giao dịch"}
      </button>
    </div>
  );
}

function RuleHits({ hits }: { hits: RuleHit[] }) {
  if (!hits.length) return <p className="text-[11px] text-slate-500">Không rule nào khớp.</p>;
  return (
    <div className="space-y-1.5">
      {hits.map((hit) => (
        <div key={hit.rule_id} className="flex items-center justify-between gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
          <div className="flex items-center gap-2">
            <span className={clsx("h-1.5 w-1.5 rounded-full", hit.severity === "high" ? "bg-coral-400" : "bg-amber-400")} />
            <span className="text-[10.5px] text-slate-300">{hit.name}</span>
          </div>
          <span className="font-mono text-[9.5px] text-amber-400">+{hit.weight}</span>
        </div>
      ))}
    </div>
  );
}

export function TransactionsPage() {
  const [params] = useSearchParams();
  const { canEdit } = useAuth();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [band, setBand] = useState("all");
  const [channel, setChannel] = useState("all");
  const [flagFilter, setFlagFilter] = useState("all");
  const [range, setRange] = useState("30");
  const [sort, setSort] = useState("recent");
  const [page, setPage] = useState(1);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [simulateOpen, setSimulateOpen] = useState(false);
  const [selected, setSelected] = useState<Transaction | null>(null);
  const [created, setCreated] = useState<Transaction | null>(null);

  const activeAdvancedFilters = [
    channel !== "all",
    flagFilter !== "all",
    range !== "30",
    sort !== "recent",
  ].filter(Boolean).length;

  const dateFrom = useMemo(() => {
    if (range === "all") return null;
    const days = range === "today" ? 1 : Number(range);
    return new Date(Date.now() - days * 86_400_000).toISOString();
  }, [range]);

  const query = new URLSearchParams({ page: String(page), page_size: "18", sort });
  if (q) query.set("q", q);
  if (band !== "all") query.set("risk_band", band);
  if (channel !== "all") query.set("channel", channel);
  if (flagFilter !== "all") query.set("flagged", flagFilter === "flagged" ? "true" : "false");
  if (dateFrom && range !== "today") query.set("date_from", dateFrom);

  const transactions = useQuery({
    queryKey: ["transactions", q, band, channel, flagFilter, range, sort, page],
    queryFn: () => api<Page<Transaction>>(`/transactions?${query.toString()}`),
    placeholderData: (previous) => previous,
  });

  const change = (action: () => void) => {
    action();
    setPage(1);
  };

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Vận hành"
        title="Giao dịch"
        subtitle="Toàn bộ giao dịch đã ingest, kèm điểm ML, điểm rule và trạng thái điều tra tương ứng."
      />

      <Disclosure
        title="Bộ lọc nâng cao"
        subtitle="Kênh, cờ gắn, khoảng thời gian và cách sắp xếp"
        badge={activeAdvancedFilters > 0 ? `${activeAdvancedFilters} đang bật` : undefined}
        icon={SlidersHorizontal}
        className="mb-3"
      >
        <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4">
          <div>
            <label className="label" htmlFor="txn-filter-channel">
              Kênh
            </label>
            <select
              id="txn-filter-channel"
              value={channel}
              onChange={(event) => change(() => setChannel(event.target.value))}
              className="field py-2 text-[11px]"
            >
              <option value="all">Mọi kênh</option>
              <option value="online">Online</option>
              <option value="pos">POS</option>
              <option value="transfer">Chuyển khoản</option>
              <option value="atm">ATM</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="txn-filter-flag">
              Trạng thái cờ
            </label>
            <select
              id="txn-filter-flag"
              value={flagFilter}
              onChange={(event) => change(() => setFlagFilter(event.target.value))}
              className="field py-2 text-[11px]"
            >
              <option value="all">Tất cả</option>
              <option value="flagged">Bị gắn cờ</option>
              <option value="clean">Không gắn cờ</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="txn-filter-range">
              Thời gian
            </label>
            <select
              id="txn-filter-range"
              value={range}
              onChange={(event) => change(() => setRange(event.target.value))}
              className="field py-2 text-[11px]"
            >
              <option value="today">Hôm nay</option>
              <option value="7">7 ngày</option>
              <option value="30">30 ngày</option>
              <option value="90">90 ngày</option>
              <option value="all">Toàn bộ</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="txn-filter-sort">
              Sắp xếp
            </label>
            <select
              id="txn-filter-sort"
              value={sort}
              onChange={(event) => change(() => setSort(event.target.value))}
              className="field py-2 text-[11px]"
            >
              <option value="recent">Mới nhất</option>
              <option value="score">Rủi ro cao</option>
              <option value="amount">Giá trị lớn</option>
            </select>
          </div>
        </div>
      </Disclosure>

      <div className="panel overflow-hidden">
        <div className="flex flex-col gap-2.5 border-b border-white/[0.06] px-4 py-3 lg:flex-row lg:items-center lg:gap-3 lg:px-5">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              change(() => setQ(search.trim()));
            }}
            className="relative w-full lg:max-w-[280px]"
          >
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Tìm giao dịch"
              placeholder="Mã giao dịch, khách hàng, merchant…"
              className="field py-2 pl-9 text-[11.5px]"
            />
          </form>
          <Segmented value={band} options={BAND_TABS} onChange={(value) => change(() => setBand(value))} />
          <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
            <button className="btn-ghost btn-sm" onClick={() => setSimulateOpen(true)} disabled={!canEdit}>
              <Sparkles size={13} /> Mô phỏng
            </button>
            <button className="btn-primary btn-sm" onClick={() => setIngestOpen(true)} disabled={!canEdit}>
              <Plus size={13} /> Nhập giao dịch
            </button>
          </div>
        </div>

        {transactions.isError ? (
          <ErrorState message={transactions.error.message} onRetry={() => transactions.refetch()} />
        ) : transactions.isLoading ? (
          <SkeletonRows rows={8} />
        ) : !transactions.data?.items.length ? (
          <EmptyState
            icon={Filter}
            title="Không có giao dịch phù hợp"
            description="Thử nới bộ lọc hoặc mô phỏng thêm giao dịch để xem luồng chấm điểm."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] border-collapse">
              <thead>
                <tr className="bg-white/[0.012]">
                  <th className="th">Thời điểm</th>
                  <th className="th">Khách hàng / Merchant</th>
                  <th className="th">Giá trị</th>
                  <th className="th">Điểm rủi ro</th>
                  <th className="th">Cờ / Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {transactions.data.items.map((txn) => (
                  <tr key={txn.id} className="table-row cursor-pointer" onClick={() => setSelected(txn)}>
                    <td className="td">
                      <div className="flex items-center gap-1.5">
                        <p className="whitespace-nowrap text-[11px] text-slate-200">{formatDateTime(txn.occurred_at)}</p>
                        {txn.is_simulated && (
                          <span className="shrink-0 rounded border border-azure-400/25 bg-azure-500/10 px-1 py-0.5 text-[8.5px] text-azure-400">
                            mô phỏng
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 max-w-[190px] truncate font-mono text-[9.5px] text-slate-500" title={txn.external_id}>
                        {channelLabel(txn.channel)} · {txn.external_id}
                      </p>
                    </td>
                    <td className="td">
                      <p className="max-w-[170px] truncate text-[11.5px] font-medium text-slate-200" title={txn.customer_id}>
                        {txn.customer_name}
                      </p>
                      <p
                        className="mt-0.5 max-w-[210px] truncate text-[9.5px] text-slate-500"
                        title={`${txn.merchant_name} · ${categoryLabel(txn.merchant_category)}`}
                      >
                        {txn.merchant_name} · {categoryLabel(txn.merchant_category)}
                      </p>
                    </td>
                    <td className="td" title={formatVND(txn.amount)}>
                      <p className="whitespace-nowrap font-mono text-[11.5px] text-slate-100">{compactVND(txn.amount)}</p>
                    </td>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <ScoreRing score={txn.risk_score} size={30} stroke={3} />
                        <RiskBadge band={txn.risk_band} />
                      </div>
                    </td>
                    <td className="td">
                      <span
                        className={clsx(
                          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
                          txn.is_flagged
                            ? "border-coral-400/30 bg-coral-500/10 text-coral-400"
                            : "border-mint-400/25 bg-mint-500/10 text-mint-300",
                        )}
                      >
                        {txn.is_flagged ? <ShieldAlert size={10} /> : <CheckCircle2 size={10} />}
                        {txn.is_flagged ? "Gắn cờ" : "Không cờ"}
                      </span>
                      <p className="mt-1">
                        {txn.case ? (
                          <Link
                            to={`/cases/${txn.case.id}`}
                            onClick={(event) => event.stopPropagation()}
                            className="inline-flex items-center gap-1 whitespace-nowrap font-mono text-[10px] text-mint-300 hover:text-mint-200"
                          >
                            {txn.case.code} <ArrowUpRight size={10} />
                          </Link>
                        ) : (
                          <span className="text-[10px] text-slate-600">Chưa có case</span>
                        )}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {transactions.data && (
          <Pagination
            page={transactions.data.page}
            pages={transactions.data.pages}
            total={transactions.data.total}
            pageSize={transactions.data.page_size}
            onPage={setPage}
          />
        )}
      </div>

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? `Giao dịch ${selected.external_id}` : ""}
        description={selected ? `${selected.customer_name} · ${formatDateTime(selected.occurred_at)}` : undefined}
        size="md"
        footer={
          selected?.case ? (
            <Link to={`/cases/${selected.case.id}`} className="btn-primary">
              <ArrowUpRight size={14} /> Mở case {selected.case.code}
            </Link>
          ) : (
            <button className="btn-ghost" onClick={() => setSelected(null)}>
              Đóng
            </button>
          )
        }
      >
        {selected && (
          <div className="space-y-4">
            <div className="flex items-center gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <ScoreRing score={selected.risk_score} size={58} stroke={4} />
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[18px] text-white">{formatVND(selected.amount)}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  {selected.merchant_name} · {categoryLabel(selected.merchant_category)} · {channelLabel(selected.channel)}
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <RiskBadge band={selected.risk_band} />
                  {selected.is_flagged && <span className="chip text-[9px] text-coral-400">Đã gắn cờ</span>}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                ["ML score", selected.ml_score.toFixed(0)],
                ["Rule score", selected.rule_score.toFixed(0)],
                ["Rule khớp", String(selected.rule_hits.length)],
                ["IP / thẻ", `${selected.ip_country} / ${selected.card_country}`],
                ["Thiết bị mới", selected.new_device ? "Có" : "Không"],
                ["Giao dịch 1h", String(selected.velocity_1h)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-white/[0.05] bg-white/[0.015] px-3 py-2">
                  <p className="text-[9px] uppercase tracking-wider text-slate-600">{label}</p>
                  <p className="mt-0.5 font-mono text-[11.5px] text-slate-200">{value}</p>
                </div>
              ))}
            </div>

            <div>
              <p className="eyebrow mb-2">Tín hiệu model</p>
              <div className="space-y-2">
                {selected.contributions.slice(0, 5).map((item) => (
                  <div key={item.label} className="flex items-center gap-3">
                    <span className="w-[150px] shrink-0 truncate text-[10.5px] text-slate-400">{item.label}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.05]">
                      <div
                        className={clsx("h-full rounded-full", item.direction === "up" ? "bg-coral-400/70" : "bg-mint-400/60")}
                        style={{ width: `${Math.min(item.impact * 2.4, 100)}%` }}
                      />
                    </div>
                    <span className="w-[70px] shrink-0 text-right text-[9.5px] text-slate-600">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="eyebrow mb-2">Rule khớp</p>
              <RuleHits hits={selected.rule_hits} />
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={ingestOpen}
        onClose={() => {
          setIngestOpen(false);
          setCreated(null);
        }}
        title={created ? "Kết quả chấm điểm" : "Nhập giao dịch mới"}
        description={
          created
            ? "Giao dịch đã được chấm điểm và lưu. Nếu vượt ngưỡng, case tương ứng đã được tạo."
            : "Dùng để demo luồng ingest → feature → rule + ML → cảnh báo."
        }
        footer={
          created ? (
            <>
              <button
                className="btn-ghost"
                onClick={() => {
                  setCreated(null);
                  setIngestOpen(false);
                }}
              >
                Đóng
              </button>
              {created.case && (
                <Link to={`/cases/${created.case.id}`} className="btn-primary" onClick={() => setIngestOpen(false)}>
                  Mở case {created.case.code}
                </Link>
              )}
            </>
          ) : undefined
        }
      >
        {created ? (
          <div className="space-y-4">
            <div className="flex items-center gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <ScoreRing score={created.risk_score} size={62} stroke={4} />
              <div>
                <p className="font-mono text-[17px] text-white">{formatVND(created.amount)}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  {created.merchant_name} · {categoryLabel(created.merchant_category)}
                </p>
                <div className="mt-2 flex gap-2">
                  <RiskBadge band={created.risk_band} />
                  <span className="chip text-[9px]">
                    ML {created.ml_score.toFixed(0)} · Rule {created.rule_score.toFixed(0)}
                  </span>
                </div>
              </div>
            </div>
            {created.is_flagged ? (
              <div className="flex items-start gap-2.5 rounded-xl border border-coral-400/20 bg-coral-500/[0.06] px-3.5 py-3">
                <ShieldAlert size={14} className="mt-0.5 shrink-0 text-coral-400" />
                <p className="text-[11px] leading-relaxed text-slate-300">
                  Giao dịch vượt ngưỡng cảnh báo.{" "}
                  {created.case ? (
                    <Link to={`/cases/${created.case.id}`} className="font-mono text-mint-300 hover:text-mint-200" onClick={() => setIngestOpen(false)}>
                      Case {created.case.code}
                    </Link>
                  ) : (
                    "Case đang được tạo."
                  )}{" "}
                  đã được đưa vào hàng chờ điều tra.
                </p>
              </div>
            ) : (
              <div className="flex items-center gap-2.5 rounded-xl border border-mint-400/20 bg-mint-500/[0.06] px-3.5 py-3 text-mint-300">
                <CheckCircle2 size={14} />
                <p className="text-[11px]">Không vượt ngưỡng cảnh báo — không tạo case.</p>
              </div>
            )}
            <div>
              <p className="eyebrow mb-2">Rule khớp ({created.rule_hits.length})</p>
              <RuleHits hits={created.rule_hits} />
            </div>
          </div>
        ) : (
          <IngestForm onDone={setCreated} />
        )}
      </Modal>

      <SimulateDialog open={simulateOpen} onClose={() => setSimulateOpen(false)} />
    </div>
  );
}

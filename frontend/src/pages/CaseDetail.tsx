import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  Check,
  CheckCircle2,
  CircleDot,
  Copy,
  CornerUpRight,
  Cpu,
  FileText,
  Gauge,
  History,
  Lock,
  MessageSquare,
  RefreshCw,
  Save,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserPlus,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  categoryLabel,
  channelLabel,
  decisionLabel,
  formatDateTime,
  formatNumber,
  formatVND,
  slaState,
  statusLabel,
  timeAgo,
} from "@/lib/format";
import type { CaseDetail, Note, RuleCondition } from "@/lib/types";
import { DecisionBadge, PriorityBadge, RiskBadge, StatusBadge } from "@/components/Badges";
import { ErrorState, PageHeader } from "@/components/Ui";
import { ScoreRing } from "@/components/ScoreRing";
import { Modal } from "@/components/Modal";
import { DataList, Disclosure, PanelHeader, ShowMore } from "@/components/Patterns";
import { useToast } from "@/lib/toast";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  openrouter: "OpenRouter",
  anthropic: "Anthropic",
  offline: "Template offline",
  "offline-fallback": "Offline fallback",
};

const FIELD_LABELS: Record<string, string> = {
  amount: "Số tiền",
  amount_ratio: "Tỷ lệ chi tiêu",
  velocity_1h: "Giao dịch/1h",
  velocity_24h: "Giao dịch/24h",
  distinct_merchants_24d: "Merchant/24h",
  account_age_days: "Tuổi tài khoản",
  hour: "Giờ",
  is_night: "Ban đêm",
  country_mismatch: "Lệch quốc gia",
  new_device: "Thiết bị mới",
  merchant_category: "Ngành hàng",
  channel: "Kênh",
  card_country: "Quốc gia thẻ",
  ip_country: "Quốc gia IP",
  merchant_country: "Quốc gia merchant",
};

const OP_LABELS: Record<string, string> = {
  ">": ">",
  ">=": "≥",
  "<": "<",
  "<=": "≤",
  "==": "=",
  "!=": "≠",
  in: "thuộc",
  not_in: "không thuộc",
};

/** Số dòng đóng góp model hiển thị trước khi bấm "Xem thêm". */
const CONTRIBUTION_LIMIT = 3;

function conditionText(condition: RuleCondition): string {
  const field = FIELD_LABELS[condition.field] ?? condition.field;
  let value: string;
  if (Array.isArray(condition.value)) {
    value = condition.value.map((item) => categoryLabel(String(item))).join(", ");
  } else if (typeof condition.value === "boolean") {
    value = condition.value ? "Có" : "Không";
  } else if (condition.field === "amount" || condition.field === "amount_ratio") {
    value = condition.field === "amount" ? formatVND(Number(condition.value)) : `${condition.value}×`;
  } else {
    value = String(condition.value);
  }
  return `${field} ${OP_LABELS[condition.op] ?? condition.op} ${value}`;
}

const DECISIONS = [
  {
    value: "confirmed_fraud",
    label: "Xác nhận gian lận",
    description: "Đã xác minh với khách hàng, chuyển hồ sơ tranh chấp.",
    icon: XCircle,
    tone: "coral",
  },
  {
    value: "false_positive",
    label: "Cảnh báo sai",
    description: "Giao dịch hợp lệ, đóng cảnh báo và ghi lý do.",
    icon: CheckCircle2,
    tone: "mint",
  },
  {
    value: "escalated",
    label: "Chuyển cấp",
    description: "Cần nhóm điều tra chuyên sâu hoặc khách chưa phản hồi.",
    icon: CornerUpRight,
    tone: "amber",
  },
];

function EventIcon({ type }: { type: string }) {
  const icons: Record<string, typeof CircleDot> = {
    created: ShieldAlert,
    assigned: UserPlus,
    status: CircleDot,
    decision: ShieldCheck,
    note: MessageSquare,
    explanation: Sparkles,
  };
  const Icon = icons[type] ?? CircleDot;
  return (
    <span className="z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-azure-400/20 bg-white text-slate-500">
      <Icon size={11} />
    </span>
  );
}

export function CaseDetailPage() {
  const { id = "" } = useParams();
  const { user, canEdit } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [decision, setDecision] = useState<string | null>(null);
  const [decisionNote, setDecisionNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [noteBody, setNoteBody] = useState("");
  const [checkedQuestions, setCheckedQuestions] = useState<Set<number>>(new Set());
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const detail = useQuery({
    queryKey: ["case", id],
    queryFn: () => api<CaseDetail>(`/cases/${id}`),
    enabled: Boolean(id),
  });
  const caseData = detail.data;

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["case", id] });
    queryClient.invalidateQueries({ queryKey: ["cases"] });
    queryClient.invalidateQueries({ queryKey: ["case-stats"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["audit"] });
  };

  const assign = useMutation({
    mutationFn: (userId: string) =>
      api<CaseDetail>(`/cases/${id}`, { method: "PATCH", body: JSON.stringify({ assigned_to: userId }) }),
    onSuccess: () => {
      toast.push("Case đã được giao và ghi nhận trong audit trail.", "success", "Đã phân công");
      invalidate();
    },
    onError: (error) => toast.push(error.message, "error", "Không thể phân công"),
  });

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      api<CaseDetail>(`/cases/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
    onSuccess: (data) => {
      toast.push(`Trạng thái mới: ${statusLabel(data.status)}.`, "success", "Đã cập nhật");
      invalidate();
    },
    onError: (error) => toast.push(error.message, "error", "Không thể đổi trạng thái"),
  });

  const explain = useMutation({
    mutationFn: () => api(`/cases/${id}/explain?force=${caseData?.latest_explanation ? "true" : "false"}`, { method: "POST" }),
    onSuccess: () => {
      toast.push("Bản giải thích đã được tạo và lưu vào case.", "success", "AI explanation");
      invalidate();
    },
    onError: (error) => toast.push(error.message, "error", "Không tạo được giải thích"),
  });

  const addNote = useMutation({
    mutationFn: (payload: { body: string; kind: string }) =>
      api<Note>(`/cases/${id}/notes`, { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: () => {
      toast.push("Ghi chú đã được thêm vào case.", "success", "Đã lưu");
      setNoteBody("");
      invalidate();
    },
    onError: (error) => toast.push(error.message, "error", "Không thêm được ghi chú"),
  });

  const submitDecision = useMutation({
    mutationFn: () =>
      api<CaseDetail>(`/cases/${id}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          note: decisionNote.trim(),
          confirm: confirmed,
          close_case: true,
        }),
      }),
    onSuccess: () => {
      toast.push("Kết luận đã được lưu cùng audit trail. Hành động này không thể ghi đè.", "success", "Đã ghi nhận kết luận");
      setDecisionOpen(false);
      invalidate();
    },
    onError: (error) => toast.push(error.message, "error", "Không ghi được kết luận"),
  });

  const timeline = useMemo(() => {
    if (!caseData) return [];
    const events = caseData.events.map((event) => ({
      id: event.id,
      kind: "event" as const,
      type: event.type,
      title: event.actor?.full_name ?? "Hệ thống",
      message: event.message,
      at: event.created_at,
    }));
    const notes = caseData.notes.map((note) => ({
      id: note.id,
      kind: "note" as const,
      type: "note",
      title: note.author?.full_name ?? "Hệ thống",
      message: note.body,
      at: note.created_at,
    }));
    return [...events, ...notes].sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
  }, [caseData]);

  if (detail.isError) {
    return (
      <div className="panel mt-8">
        <ErrorState message={detail.error.message} onRetry={() => detail.refetch()} />
      </div>
    );
  }

  if (!caseData) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-8 w-64" />
        <div className="grid gap-4 xl:grid-cols-12">
          <div className="panel h-[420px] xl:col-span-7" />
          <div className="panel h-[420px] xl:col-span-5" />
        </div>
      </div>
    );
  }

  const txn = caseData.transaction;
  const sla = slaState(caseData.sla_due_at, caseData.status);
  const explanation = caseData.latest_explanation;
  const aiDraftSaved = caseData.notes.some((note) => note.kind === "ai_draft");
  const canDecide = canEdit && !caseData.decision && caseData.status !== "resolved";
  const isResolved = Boolean(caseData.decision) || caseData.status === "resolved";

  const contextFlags = [
    { label: "Ban đêm", active: txn.is_night, tone: "amber" },
    { label: "Thiết bị mới", active: txn.new_device, tone: "amber" },
    { label: "Lệch quốc gia", active: txn.country_mismatch, tone: "coral" },
    { label: "Tần suất cao", active: txn.velocity_1h >= 3, tone: "coral" },
  ];

  const transactionItems: { label: string; value: string; emphasis?: boolean }[] = [
    { label: "Khách hàng", value: txn.customer_name },
    { label: "Mã khách hàng", value: txn.customer_id },
    { label: "Merchant", value: txn.merchant_name },
    { label: "Ngành hàng", value: categoryLabel(txn.merchant_category) },
    { label: "Kênh", value: channelLabel(txn.channel) },
    { label: "Thời điểm", value: formatDateTime(txn.occurred_at) },
    { label: "Quốc gia thẻ", value: txn.card_country },
    { label: "Quốc gia IP", value: txn.ip_country },
    { label: "Thiết bị", value: txn.device_id },
    { label: "Tuổi tài khoản", value: `${formatNumber(txn.account_age_days)} ngày` },
    { label: "Giao dịch 1 giờ", value: `${txn.velocity_1h}` },
    { label: "Giao dịch 24 giờ", value: `${txn.velocity_24h}` },
  ];

  const visibleContributions = expanded ? txn.contributions : txn.contributions.slice(0, CONTRIBUTION_LIMIT);
  const hiddenContributions = Math.max(txn.contributions.length - CONTRIBUTION_LIMIT, 0);

  return (
    <div className="animate-fade-in">
      <Link to="/queue" className="mb-3 inline-flex items-center gap-1.5 text-[11px] text-slate-500 transition hover:text-mint-300">
        <ArrowLeft size={13} /> Quay lại hàng chờ
      </Link>

      <PageHeader
        eyebrow={`${caseData.code} · ${timeAgo(caseData.created_at)}`}
        title={`${formatVND(txn.amount)} tại ${txn.merchant_name}`}
        subtitle={`${txn.customer_name} · ${channelLabel(txn.channel)} · ${formatDateTime(txn.occurred_at)}`}
        actions={
          <>
            <RiskBadge band={txn.risk_band} />
            <StatusBadge status={caseData.status} />
            <PriorityBadge priority={caseData.priority} />
            {canEdit && !caseData.assignee && (
              <button className="btn-ghost btn-sm" onClick={() => assign.mutate(user?.id ?? "")} disabled={assign.isPending}>
                <UserPlus size={13} /> Nhận xử lý
              </button>
            )}
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-white/70 bg-white/45 px-4 py-3">
        <ScoreRing score={caseData.risk_score} size={46} stroke={3.5} />
        <div className="min-w-[190px] flex-1">
          <p className="text-[11px] leading-relaxed text-slate-400">
            Điểm rủi ro tổng hợp <span className="font-mono text-white">{caseData.risk_score.toFixed(0)}</span>/100 ·{" "}
            ML <span className="font-mono text-slate-300">{txn.ml_score.toFixed(0)}</span> · Rule{" "}
            <span className="font-mono text-slate-300">{txn.rule_score.toFixed(0)}</span> · {txn.rule_hits.length} rule khớp
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-slate-600">
            <span className={clsx(sla.tone === "bad" ? "text-coral-400" : sla.tone === "warn" ? "text-amber-400" : "text-slate-500")}>
              {sla.label}
            </span>
            <span className="h-2.5 w-px bg-[#04384d]/15" />
            <span>Tạo lúc {formatDateTime(caseData.created_at)}</span>
            <span className="hidden h-2.5 w-px bg-[#04384d]/15 sm:block" />
            <span className="font-mono">{txn.external_id}</span>
          </div>
        </div>
        {canEdit && !isResolved && (
          <div className="flex w-full items-center gap-2 sm:w-auto">
            <select
              value={caseData.status}
              onChange={(event) => updateStatus.mutate(event.target.value)}
              className="field w-auto flex-1 py-2 text-[11px] sm:flex-none"
              aria-label="Trạng thái case"
              disabled={updateStatus.isPending}
            >
              <option value="open">Mới</option>
              <option value="in_review">Đang xử lý</option>
              <option value="awaiting_info">Chờ thông tin</option>
            </select>
            <button
              className="btn-primary btn-sm shrink-0"
              onClick={() => document.getElementById("decision-panel")?.scrollIntoView({ behavior: "smooth", block: "start" })}
            >
              <ShieldCheck size={13} /> Ghi kết luận
            </button>
          </div>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-12 xl:items-start">
        {/* ───────────────────────── cột trái: luồng ra quyết định ───────────────────────── */}
        <div className="min-w-0 space-y-4 xl:col-span-7">
          <section className="panel overflow-hidden">
            <PanelHeader
              title="Vì sao bị gắn cờ"
              subtitle="Điểm ML và rule engine độc lập, kết hợp thành điểm rủi ro cuối"
              icon={Gauge}
              badge={`${txn.rule_hits.length} rule khớp`}
            />
            <div className="px-4 pb-4 pt-3">
              <div className="space-y-3">
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-[10.5px]">
                    <span className="flex items-center gap-1.5 text-slate-400"><Cpu size={11} /> ML score</span>
                    <span className="font-mono text-slate-300">{txn.ml_score.toFixed(0)}/100</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#04384d]/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-azure-500/80 to-mint-400" style={{ width: `${txn.ml_score}%` }} />
                  </div>
                </div>
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-[10.5px]">
                    <span className="flex items-center gap-1.5 text-slate-400"><ShieldAlert size={11} /> Rule score</span>
                    <span className="font-mono text-slate-300">{txn.rule_score.toFixed(0)}/100</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#04384d]/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-amber-500/80 to-coral-400" style={{ width: `${txn.rule_score}%` }} />
                  </div>
                </div>
              </div>

              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="eyebrow">Tín hiệu model đóng góp</p>
                  <span className="text-[9.5px] text-slate-500">{txn.contributions.length} tín hiệu</span>
                </div>
                {txn.contributions.length === 0 ? (
                  <p className="text-[11px] text-slate-500">Model không trả về tín hiệu đóng góp nào cho giao dịch này.</p>
                ) : (
                  <div className="space-y-2.5">
                    {visibleContributions.map((item) => (
                      <div key={item.label}>
                        <div className="mb-1 flex items-center justify-between gap-3 text-[10.5px]">
                          <span className="truncate text-slate-400">{item.label}</span>
                          <span className="flex shrink-0 items-center gap-2">
                            <span className="font-mono text-[10px] text-slate-600">{item.value}</span>
                            <span className={clsx("font-mono text-[10px]", item.direction === "up" ? "text-coral-400" : "text-mint-300")}>
                              {item.impact.toFixed(1)}%
                            </span>
                          </span>
                        </div>
                        <div className="h-1 overflow-hidden rounded-full bg-[#04384d]/10">
                          <div
                            className={clsx("h-full rounded-full", item.direction === "up" ? "bg-coral-400/70" : "bg-mint-400/60")}
                            style={{ width: `${Math.min(item.impact * 2.4, 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {hiddenContributions > 0 && (
                  <div className="mt-2.5">
                    <ShowMore
                      expanded={expanded}
                      onClick={() => setExpanded((value) => !value)}
                      rest={hiddenContributions}
                    />
                  </div>
                )}
                <p className="mt-2.5 text-[9.5px] leading-relaxed text-slate-500">
                  Mức đóng góp là ước lượng theo độ quan trọng toàn cục của model và độ lệch so với baseline, không phải kết luận nhân quả.
                  {txn.rule_hits.length > 0 && ` Chi tiết ${txn.rule_hits.length} rule khớp nằm ở mục “Rule đã khớp”.`}
                </p>
              </div>
            </div>
          </section>

          <Disclosure
            title="AI giải thích cảnh báo"
            subtitle="Tóm tắt, so sánh hành vi và câu hỏi xác minh"
            icon={Bot}
            defaultOpen
            actions={
              canEdit ? (
                <button
                  className="btn-ghost btn-sm px-2"
                  onClick={() => explain.mutate()}
                  disabled={explain.isPending}
                  title={explanation ? "Tạo lại bản giải thích" : "Tạo bản giải thích"}
                  aria-label={explanation ? "Tạo lại bản giải thích" : "Tạo bản giải thích"}
                >
                  <RefreshCw size={12} className={explain.isPending ? "animate-spin" : ""} />
                </button>
              ) : undefined
            }
            bodyClassName="px-4 pb-4 pt-3"
          >
            {!explanation ? (
              <div className="px-1 py-7 text-center">
                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-white/70 bg-white/60 text-slate-500">
                  <Sparkles size={17} />
                </div>
                <p className="text-[12px] font-medium text-slate-200">Chưa có bản giải thích</p>
                <p className="mx-auto mt-1 max-w-[300px] text-[10.5px] leading-relaxed text-slate-500">
                  AI sẽ tóm tắt các tín hiệu, so sánh với hành vi 30 ngày và soạn câu hỏi xác minh cho analyst.
                </p>
                {canEdit && (
                  <button className="btn-primary btn-sm mt-4" onClick={() => explain.mutate()} disabled={explain.isPending}>
                    <Sparkles size={13} /> {explain.isPending ? "Đang tạo…" : "Tạo giải thích"}
                  </button>
                )}
              </div>
            ) : (
              <div>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="chip border-mint-400/20 bg-mint-500/[0.07] text-[9px] text-mint-300">
                    <span className="h-1 w-1 rounded-full bg-mint-400" />
                    Bản nháp AI
                  </span>
                  <span className="chip text-[9px]">
                    {PROVIDER_LABELS[explanation.provider] ?? explanation.provider}{" "}
                    · {explanation.latency_ms < 1 ? "<1ms" : `${explanation.latency_ms}ms`}
                  </span>
                  <span className="ml-auto text-[9px] text-slate-600">{timeAgo(explanation.created_at)}</span>
                </div>

                <p className="text-[12px] leading-relaxed text-slate-200">{explanation.content.summary}</p>

                <div className="mt-4 space-y-4">
                  <div>
                    <p className="eyebrow mb-2">Tín hiệu chính</p>
                    <ul className="space-y-1.5">
                      {explanation.content.why_flagged.map((reason, index) => (
                        <li key={index} className="flex items-start gap-2 text-[10.5px] leading-relaxed text-slate-400">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-coral-400/80" />
                          {reason}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="rounded-xl border border-white/70 bg-ink-950/70 px-3 py-2.5">
                    <p className="eyebrow mb-1.5">So với hành vi thông thường</p>
                    <p className="text-[10.5px] leading-relaxed text-slate-400">{explanation.content.normal_comparison}</p>
                  </div>

                  <div>
                    <p className="eyebrow mb-2">Câu hỏi xác minh</p>
                    <div className="space-y-1.5">
                      {explanation.content.verification_questions.map((question, index) => {
                        const checked = checkedQuestions.has(index);
                        return (
                          <button
                            key={index}
                            type="button"
                            aria-pressed={checked}
                            className="flex w-full items-start gap-2.5 rounded-lg px-1.5 py-1 text-left transition hover:bg-white/50"
                            onClick={() =>
                              setCheckedQuestions((prev) => {
                                const next = new Set(prev);
                                if (next.has(index)) next.delete(index);
                                else next.add(index);
                                return next;
                              })
                            }
                          >
                            <span
                              className={clsx(
                                "mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition",
                                checked ? "border-mint-400 bg-mint-400 text-ink-950" : "border-[#04384d]/25 bg-white/60",
                              )}
                            >
                              {checked && <Check size={9} strokeWidth={3} />}
                            </span>
                            <span className={clsx("text-[10.5px] leading-relaxed", checked ? "text-slate-500 line-through" : "text-slate-400")}>
                              {question}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <p className="eyebrow">Ghi chú nháp</p>
                      <div className="flex items-center gap-1">
                        <button
                          className="icon-btn h-6 w-6"
                          title="Sao chép"
                          aria-label="Sao chép ghi chú nháp"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(explanation.content.draft_note);
                              setCopied(true);
                              window.setTimeout(() => setCopied(false), 1800);
                            } catch {
                              toast.push("Trình duyệt chặn clipboard.", "error");
                            }
                          }}
                        >
                          {copied ? <Check size={12} className="text-mint-400" /> : <Copy size={12} />}
                        </button>
                        {canEdit && !aiDraftSaved && (
                          <button
                            className="icon-btn h-6 w-6"
                            title="Lưu vào case dưới dạng ghi chú"
                            aria-label="Lưu ghi chú nháp vào case"
                            onClick={() => addNote.mutate({ body: explanation.content.draft_note, kind: "ai_draft" })}
                            disabled={addNote.isPending}
                          >
                            <Save size={12} />
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="rounded-xl border border-dashed border-white/70 bg-ink-950/60 px-3 py-2.5 text-[10.5px] leading-relaxed text-slate-400">
                      {explanation.content.draft_note}
                    </p>
                    {aiDraftSaved && <p className="mt-1.5 text-[9px] text-mint-300/70">Đã lưu vào case dưới dạng ghi chú AI.</p>}
                  </div>
                </div>

                <p className="mt-4 border-t border-white/70 pt-3 text-[9px] leading-relaxed text-slate-600">
                  {explanation.content.disclaimer}
                </p>
              </div>
            )}
          </Disclosure>

          <div
            className={clsx(
              "flex items-start gap-2.5 rounded-xl border px-4 py-3",
              isResolved ? "border-mint-400/20 bg-mint-500/[0.055]" : "border-amber-400/20 bg-amber-500/[0.055]",
            )}
          >
            {isResolved ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-mint-400" /> : <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-400" />}
            <div className="min-w-0">
              <p className={clsx("text-[11.5px] font-medium", isResolved ? "text-mint-200" : "text-amber-200")}>
                {isResolved ? "Case đã có kết luận của con người" : "Hệ thống chưa kết luận gian lận"}
              </p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-slate-500">
                {isResolved
                  ? `${decisionLabel(caseData.decision)} · ${formatDateTime(caseData.resolved_at)}. Kết luận được lưu vĩnh viễn trong audit trail.`
                  : "Điểm rủi ro chỉ là tín hiệu. Cần analyst xác minh với khách hàng trước khi ghi nhận kết luận."}
              </p>
            </div>
          </div>

          <section id="decision-panel" className="panel scroll-mt-24 overflow-hidden">
            {canDecide ? (
              <>
                <PanelHeader
                  title="Kết luận của analyst"
                  subtitle="Bắt buộc ghi chú, không thể ghi đè sau khi lưu"
                  icon={Lock}
                />
                <div className="px-4 pb-4 pt-3">
                  <div className="grid gap-2">
                    {DECISIONS.map((option) => {
                      const Icon = option.icon;
                      const active = decision === option.value;
                      const tones = {
                        coral: "border-coral-400/40 bg-coral-500/10 text-coral-400",
                        mint: "border-mint-400/40 bg-mint-500/10 text-mint-300",
                        amber: "border-amber-400/40 bg-amber-500/10 text-amber-400",
                      }[option.tone as "coral" | "mint" | "amber"];
                      return (
                        <button
                          key={option.value}
                          type="button"
                          aria-pressed={active}
                          onClick={() => setDecision(option.value)}
                          className={clsx(
                            "flex items-start gap-3 rounded-xl border px-3.5 py-2.5 text-left transition",
                            active ? tones : "border-white/70 bg-white/45 text-slate-400 hover:border-azure-400/40 hover:bg-white/70",
                          )}
                        >
                          <Icon size={15} className="mt-0.5 shrink-0" />
                          <span>
                            <span className="block text-[11.5px] font-medium">{option.label}</span>
                            <span className={clsx("mt-0.5 block text-[9.5px] leading-relaxed", active ? "opacity-80" : "text-slate-600")}>
                              {option.description}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <textarea
                    value={decisionNote}
                    onChange={(event) => setDecisionNote(event.target.value)}
                    className="field mt-3 min-h-[84px] resize-y text-[11px]"
                    aria-label="Ghi chú kết luận"
                    placeholder="Ghi rõ bước xác minh, thông tin khách hàng cung cấp và lý do kết luận (tối thiểu 10 ký tự)…"
                  />
                  <div className="mt-2 flex items-center justify-between text-[9.5px] text-slate-600">
                    <span>{decisionNote.trim().length}/10 ký tự tối thiểu</span>
                  </div>
                  <label className="mt-3 flex cursor-pointer items-start gap-2.5 rounded-lg border border-white/70 bg-ink-950/60 px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      onChange={(event) => setConfirmed(event.target.checked)}
                      className="mt-0.5 h-3.5 w-3.5 accent-mint-400"
                    />
                    <span className="text-[10px] leading-relaxed text-slate-400">
                      Tôi đã xác minh với khách hàng và hiểu kết luận này được lưu vĩnh viễn trong audit trail.
                    </span>
                  </label>
                  <button
                    className="btn-primary mt-3 w-full"
                    disabled={!decision || decisionNote.trim().length < 10 || !confirmed || submitDecision.isPending}
                    onClick={() => setDecisionOpen(true)}
                  >
                    {submitDecision.isPending ? "Đang lưu…" : "Xem lại & ghi kết luận"}
                  </button>
                </div>
              </>
            ) : isResolved ? (
              <>
                <PanelHeader
                  title="Kết luận đã ghi nhận"
                  subtitle="Kết luận được lưu vĩnh viễn trong audit trail"
                  icon={ShieldCheck}
                />
                <div className="space-y-2.5 px-4 pb-4 pt-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10.5px] text-slate-500">Kết luận</span>
                    <DecisionBadge decision={caseData.decision} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[10.5px] text-slate-500">Thời điểm</span>
                    <span className="text-[10.5px] text-slate-300">{formatDateTime(caseData.resolved_at)}</span>
                  </div>
                  <div>
                    <p className="text-[10.5px] text-slate-500">Ghi chú của analyst</p>
                    <p className="mt-1.5 rounded-lg border border-white/70 bg-ink-950/70 px-3 py-2 text-[10.5px] leading-relaxed text-slate-400">
                      {caseData.decision_note ?? "—"}
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <>
                <PanelHeader title="Chế độ chỉ xem" subtitle="Tài khoản của bạn không có quyền ghi kết luận" icon={Lock} />
                <p className="px-4 pb-4 pt-2 text-[10.5px] leading-relaxed text-slate-500">
                  Tài khoản của bạn có thể xem case, tín hiệu và bản giải thích nhưng không thể ghi kết luận hoặc thêm ghi chú.
                </p>
              </>
            )}
          </section>
        </div>

        {/* ───────────────────── cột phải: bằng chứng & chi tiết (mặc định đóng) ───────────────────── */}
        <div className="min-w-0 space-y-3 xl:col-span-5 xl:sticky xl:top-[74px] xl:max-h-[calc(100vh_-_5.625rem)] xl:overflow-y-auto xl:pr-1">
          <Disclosure
            title="Thông tin giao dịch"
            subtitle={`${transactionItems.length} trường · ${txn.merchant_name} · ${formatVND(txn.amount)}`}
            icon={FileText}
            bodyClassName="px-4 pb-4 pt-4"
          >
            <DataList columns={2} items={transactionItems} />
            <div className="mt-4 border-t border-white/70 pt-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="eyebrow mr-1">Tín hiệu ngữ cảnh</span>
                {contextFlags.map((flag) => (
                  <span
                    key={flag.label}
                    className={clsx(
                      "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[9.5px]",
                      flag.active
                        ? flag.tone === "coral"
                          ? "border-coral-400/25 bg-coral-500/10 text-coral-400"
                          : "border-amber-400/25 bg-amber-500/10 text-amber-400"
                        : "border-white/70 bg-white/45 text-slate-600",
                    )}
                  >
                    <span className={clsx("h-1 w-1 rounded-full", flag.active ? "bg-current" : "bg-slate-700")} />
                    {flag.label}
                  </span>
                ))}
              </div>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[9.5px] text-slate-500">
                <span>
                  Chi tiêu gấp <span className="mono font-semibold text-white">{txn.amount_ratio.toFixed(1)}×</span> trung bình 30 ngày
                </span>
                <span className="mono text-slate-600">{txn.model_version}</span>
              </div>
            </div>
          </Disclosure>

          <Disclosure
            title="Rule đã khớp"
            subtitle={`${txn.rule_hits.length} rule`}
            icon={ShieldAlert}
            bodyClassName="px-4 pb-4 pt-4"
          >
            {txn.rule_hits.length === 0 ? (
              <p className="text-[11px] text-slate-500">Không có rule nào khớp — điểm rủi ro đến hoàn toàn từ model ML.</p>
            ) : (
              <div className="space-y-2">
                {txn.rule_hits.map((hit) => (
                  <div key={hit.rule_id} className="rounded-xl border border-white/70 bg-ink-950/70 px-3.5 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2.5">
                        <span
                          className={clsx(
                            "mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full",
                            hit.severity === "high" ? "bg-coral-400" : hit.severity === "medium" ? "bg-amber-400" : "bg-slate-500",
                          )}
                        />
                        <div className="min-w-0">
                          <p className="text-[11.5px] font-medium text-slate-200">{hit.name}</p>
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            {hit.conditions.map((condition, index) => (
                              <span key={index} className="rounded border border-white/70 bg-white/70 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">
                                {conditionText(condition)}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                      <span className="shrink-0 rounded-md border border-amber-400/20 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9.5px] text-amber-400">
                        +{hit.weight}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Disclosure>

          {canEdit && (
            <Disclosure
              title="Ghi chú điều tra"
              subtitle={`${caseData.notes.length} ghi chú`}
              icon={MessageSquare}
              bodyClassName="px-4 pb-4 pt-4"
            >
              <div className="flex gap-2">
                <textarea
                  value={noteBody}
                  onChange={(event) => setNoteBody(event.target.value)}
                  className="field min-h-[70px] flex-1 resize-y text-[11px]"
                  aria-label="Ghi chú điều tra"
                  placeholder="Ghi chú nội bộ, ví dụ: đã gọi khách hàng lúc 14:30…"
                />
                <button
                  className="btn-ghost self-end px-2.5"
                  disabled={noteBody.trim().length < 2 || addNote.isPending}
                  onClick={() => addNote.mutate({ body: noteBody.trim(), kind: "note" })}
                  title="Thêm ghi chú"
                  aria-label="Thêm ghi chú"
                >
                  <Send size={14} />
                </button>
              </div>
            </Disclosure>
          )}

          <Disclosure title="Lịch sử case" subtitle={`${timeline.length} mục`} icon={History} bodyClassName="px-4 py-3">
            <div className="scroll-area max-h-[380px]">
              <div className="relative space-y-4 before:absolute before:bottom-2 before:left-3 before:top-2 before:w-px before:bg-azure-400/20">
                {timeline.map((entry) => (
                  <div key={`${entry.kind}-${entry.id}`} className="relative flex gap-3">
                    <EventIcon type={entry.type} />
                    <div className="min-w-0 flex-1 pb-0.5">
                      <div className="flex items-baseline justify-between gap-2">
                        <p className="truncate text-[10.5px] font-medium text-slate-300">
                          {entry.title}
                          {entry.kind === "note" && <span className="ml-1.5 text-[9px] font-normal text-slate-600">ghi chú</span>}
                        </p>
                        <span className="shrink-0 text-[9px] text-slate-600">{formatDateTime(entry.at)}</span>
                      </div>
                      <p className="mt-0.5 whitespace-pre-line text-[10.5px] leading-relaxed text-slate-500">{entry.message}</p>
                    </div>
                  </div>
                ))}
                {timeline.length === 0 && <p className="text-[11px] text-slate-500">Chưa có hoạt động.</p>}
              </div>
            </div>
          </Disclosure>

          <div className="flex items-center justify-center gap-2 pb-1 text-[9px] text-slate-700">
            <FileText size={10} /> Dữ liệu demo tổng hợp · FraudLens v1.0
          </div>
        </div>
      </div>

      <Modal
        open={decisionOpen}
        onClose={() => setDecisionOpen(false)}
        title="Xác nhận kết luận"
        description="Kết luận sẽ được ghi vào case, thêm ghi chú và audit trail. Không thể ghi đè sau khi lưu."
        size="sm"
        footer={
          <>
            <button className="btn-ghost" onClick={() => setDecisionOpen(false)}>
              Quay lại
            </button>
            <button
              className={clsx("btn", decision === "false_positive" ? "bg-mint-400 text-ink-950 hover:bg-mint-300" : "bg-coral-500 text-white hover:bg-coral-400")}
              disabled={submitDecision.isPending || !confirmed}
              onClick={() => submitDecision.mutate()}
            >
              {submitDecision.isPending ? "Đang lưu…" : "Xác nhận & lưu"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="rounded-xl border border-white/70 bg-ink-950/60 p-3.5">
            <p className="text-[10px] text-slate-500">Case</p>
            <p className="mt-0.5 font-mono text-[12px] text-white">{caseData.code}</p>
            <p className="mt-2 text-[10px] text-slate-500">Kết luận</p>
            <p className="mt-0.5 text-[12px] font-medium text-slate-100">{decisionLabel(decision)}</p>
            <p className="mt-2 text-[10px] text-slate-500">Ghi chú</p>
            <p className="mt-0.5 text-[11px] leading-relaxed text-slate-400">{decisionNote}</p>
          </div>
          <p className="text-[10.5px] leading-relaxed text-slate-500">
            Sau khi lưu, case chuyển sang trạng thái <span className="text-slate-300">Đã đóng</span> và analyst phụ trách được
            ghi nhận. Mọi thay đổi đều có trong Audit trail.
          </p>
        </div>
      </Modal>
    </div>
  );
}

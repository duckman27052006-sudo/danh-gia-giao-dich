import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  Copy,
  Database,
  Gauge,
  KeyRound,
  Lock,
  Save,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatNumber, roleLabel } from "@/lib/format";
import type { ModelInfo, Settings, SystemStatus } from "@/lib/types";
import { ErrorState, PageHeader } from "@/components/Ui";
import { DataList, Disclosure } from "@/components/Patterns";
import { useToast } from "@/lib/toast";

const DEMO_ACCOUNTS = [
  { role: "admin", email: "admin@fraudlens.vn", password: "Admin@12345", name: "Nguyễn Thu Hà" },
  { role: "analyst", email: "analyst@fraudlens.vn", password: "Analyst@123", name: "Trần Minh Anh" },
  { role: "viewer", email: "viewer@fraudlens.vn", password: "Viewer@123", name: "Phạm Ngọc Diệp" },
];

const AI_PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  openrouter: "OpenRouter",
  anthropic: "Anthropic",
};

export function SettingsPage() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();

  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<Settings>("/settings") });
  const model = useQuery({ queryKey: ["model-info"], queryFn: () => api<ModelInfo>("/model/info") });
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => api<SystemStatus>("/system/status") });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string; database: string; model: string; model_auc: number }>("/health"),
  });

  const [form, setForm] = useState<Settings | null>(null);
  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () =>
      api<Settings>("/settings", {
        method: "PATCH",
        body: JSON.stringify({
          review_threshold: form?.review_threshold,
          high_threshold: form?.high_threshold,
          ml_weight: form?.ml_weight,
          rule_weight: form?.rule_weight,
          ai_enabled: form?.ai_enabled,
        }),
      }),
    onSuccess: () => {
      toast.push("Ngưỡng mới áp dụng cho các giao dịch được chấm điểm tiếp theo. Case cũ giữ nguyên.", "success", "Đã lưu cấu hình");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (error) => toast.push(error.message, "error", "Không lưu được cấu hình"),
  });

  const modelInfo = model.data;
  const featureRows = useMemo(() => {
    const grouped = new Map<string, number>();
    for (const item of model.data?.feature_importance ?? []) {
      grouped.set(item.label, (grouped.get(item.label) ?? 0) + item.importance);
    }
    return [...grouped.entries()]
      .map(([label, importance]) => ({ label, importance }))
      .sort((a, b) => b.importance - a.importance)
      .slice(0, 8);
  }, [model.data]);
  const maxImportance = featureRows[0]?.importance ?? 1;

  const weightTotal = form ? Math.round((form.ml_weight + form.rule_weight) * 100) : 100;
  const aiProvider = AI_PROVIDER_LABELS[status.data?.ai.provider ?? ""] ?? "Offline template";
  const aiModel = status.data?.ai.model ?? "template-v1";
  const aiConfigured = Boolean(status.data?.ai.configured);

  const copyDemoAccounts = async () => {
    try {
      await navigator.clipboard.writeText(
        DEMO_ACCOUNTS.map((account) => `${account.role}: ${account.email} / ${account.password}`).join("\n"),
      );
      toast.push("Đã sao chép danh sách tài khoản demo.", "success");
    } catch {
      toast.push("Trình duyệt chặn clipboard.", "error");
    }
  };

  if (settings.isError) {
    return <div className="panel"><ErrorState message={settings.error.message} onRetry={() => settings.refetch()} /></div>;
  }

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Quản trị"
        title="Cấu hình & model"
        subtitle="Điều chỉnh ngưỡng cảnh báo, trọng số ML/rule, bật tắt AI và xem model card đang chạy."
        actions={
          isAdmin && form ? (
            <button type="button" className="btn-primary btn-sm" onClick={() => save.mutate()} disabled={save.isPending}>
              <Save size={13} /> {save.isPending ? "Đang lưu…" : "Lưu cấu hình"}
            </button>
          ) : (
            <span className="chip text-[10px]">
              <Lock size={10} /> Chỉ admin được sửa
            </span>
          )
        }
      />

      <div className="space-y-3">
        <Disclosure
          title="Ngưỡng chấm điểm"
          subtitle="Áp dụng cho giao dịch mới, không hồi tố case đã tạo"
          icon={SlidersHorizontal}
          defaultOpen
          bodyClassName="px-4 pb-4 pt-3"
        >
          {!form ? (
            <div className="space-y-3">
              <div className="skeleton h-10 w-full" />
              <div className="skeleton h-10 w-full" />
            </div>
          ) : (
            <div className="space-y-5">
              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="label mb-0" htmlFor="review-threshold">Ngưỡng cảnh báo (tạo case)</label>
                  <span className="mono text-[12px] text-amber-400">{form.review_threshold.toFixed(0)}</span>
                </div>
                <input
                  id="review-threshold"
                  type="range"
                  min={10}
                  max={95}
                  value={form.review_threshold}
                  disabled={!isAdmin}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    setForm((prev) => prev && { ...prev, review_threshold: value, high_threshold: Math.max(prev.high_threshold, value + 5) });
                  }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-ink-700 accent-mint-400 disabled:opacity-40"
                />
                <p className="mt-1.5 text-[9.5px] text-slate-600">Giao dịch có điểm rủi ro ≥ ngưỡng này sẽ vào hàng chờ.</p>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="label mb-0" htmlFor="high-threshold">Ngưỡng rủi ro rất cao (P1)</label>
                  <span className="mono text-[12px] text-coral-400">{form.high_threshold.toFixed(0)}</span>
                </div>
                <input
                  id="high-threshold"
                  type="range"
                  min={20}
                  max={100}
                  value={form.high_threshold}
                  disabled={!isAdmin}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    setForm((prev) => prev && { ...prev, high_threshold: value, review_threshold: Math.min(prev.review_threshold, value - 5) });
                  }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-ink-700 accent-coral-400 disabled:opacity-40"
                />
                <p className="mt-1.5 text-[9.5px] text-slate-600">Case vượt ngưỡng này có SLA 4 giờ và ưu tiên P1.</p>
              </div>

              <div className="divider" />

              <div className="rounded-xl border border-mint-400/15 bg-mint-500/[0.045] px-3.5 py-3">
                <div className="flex items-center gap-2 text-mint-300">
                  <ShieldCheck size={13} />
                  <p className="text-[10.5px] font-medium">Nguyên tắc human-in-the-loop</p>
                </div>
                <p className="mt-1 text-[9.5px] leading-relaxed text-slate-500">
                  Dù ngưỡng thấp đến đâu, hệ thống không bao giờ tự động kết luận gian lận. Kết luận cuối cùng luôn cần
                  analyst và được lưu trong audit trail.
                </p>
              </div>

              {!isAdmin && (
                <p className="text-[10px] text-slate-500">Bạn đang xem cấu hình ở chế độ chỉ đọc.</p>
              )}
            </div>
          )}
        </Disclosure>

        <Disclosure
          title="Trọng số mô hình & luật"
          subtitle="Tỉ lệ đóng góp của ML và rule engine trong điểm rủi ro"
          icon={Gauge}
          defaultOpen
          bodyClassName="px-4 pb-4 pt-3"
        >
          {!form ? (
            <div className="space-y-3">
              <div className="skeleton h-10 w-full" />
              <div className="skeleton h-4 w-2/3" />
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="label mb-0" htmlFor="ml-weight">Trọng số model ML</label>
                  <span className="mono text-[12px] text-azure-400">{Math.round(form.ml_weight * 100)}%</span>
                </div>
                <input
                  id="ml-weight"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={form.ml_weight}
                  disabled={!isAdmin}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    setForm((prev) => prev && { ...prev, ml_weight: value, rule_weight: Number((1 - value).toFixed(2)) });
                  }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-ink-700 accent-azure-400 disabled:opacity-40"
                />
                <div className="mt-2 flex items-center justify-between text-[9.5px] text-slate-600">
                  <span>ML {Math.round(form.ml_weight * 100)}%</span>
                  <span>Rule {Math.round(form.rule_weight * 100)}%</span>
                </div>
              </div>

              <div className="flex h-2 overflow-hidden rounded-full bg-white/60 ring-1 ring-white/70" aria-hidden="true">
                <div className="h-full bg-azure-400" style={{ width: `${form.ml_weight * 100}%` }} />
                <div className="h-full bg-mint-400" style={{ width: `${form.rule_weight * 100}%` }} />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[10px] text-slate-500">
                  Điểm tổng hợp = ML × trọng số + rule × trọng số. Tổng phải bằng 100%.
                </p>
                <span className={clsx("mono text-[10.5px]", weightTotal === 100 ? "text-mint-300" : "text-amber-400")}>
                  Tổng {weightTotal}%
                </span>
              </div>

              {weightTotal !== 100 && (
                <div role="alert" className="flex items-start gap-2 rounded-xl border border-amber-400/25 bg-amber-500/[0.07] px-3.5 py-3 text-[10.5px] leading-relaxed text-amber-400">
                  <TriangleAlert size={13} className="mt-0.5 shrink-0" />
                  <span>Tổng trọng số đang là {weightTotal}% — cần bằng 100% trước khi lưu.</span>
                </div>
              )}
            </div>
          )}
        </Disclosure>

        <Disclosure
          title="Trí tuệ nhân tạo"
          subtitle="Công tắc giải thích bằng LLM, provider và model đang cấu hình"
          icon={Bot}
          badge={form ? (form.ai_enabled ? "Đang bật" : "Đang tắt") : undefined}
          bodyClassName="px-4 pb-4 pt-3"
        >
          {!form ? (
            <div className="space-y-3">
              <div className="skeleton h-12 w-full" />
              <div className="skeleton h-4 w-2/3" />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3 rounded-xl border border-white/70 bg-white/45 px-3.5 py-3">
                <div className="flex items-center gap-2.5">
                  <Sparkles size={14} className={form.ai_enabled ? "text-mint-400" : "text-slate-600"} />
                  <div>
                    <p className="text-[11px] text-slate-300">Bật AI giải thích</p>
                    <p className="text-[9.5px] text-slate-600">Tắt để tiết kiệm chi phí; hệ thống dùng template offline</p>
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={form.ai_enabled}
                  aria-label="Bật AI giải thích"
                  disabled={!isAdmin}
                  onClick={() => setForm((prev) => prev && { ...prev, ai_enabled: !prev.ai_enabled })}
                  className={clsx(
                    "relative h-5 w-9 shrink-0 rounded-full border transition disabled:opacity-40",
                    form.ai_enabled ? "border-mint-400/40 bg-mint-500/25" : "border-white/10 bg-white/[0.05]",
                  )}
                >
                  <span
                    className={clsx(
                      "absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all",
                      form.ai_enabled ? "left-[18px] bg-mint-400" : "left-0.5 bg-slate-500",
                    )}
                  />
                </button>
              </div>

              <DataList
                columns={3}
                items={[
                  { label: "Provider", value: aiProvider, emphasis: true },
                  { label: "Model", value: <span className="font-mono text-[11px]">{aiModel}</span> },
                  {
                    label: "API key",
                    value: (
                      <span
                        className={clsx(
                          "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[9px]",
                          aiConfigured
                            ? "border-mint-400/25 bg-mint-500/10 text-mint-300"
                            : "border-amber-400/25 bg-amber-500/10 text-amber-400",
                        )}
                      >
                        <KeyRound size={9} />
                        {aiConfigured ? "Đã cấu hình" : "Chưa cấu hình"}
                      </span>
                    ),
                  },
                ]}
              />

              {!aiConfigured && (
                <div className="rounded-lg border border-amber-400/15 bg-amber-500/[0.05] px-3 py-2.5">
                  <p className="text-[9.5px] leading-relaxed text-slate-500">
                    Đặt <span className="font-mono text-slate-300">OPENROUTER_API_KEY</span>,{" "}
                    <span className="font-mono text-slate-300">OPENAI_API_KEY</span> hoặc{" "}
                    <span className="font-mono text-slate-300">ANTHROPIC_API_KEY</span> trong biến môi trường để bật giải
                    thích bằng LLM. Khi chưa có key, hệ thống dùng template offline dựa trên tín hiệu thật.
                  </p>
                </div>
              )}
            </div>
          )}
        </Disclosure>

        <Disclosure
          title="Hệ thống & thẻ mô hình"
          subtitle="Runtime, cơ sở dữ liệu, phiên bản và chỉ số model card"
          icon={Server}
          badge={modelInfo?.version}
          bodyClassName="px-4 pb-4 pt-3"
        >
          <div className="space-y-4">
            <DataList
              columns={3}
              items={[
                { label: "Environment", value: status.data?.environment ?? "—" },
                { label: "Database", value: health.data?.database ?? "—" },
                { label: "Model runtime", value: health.data?.model ?? "—" },
                { label: "Trạng thái", value: health.data?.status === "ok" ? "Hoạt động" : "—", emphasis: true },
                { label: "Demo mode", value: status.data?.demo_mode ? "Bật" : "Tắt" },
              ]}
            />

            <div className="divider" />

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-[11.5px] font-medium text-white">Model card</p>
                <p className="text-[9.5px] text-slate-500">Huấn luyện trên dữ liệu giao dịch tổng hợp</p>
              </div>
              <span className="chip font-mono text-[9px]">{modelInfo?.version ?? "—"}</span>
            </div>

            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {[
                ["ROC-AUC", modelInfo ? modelInfo.auc.toFixed(4) : "—", "text-mint-300"],
                ["Precision", modelInfo ? `${(modelInfo.precision * 100).toFixed(1)}%` : "—", "text-slate-200"],
                ["Recall", modelInfo ? `${(modelInfo.recall * 100).toFixed(1)}%` : "—", "text-slate-200"],
                ["Mẫu huấn luyện", modelInfo ? formatNumber(modelInfo.samples) : "—", "text-slate-200"],
              ].map(([label, value, tone]) => (
                <div key={label} className="rounded-lg border border-white/[0.05] bg-white/[0.015] px-3 py-2.5">
                  <p className="text-[9px] uppercase tracking-wider text-slate-600">{label}</p>
                  <p className={clsx("mt-1 font-mono text-[13px]", tone)}>{value}</p>
                </div>
              ))}
            </div>

            <div>
              <p className="eyebrow mb-2.5">Feature importance (permutation)</p>
              <div className="space-y-2">
                {featureRows.map((item) => (
                  <div key={item.label} className="flex items-center gap-3">
                    <span className="w-[110px] shrink-0 truncate text-[10.5px] text-slate-400 sm:w-[170px]">{item.label}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.05]">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-mint-500/80 to-azure-400/70"
                        style={{ width: `${Math.max((item.importance / maxImportance) * 100, 2)}%` }}
                      />
                    </div>
                    <span className="w-[46px] shrink-0 text-right font-mono text-[9.5px] text-slate-500">
                      {(item.importance * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[9px] leading-relaxed text-slate-600">
                {modelInfo ? `${modelInfo.algorithm} · huấn luyện ${formatDateTime(modelInfo.trained_at)}.` : ""} Chỉ số được
                đo trên tập test tổng hợp, không đại diện cho hiệu năng trên dữ liệu ngân hàng thật.
              </p>
            </div>
          </div>
        </Disclosure>

        <Disclosure
          title="Tài khoản demo"
          subtitle="Chỉ hiển thị khi DEMO_MODE bật"
          icon={Database}
          bodyClassName="px-4 pb-4 pt-3"
          actions={
            <button
              type="button"
              className="icon-btn"
              title="Sao chép thông tin"
              aria-label="Sao chép thông tin tài khoản demo"
              onClick={copyDemoAccounts}
            >
              <Copy size={13} />
            </button>
          }
        >
          {status.data?.demo_mode ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] border-collapse">
                <caption className="sr-only">Tài khoản demo và mật khẩu</caption>
                <thead>
                  <tr>
                    <th className="th pl-0" scope="col">Vai trò</th>
                    <th className="th" scope="col">Họ tên</th>
                    <th className="th" scope="col">Email</th>
                    <th className="th pr-0" scope="col">Mật khẩu</th>
                  </tr>
                </thead>
                <tbody>
                  {DEMO_ACCOUNTS.map((account) => (
                    <tr key={account.email} className="table-row">
                      <td className="td pl-0">
                        <span className="chip text-[8.5px]">{roleLabel(account.role as "admin" | "analyst" | "viewer")}</span>
                      </td>
                      <td className="td text-[11px] text-slate-300">{account.name}</td>
                      <td className="td font-mono text-[10px] text-slate-500">{account.email}</td>
                      <td className="td pr-0 font-mono text-[10px] text-slate-500">{account.password}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="rounded-lg border border-white/70 bg-white/45 px-3 py-3 text-[10px] leading-relaxed text-slate-500">
              <CheckCircle2 size={11} className="mr-1 inline text-mint-400" /> DEMO_MODE đang tắt — không hiển thị thông tin
              đăng nhập mẫu. Đây là cấu hình nên dùng khi deploy thật.
            </p>
          )}
        </Disclosure>
      </div>
    </div>
  );
}

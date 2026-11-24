import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUp, Plus, Search, Trash2, X } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { categoryLabel, formatDateTime, formatNumber } from "@/lib/format";
import type { Rule, RuleCondition, RuleField } from "@/lib/types";
import { ErrorState, PageHeader, SkeletonRows } from "@/components/Ui";
import { Disclosure, Segmented, StatStrip } from "@/components/Patterns";
import { Modal } from "@/components/Modal";
import { useToast } from "@/lib/toast";

const SEVERITY_STYLE = {
  high: { label: "Nghiêm trọng", text: "text-coral-400" },
  medium: { label: "Trung bình", text: "text-amber-400" },
  low: { label: "Thấp", text: "text-slate-500" },
} as const;

const FILTER_OPTIONS: { value: "all" | "on" | "off"; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "on", label: "Đang bật" },
  { value: "off", label: "Đã tắt" },
];

const OP_LABELS: Record<string, string> = {
  ">": "lớn hơn",
  ">=": "lớn hơn hoặc bằng",
  "<": "nhỏ hơn",
  "<=": "nhỏ hơn hoặc bằng",
  "==": "bằng",
  "!=": "khác",
  in: "thuộc danh sách",
  not_in: "không thuộc",
};

function defaultCondition(field: RuleField): RuleCondition {
  const op = field.ops[0];
  if (field.type === "number") return { field: field.key, op, value: 0 };
  if (field.type === "bool") return { field: field.key, op: "==", value: true };
  if (field.type === "enum") return { field: field.key, op: "in", value: [] };
  return { field: field.key, op: "==", value: "" };
}

function conditionSummary(condition: RuleCondition): string {
  const label = condition.field;
  const value = Array.isArray(condition.value)
    ? condition.value.map((item) => categoryLabel(String(item))).join(", ")
    : typeof condition.value === "boolean"
      ? condition.value
        ? "Có"
        : "Không"
      : String(condition.value);
  return `${label} ${OP_LABELS[condition.op] ?? condition.op} ${value || "…"}`;
}

export function RulesPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<"all" | "on" | "off">("all");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Rule | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const rules = useQuery({ queryKey: ["rules"], queryFn: () => api<Rule[]>("/rules") });
  const fields = useQuery({
    queryKey: ["rule-fields"],
    queryFn: () => api<{ fields: RuleField[] }>("/rules/fields"),
  });

  const [draft, setDraft] = useState<{
    name: string;
    description: string;
    weight: number;
    severity: "low" | "medium" | "high";
    category: string;
    enabled: boolean;
    conditions: RuleCondition[];
  }>({ name: "", description: "", weight: 15, severity: "medium", category: "general", enabled: true, conditions: [] });

  const openCreate = () => {
    setDraft({
      name: "",
      description: "",
      weight: 15,
      severity: "medium",
      category: "behavior",
      enabled: true,
      conditions: fields.data?.fields[0] ? [defaultCondition(fields.data.fields[0])] : [],
    });
    setConfirmDelete(false);
    setCreating(true);
  };

  const openEdit = (rule: Rule) => {
    setDraft({
      name: rule.name,
      description: rule.description,
      weight: rule.weight,
      severity: rule.severity,
      category: rule.category,
      enabled: rule.enabled,
      conditions: rule.conditions.map((condition) => ({ ...condition })),
    });
    setEditing(rule);
    setConfirmDelete(false);
  };

  const close = () => {
    setEditing(null);
    setCreating(false);
    setConfirmDelete(false);
  };

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["rules"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["audit"] });
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = { ...draft };
      if (editing) return api(`/rules/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      return api("/rules", { method: "POST", body: JSON.stringify(payload) });
    },
    onSuccess: () => {
      toast.push("Rule đã được lưu và áp dụng cho giao dịch tiếp theo.", "success", editing ? "Đã cập nhật" : "Đã tạo rule");
      invalidate();
      close();
    },
    onError: (error) => toast.push(error.message, "error", "Không lưu được rule"),
  });

  const toggle = useMutation({
    mutationFn: (rule: Rule) =>
      api(`/rules/${rule.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !rule.enabled }) }),
    onSuccess: (_, rule) => {
      toast.push(`Rule “${rule.name}” đã được ${rule.enabled ? "tắt" : "bật"}.`, "success");
      invalidate();
    },
    onError: (error) => toast.push(error.message, "error", "Không đổi được trạng thái"),
  });

  const remove = useMutation({
    mutationFn: () => api(`/rules/${editing?.id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.push("Rule đã bị xoá vĩnh viễn.", "success", "Đã xoá");
      invalidate();
      close();
    },
    onError: (error) => toast.push(error.message, "error", "Không xoá được rule"),
  });

  const visible = useMemo(() => {
    const list = rules.data ?? [];
    return list.filter((rule) => {
      if (filter === "on" && !rule.enabled) return false;
      if (filter === "off" && rule.enabled) return false;
      if (search && !`${rule.name} ${rule.description} ${rule.category}`.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [rules.data, filter, search]);

  const totalHits = rules.data?.reduce((sum, rule) => sum + rule.hit_count, 0) ?? 0;
  const totalWeight = rules.data?.filter((rule) => rule.enabled).reduce((sum, rule) => sum + rule.weight, 0) ?? 0;
  const modalOpen = creating || Boolean(editing);
  const conditionFields = fields.data?.fields ?? [];

  const updateCondition = (index: number, next: RuleCondition) => {
    setDraft((prev) => ({
      ...prev,
      conditions: prev.conditions.map((condition, position) => (position === index ? next : condition)),
    }));
  };

  const changeField = (index: number, key: string) => {
    const field = conditionFields.find((item) => item.key === key);
    if (field) updateCondition(index, defaultCondition(field));
  };

  const canSave =
    draft.name.trim().length >= 3 &&
    draft.conditions.length > 0 &&
    draft.conditions.every((condition) => {
      if (Array.isArray(condition.value)) return condition.value.length > 0;
      return condition.value !== "" && condition.value !== null;
    });

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Quản trị"
        title="Rule engine"
        subtitle="Các luật quyết định được cộng điểm độc lập với model ML. Tổng điểm rule giới hạn ở 100; vượt ngưỡng rule trong Cài đặt thì tự gắn cờ, ngược lại blend theo trọng số."
        actions={
          <button className="btn-primary btn-sm" onClick={openCreate} disabled={!fields.data}>
            <Plus size={13} /> Tạo rule
          </button>
        }
      />

      <StatStrip
        className="mb-3"
        items={[
          {
            label: "Rule đang bật",
            value: (
              <>
                {rules.data?.filter((rule) => rule.enabled).length ?? "—"}
                <span className="ml-1 text-[11px] font-normal text-slate-500">/ {rules.data?.length ?? "—"}</span>
              </>
            ),
            tone: "good",
          },
          {
            label: "Tổng trọng số rule",
            value: (
              <>
                {totalWeight}
                <span className="ml-1 text-[11px] font-normal text-slate-500">điểm</span>
              </>
            ),
            tone: "warn",
          },
          { label: "Tổng lượt khớp", value: formatNumber(totalHits), tone: "neutral" },
        ]}
      />

      <div className="panel-flat mb-3 flex flex-col gap-2.5 px-4 py-3 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-center gap-2 text-slate-500">
          <Search size={14} className="shrink-0" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tìm rule…"
            aria-label="Tìm rule"
            className="w-full bg-transparent text-[11.5px] text-slate-200 outline-none placeholder:text-slate-600 sm:w-52"
          />
        </div>
        <Segmented className="sm:ml-auto" value={filter} options={FILTER_OPTIONS} onChange={setFilter} />
      </div>

      {rules.isError ? (
        <div className="panel"><ErrorState message={rules.error.message} onRetry={() => rules.refetch()} /></div>
      ) : rules.isLoading ? (
        <div className="panel"><SkeletonRows rows={6} /></div>
      ) : (
        <div className="space-y-2">
          {visible.map((rule) => {
            const severity = SEVERITY_STYLE[rule.severity];
            return (
              <Disclosure
                key={rule.id}
                title={rule.name}
                subtitle={`Nhóm: ${rule.category}`}
                badge={<span className={clsx("whitespace-nowrap", severity.text)}>{severity.label}</span>}
                actions={
                  <div className="flex flex-col items-end gap-1 sm:flex-row sm:items-center sm:gap-1.5">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="mono inline-flex items-center gap-0.5 text-[11px] font-semibold text-amber-400"
                        title="Điểm cộng khi rule khớp"
                      >
                        <ArrowUp size={10} />+{rule.weight}
                      </span>
                      <button
                        type="button"
                        onClick={() => toggle.mutate(rule)}
                        className={clsx(
                          "relative h-5 w-9 shrink-0 rounded-full border transition",
                          rule.enabled ? "border-mint-400/40 bg-mint-500/25" : "border-white/10 bg-white/[0.05]",
                        )}
                        aria-label={rule.enabled ? "Tắt rule" : "Bật rule"}
                      >
                        <span
                          className={clsx(
                            "absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all",
                            rule.enabled ? "left-[18px] bg-mint-400" : "left-0.5 bg-slate-500",
                          )}
                        />
                      </button>
                    </div>
                    <button type="button" className="btn-ghost btn-sm" onClick={() => openEdit(rule)}>
                      Sửa
                    </button>
                  </div>
                }
                bodyClassName="px-4 py-3"
              >
                <div className="space-y-3">
                  {rule.description && (
                    <p className="text-[11.5px] leading-relaxed text-slate-500">{rule.description}</p>
                  )}

                  {rule.conditions.length > 0 && (
                    <div>
                      <p className="eyebrow mb-1.5">Điều kiện (AND)</p>
                      <div className="flex flex-wrap gap-1.5">
                        {rule.conditions.map((condition, index) => (
                          <span
                            key={index}
                            className="rounded-md border border-white/[0.07] bg-ink-950/40 px-2 py-1 font-mono text-[9.5px] text-slate-500"
                          >
                            {conditionSummary(condition)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-white/[0.06] pt-2.5 text-[10px] text-slate-600">
                    <span className="font-mono text-amber-400">{formatNumber(rule.hit_count)} lượt khớp</span>
                    {rule.last_hit_at && <span>gần nhất {formatDateTime(rule.last_hit_at)}</span>}
                  </div>
                </div>
              </Disclosure>
            );
          })}

          {visible.length === 0 && (
            <div className="panel py-14 text-center">
              <AlertTriangle size={20} className="mx-auto mb-3 text-slate-600" />
              <p className="text-[12px] text-slate-400">Không có rule phù hợp bộ lọc.</p>
            </div>
          )}
        </div>
      )}

      <p className="mt-4 text-[10px] leading-relaxed text-slate-600">
        Rule được đánh giá độc lập với ML. Tổng trọng số rule được giới hạn ở 100 điểm trước khi blend với model theo
        trọng số cấu hình; nếu tổng này vượt ngưỡng rule trong Cài đặt thì rule tự gắn cờ. Thay đổi rule được lưu trong
        audit trail — không áp dụng hồi tố cho case đã tạo.
      </p>

      <Modal
        open={modalOpen}
        onClose={close}
        title={editing ? "Sửa rule" : "Tạo rule mới"}
        description="Điều kiện được AND với nhau. Rule khớp khi tất cả điều kiện đúng tại thời điểm giao dịch."
        size="lg"
        footer={
          <>
            {editing && (
              <button
                className={clsx("mr-auto", confirmDelete ? "btn-danger" : "btn-ghost")}
                onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
                disabled={remove.isPending}
              >
                <Trash2 size={13} /> {confirmDelete ? "Xác nhận xoá vĩnh viễn" : "Xoá rule"}
              </button>
            )}
            <button className="btn-ghost" onClick={close}>Huỷ</button>
            <button className="btn-primary" onClick={() => save.mutate()} disabled={!canSave || save.isPending}>
              {save.isPending ? "Đang lưu…" : editing ? "Lưu thay đổi" : "Tạo rule"}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label">Tên rule</label>
              <input
                className="field"
                value={draft.name}
                onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="VD: Giao dịch đêm giá trị cao"
              />
            </div>
            <div>
              <label className="label">Nhóm</label>
              <input
                className="field"
                value={draft.category}
                onChange={(event) => setDraft((prev) => ({ ...prev, category: event.target.value }))}
                placeholder="amount, velocity, geo…"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Mô tả</label>
              <input
                className="field"
                value={draft.description}
                onChange={(event) => setDraft((prev) => ({ ...prev, description: event.target.value }))}
                placeholder="Rule này bắt tín hiệu gì?"
              />
            </div>
            <div>
              <label className="label">Mức độ</label>
              <select
                className="field"
                value={draft.severity}
                onChange={(event) => setDraft((prev) => ({ ...prev, severity: event.target.value as typeof draft.severity }))}
              >
                <option value="high">Nghiêm trọng</option>
                <option value="medium">Trung bình</option>
                <option value="low">Thấp</option>
              </select>
            </div>
            <div>
              <div className="mb-1.5 flex justify-between">
                <label className="label mb-0">Điểm cộng</label>
                <span className="font-mono text-[11px] text-amber-400">+{draft.weight}</span>
              </div>
              <input
                type="range"
                min={1}
                max={100}
                value={draft.weight}
                onChange={(event) => setDraft((prev) => ({ ...prev, weight: Number(event.target.value) }))}
                className="mt-2 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-ink-700 accent-mint-400"
              />
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="label mb-0">Điều kiện (AND)</label>
              <button
                className="btn-ghost btn-sm px-2 py-1 text-[10px]"
                onClick={() =>
                  conditionFields[0] && setDraft((prev) => ({ ...prev, conditions: [...prev.conditions, defaultCondition(conditionFields[0])] }))
                }
              >
                <Plus size={11} /> Thêm điều kiện
              </button>
            </div>
            <div className="space-y-2">
              {draft.conditions.map((condition, index) => {
                const field = conditionFields.find((item) => item.key === condition.field);
                return (
                  <div key={index} className="flex flex-col gap-2 rounded-xl border border-white/[0.06] bg-white/[0.018] p-2.5 sm:flex-row sm:items-center">
                    <select
                      value={condition.field}
                      onChange={(event) => changeField(index, event.target.value)}
                      className="field py-2 text-[11px] sm:w-[190px]"
                    >
                      {conditionFields.map((item) => (
                        <option key={item.key} value={item.key}>{item.label}</option>
                      ))}
                    </select>
                    <select
                      value={condition.op}
                      onChange={(event) => updateCondition(index, { ...condition, op: event.target.value })}
                      className="field py-2 text-[11px] sm:w-[120px]"
                    >
                      {(field?.ops ?? ["=="]).map((op) => (
                        <option key={op} value={op}>{OP_LABELS[op] ?? op}</option>
                      ))}
                    </select>

                    {field?.type === "bool" ? (
                      <select
                        value={String(condition.value)}
                        onChange={(event) => updateCondition(index, { ...condition, value: event.target.value === "true" })}
                        className="field flex-1 py-2 text-[11px]"
                      >
                        <option value="true">Có</option>
                        <option value="false">Không</option>
                      </select>
                    ) : field?.type === "enum" ? (
                      <div className="flex flex-1 flex-wrap gap-1.5">
                        {(field.options ?? []).map((option) => {
                          const values = Array.isArray(condition.value) ? condition.value : [];
                          const active = values.includes(option);
                          return (
                            <button
                              key={option}
                              type="button"
                              onClick={() =>
                                updateCondition(index, {
                                  ...condition,
                                  value: active ? values.filter((value) => value !== option) : [...values, option],
                                })
                              }
                              className={clsx(
                                "rounded-md border px-1.5 py-1 text-[9.5px] transition",
                                active
                                  ? "border-mint-400/40 bg-mint-500/15 text-mint-200"
                                  : "border-white/[0.07] bg-white/[0.02] text-slate-500 hover:text-slate-300",
                              )}
                            >
                              {option}
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <input
                        className={clsx("field flex-1 py-2 text-[11px]", field?.type === "number" && "font-mono")}
                        type={field?.type === "number" ? "number" : "text"}
                        value={String(condition.value)}
                        onChange={(event) =>
                          updateCondition(index, {
                            ...condition,
                            value: field?.type === "number" ? Number(event.target.value) : event.target.value,
                          })
                        }
                      />
                    )}

                    <button
                      className="icon-btn h-7 w-7 shrink-0 self-end text-slate-600 hover:text-coral-400 sm:self-auto"
                      onClick={() =>
                        setDraft((prev) => ({ ...prev, conditions: prev.conditions.filter((_, position) => position !== index) }))
                      }
                      aria-label="Xoá điều kiện"
                      disabled={draft.conditions.length === 1}
                    >
                      <X size={13} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-ink-950/40 px-3.5 py-3">
            <label className="flex cursor-pointer items-center gap-2 text-[11px] text-slate-400">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) => setDraft((prev) => ({ ...prev, enabled: event.target.checked }))}
                className="h-3.5 w-3.5 accent-mint-400"
              />
              Bật rule ngay sau khi lưu
            </label>
            <p className="text-[10px] text-slate-600">
              {draft.conditions.length} điều kiện · +{draft.weight} điểm
            </p>
          </div>
        </div>
      </Modal>
    </div>
  );
}

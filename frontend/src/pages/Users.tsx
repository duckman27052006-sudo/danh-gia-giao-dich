import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CheckCircle2, KeyRound, Mail, Pencil, ShieldCheck, UserPlus, Users } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, roleLabel } from "@/lib/format";
import type { Role, User } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { RoleBadge } from "@/components/Badges";
import { ErrorState, PageHeader, SkeletonRows } from "@/components/Ui";
import { Modal } from "@/components/Modal";
import { Disclosure, PanelHeader, StatStrip } from "@/components/Patterns";
import { useToast } from "@/lib/toast";

type Mode = "create" | "edit" | "password" | null;

/* ── ma trận quyền tĩnh (chỉ để đọc, không gọi API) ─────────────── */
type PermissionLevel = "full" | "edit" | "view" | "none";

const PERMISSION_STYLES: Record<PermissionLevel, { label: string; text: string; dot: string }> = {
  full: { label: "Toàn quyền", text: "text-mint-300", dot: "bg-mint-400" },
  edit: { label: "Thao tác", text: "text-azure-400", dot: "bg-azure-400" },
  view: { label: "Chỉ xem", text: "text-slate-400", dot: "bg-slate-600" },
  none: { label: "Không", text: "text-slate-600", dot: "border border-slate-500 bg-transparent" },
};

const PERMISSION_MATRIX: {
  group: string;
  hint: string;
  admin: PermissionLevel;
  analyst: PermissionLevel;
  viewer: PermissionLevel;
}[] = [
  { group: "Bảng điều khiển", hint: "Chỉ số rủi ro, xu hướng, cảnh báo", admin: "full", analyst: "view", viewer: "view" },
  { group: "Hàng chờ & case", hint: "Lọc, nhận case, xem chi tiết", admin: "full", analyst: "edit", viewer: "view" },
  { group: "Kết luận & ghi chú", hint: "Quyết định gian lận, ghi chú điều tra", admin: "full", analyst: "edit", viewer: "none" },
  { group: "Giải thích AI", hint: "Tạo và đọc bản giải thích", admin: "full", analyst: "edit", viewer: "view" },
  { group: "Rule engine", hint: "Tạo, sửa, bật/tắt rule", admin: "full", analyst: "none", viewer: "none" },
  { group: "Người dùng", hint: "Mời, đổi vai trò, đặt lại mật khẩu", admin: "full", analyst: "none", viewer: "none" },
  { group: "Audit trail", hint: "Tra cứu bản ghi bất biến", admin: "view", analyst: "none", viewer: "none" },
  { group: "Cấu hình & ngưỡng", hint: "Ngưỡng, trọng số, công tắc AI", admin: "full", analyst: "view", viewer: "view" },
];

const ROLE_SUMMARIES: { role: Role; text: string }[] = [
  { role: "admin", text: "Quản lý user, rule, cấu hình ngưỡng, xem audit trail và xử lý case." },
  { role: "analyst", text: "Xem hàng chờ, nhập giao dịch, tạo giải thích AI, ghi kết luận và audit." },
  { role: "viewer", text: "Chỉ xem dashboard, giao dịch, case và bản giải thích. Không thao tác." },
];

function PermissionCell({ level }: { level: PermissionLevel }) {
  const config = PERMISSION_STYLES[level];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[10.5px]">
      <span className={clsx("h-1.5 w-1.5 rounded-full", config.dot)} />
      <span className={config.text}>{config.label}</span>
    </span>
  );
}

export function UsersPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const [mode, setMode] = useState<Mode>(null);
  const [target, setTarget] = useState<User | null>(null);
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "analyst" as Role });
  const [resetPassword, setResetPassword] = useState("");

  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["users"] });
    queryClient.invalidateQueries({ queryKey: ["analysts"] });
    queryClient.invalidateQueries({ queryKey: ["audit"] });
  };

  const openCreate = () => {
    setForm({ full_name: "", email: "", password: "", role: "analyst" });
    setTarget(null);
    setMode("create");
  };

  const openEdit = (user: User) => {
    setForm({ full_name: user.full_name, email: user.email, password: "", role: user.role });
    setTarget(user);
    setMode("edit");
  };

  const openPassword = (user: User) => {
    setTarget(user);
    setResetPassword("");
    setMode("password");
  };

  const create = useMutation({
    mutationFn: () =>
      api<User>("/users", {
        method: "POST",
        body: JSON.stringify({
          full_name: form.full_name.trim(),
          email: form.email.trim(),
          password: form.password,
          role: form.role,
        }),
      }),
    onSuccess: () => {
      toast.push("Tài khoản đã được tạo. Mật khẩu không hiển thị lại.", "success", "Đã tạo người dùng");
      invalidate();
      setMode(null);
    },
    onError: (error) => toast.push(error.message, "error", "Không tạo được người dùng"),
  });

  const update = useMutation({
    mutationFn: (payload: Partial<{ full_name: string; role: Role; is_active: boolean }>) =>
      api<User>(`/users/${target?.id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    onSuccess: () => {
      toast.push("Thông tin người dùng đã được cập nhật.", "success", "Đã lưu");
      invalidate();
      setMode(null);
    },
    onError: (error) => toast.push(error.message, "error", "Không cập nhật được"),
  });

  const password = useMutation({
    mutationFn: () =>
      api(`/users/${target?.id}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ new_password: resetPassword }),
      }),
    onSuccess: () => {
      toast.push("Mật khẩu mới đã được đặt. Mọi phiên đăng nhập cũ bị thu hồi.", "success", "Đã đặt lại mật khẩu");
      invalidate();
      setMode(null);
    },
    onError: (error) => toast.push(error.message, "error", "Không đặt lại được mật khẩu"),
  });

  const toggleActive = useMutation({
    mutationFn: (user: User) =>
      api<User>(`/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !user.is_active }) }),
    onSuccess: (_, user) => {
      toast.push(
        user.is_active ? "Tài khoản đã bị vô hiệu hoá và thu hồi phiên." : "Tài khoản đã được kích hoạt lại.",
        "success",
      );
      invalidate();
    },
    onError: (error) => toast.push(error.message, "error", "Không đổi được trạng thái"),
  });

  const list = users.data ?? [];
  const active = list.filter((user) => user.is_active).length;

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Quản trị"
        title="Người dùng & phân quyền"
        subtitle="Quản lý tài khoản nội bộ theo mô hình RBAC: admin toàn quyền, analyst điều tra, viewer chỉ đọc."
        actions={
          <button type="button" className="btn-primary btn-sm" onClick={openCreate}>
            <UserPlus size={13} /> Mời người dùng
          </button>
        }
      />

      <StatStrip
        className="mb-4"
        items={[
          { label: "Tổng tài khoản", value: list.length, tone: "neutral" },
          { label: "Đang hoạt động", value: active, tone: "good" },
          { label: "Analyst", value: list.filter((user) => user.role === "analyst").length, tone: "neutral" },
          { label: "Đã vô hiệu hoá", value: list.length - active, tone: "danger" },
        ]}
      />

      <section className="panel overflow-hidden">
        <PanelHeader
          title="Danh sách tài khoản"
          subtitle="Đổi vai trò, đặt lại mật khẩu hoặc thu hồi phiên của từng tài khoản."
          icon={Users}
          badge={users.data ? `${list.length} tài khoản` : undefined}
          className="pb-3"
        />

        {users.isError ? (
          <ErrorState message={users.error.message} onRetry={() => users.refetch()} />
        ) : users.isLoading ? (
          <SkeletonRows rows={6} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse">
              <caption className="sr-only">Danh sách tài khoản nội bộ</caption>
              <thead>
                <tr className="bg-white/[0.012]">
                  <th className="th" scope="col">Người dùng</th>
                  <th className="th" scope="col">Vai trò</th>
                  <th className="th" scope="col">Trạng thái</th>
                  <th className="th" scope="col">Đăng nhập cuối</th>
                  <th className="th text-right" scope="col">Hành động</th>
                </tr>
              </thead>
              <tbody>
                {list.map((user) => (
                  <tr key={user.id} className="table-row">
                    <td className="td">
                      <div className="flex items-center gap-3">
                        <Avatar name={user.full_name} size="md" />
                        <div className="min-w-0">
                          <p className="text-[12px] font-medium text-white">
                            {user.full_name}
                            {user.id === me?.id && <span className="ml-2 text-[9px] text-mint-400">bạn</span>}
                          </p>
                          <p className="mt-0.5 flex items-center gap-1 truncate text-[10px] text-slate-500">
                            <Mail size={9} /> {user.email}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="td"><RoleBadge role={user.role} /></td>
                    <td className="td">
                      <span className="flex items-center gap-1.5 text-[10.5px]">
                        <span className={clsx("h-1.5 w-1.5 rounded-full", user.is_active ? "bg-mint-400" : "bg-slate-600")} />
                        <span className={user.is_active ? "text-mint-300" : "text-slate-500"}>
                          {user.is_active ? "Hoạt động" : "Đã khoá"}
                        </span>
                      </span>
                    </td>
                    <td className="td whitespace-nowrap text-[10.5px] text-slate-500">
                      {user.last_login_at ? formatDateTime(user.last_login_at) : "Chưa đăng nhập"}
                    </td>
                    <td className="td">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          className="icon-btn"
                          title="Đặt lại mật khẩu & thu hồi phiên"
                          aria-label={`Đặt lại mật khẩu cho ${user.full_name}`}
                          onClick={() => openPassword(user)}
                        >
                          <KeyRound size={13} />
                        </button>
                        <button
                          type="button"
                          className="icon-btn"
                          title="Đổi vai trò"
                          aria-label={`Đổi vai trò của ${user.full_name}`}
                          onClick={() => openEdit(user)}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          type="button"
                          className={clsx("icon-btn", user.is_active ? "hover:text-coral-400" : "hover:text-mint-400")}
                          title={user.is_active ? "Vô hiệu hoá & thu hồi phiên" : "Kích hoạt"}
                          aria-label={user.is_active ? `Vô hiệu hoá ${user.full_name}` : `Kích hoạt ${user.full_name}`}
                          onClick={() => toggleActive.mutate(user)}
                          disabled={toggleActive.isPending || user.id === me?.id}
                        >
                          {user.is_active ? <Ban size={13} /> : <CheckCircle2 size={13} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Disclosure
        title="Ma trận quyền theo vai trò"
        subtitle="3 vai trò × 8 nhóm chức năng"
        icon={ShieldCheck}
        defaultOpen={false}
        className="mt-4"
        bodyClassName="pb-4"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse">
            <caption className="sr-only">Ma trận quyền theo vai trò và nhóm chức năng</caption>
            <thead>
              <tr>
                <th className="th" scope="col">Nhóm chức năng</th>
                <th className="th text-center" scope="col"><span className="normal-case"><RoleBadge role="admin" /></span></th>
                <th className="th text-center" scope="col"><span className="normal-case"><RoleBadge role="analyst" /></span></th>
                <th className="th text-center" scope="col"><span className="normal-case"><RoleBadge role="viewer" /></span></th>
              </tr>
            </thead>
            <tbody>
              {PERMISSION_MATRIX.map((row) => (
                <tr key={row.group} className="table-row">
                  <td className="td">
                    <p className="text-[11.5px] font-medium text-white">{row.group}</p>
                    <p className="mt-0.5 text-[9.5px] text-slate-500">{row.hint}</p>
                  </td>
                  <td className="td text-center"><PermissionCell level={row.admin} /></td>
                  <td className="td text-center"><PermissionCell level={row.analyst} /></td>
                  <td className="td text-center"><PermissionCell level={row.viewer} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid gap-2 border-t border-white/70 px-4 pb-1 pt-3 sm:grid-cols-3">
          {ROLE_SUMMARIES.map((item) => (
            <div key={item.role} className="rounded-xl border border-white/70 bg-white/45 px-3 py-2.5">
              <p className="text-[11px] font-semibold text-white">{roleLabel(item.role)}</p>
              <p className="mt-1 text-[9.5px] leading-relaxed text-slate-500">{item.text}</p>
            </div>
          ))}
        </div>
      </Disclosure>

      <Modal
        open={mode === "create"}
        onClose={() => setMode(null)}
        title="Mời người dùng"
        description="Tài khoản được tạo với mật khẩu tạm. Hãy yêu cầu người dùng đổi mật khẩu sau lần đăng nhập đầu tiên."
        footer={
          <>
            <button className="btn-ghost" onClick={() => setMode(null)}>Huỷ</button>
            <button
              className="btn-primary"
              onClick={() => create.mutate()}
              disabled={create.isPending || form.full_name.trim().length < 2 || form.password.length < 8 || !form.email}
            >
              {create.isPending ? "Đang tạo…" : "Tạo tài khoản"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="label" htmlFor="invite-name">Họ tên</label>
            <input id="invite-name" className="field" value={form.full_name} onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))} />
          </div>
          <div>
            <label className="label" htmlFor="invite-email">Email</label>
            <input id="invite-email" className="field" type="email" value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="invite-password">Mật khẩu tạm</label>
              <input
                id="invite-password"
                className="field font-mono"
                type="text"
                value={form.password}
                onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                minLength={8}
                placeholder="≥ 8 ký tự"
              />
            </div>
            <div>
              <label className="label" htmlFor="invite-role">Vai trò</label>
              <select id="invite-role" className="field" value={form.role} onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value as Role }))}>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={mode === "edit"}
        onClose={() => setMode(null)}
        title="Cập nhật người dùng"
        description={target?.email}
        size="sm"
        footer={
          <>
            <button className="btn-ghost" onClick={() => setMode(null)}>Huỷ</button>
            <button
              className="btn-primary"
              onClick={() => update.mutate({ full_name: form.full_name.trim(), role: form.role })}
              disabled={update.isPending || form.full_name.trim().length < 2}
            >
              {update.isPending ? "Đang lưu…" : "Lưu thay đổi"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="label" htmlFor="edit-name">Họ tên</label>
            <input id="edit-name" className="field" value={form.full_name} onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))} />
          </div>
          <div>
            <label className="label" htmlFor="edit-role">Vai trò</label>
            <select id="edit-role" className="field" value={form.role} onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value as Role }))}>
              <option value="analyst">Analyst — điều tra</option>
              <option value="admin">Admin — toàn quyền</option>
              <option value="viewer">Viewer — chỉ xem</option>
            </select>
            <p className="mt-1.5 text-[10px] text-slate-500">
              Không thể hạ quyền hoặc vô hiệu hoá admin hoạt động cuối cùng của hệ thống.
            </p>
          </div>
          <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
            <p className="text-[10px] text-slate-500">Vai trò hiện tại</p>
            <p className="mt-1 text-[11px] text-slate-300">{roleLabel(target?.role ?? "viewer")}</p>
          </div>
        </div>
      </Modal>

      <Modal
        open={mode === "password"}
        onClose={() => setMode(null)}
        title="Đặt lại mật khẩu"
        description={`${target?.full_name} · ${target?.email}`}
        size="sm"
        footer={
          <>
            <button className="btn-ghost" onClick={() => setMode(null)}>Huỷ</button>
            <button className="btn-primary" onClick={() => password.mutate()} disabled={password.isPending || resetPassword.length < 8}>
              {password.isPending ? "Đang đặt…" : "Đặt lại mật khẩu"}
            </button>
          </>
        }
      >
        <div>
          <label className="label" htmlFor="reset-password">Mật khẩu mới</label>
          <input
            id="reset-password"
            className="field font-mono"
            type="text"
            value={resetPassword}
            onChange={(event) => setResetPassword(event.target.value)}
            placeholder="Tối thiểu 8 ký tự"
          />
          <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
            Mọi refresh token hiện tại của người dùng sẽ bị thu hồi. Hành động được ghi vào audit trail.
          </p>
        </div>
      </Modal>
    </div>
  );
}

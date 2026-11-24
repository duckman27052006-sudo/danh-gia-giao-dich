import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Eye, EyeOff, KeyRound, Lock, Mail, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LogoMark } from "@/components/Logo";
import { ScoreRing } from "@/components/ScoreRing";
import { Disclosure } from "@/components/Patterns";

const DEMO_ACCOUNTS = [
  { label: "Quản trị", email: "admin@fraudlens.vn", password: "Admin@12345", tone: "text-mint-300" },
  { label: "Chuyên viên", email: "analyst@fraudlens.vn", password: "Analyst@123", tone: "text-azure-400" },
  { label: "Chỉ xem", email: "viewer@fraudlens.vn", password: "Viewer@123", tone: "text-slate-400" },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  // Không prefill tài khoản/mật khẩu: trước đây bundle production chứa sẵn
  // thông tin đăng nhập admin, ai mở trang cũng thấy.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được máy chủ");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 top-1/4 h-[420px] w-[420px] rounded-full bg-mint-500/[0.08] blur-[100px]" />
        <div className="absolute -right-32 bottom-0 h-[380px] w-[380px] rounded-full bg-azure-500/[0.07] blur-[110px]" />
      </div>

      <section className="relative hidden w-[54%] flex-col justify-between border-r border-white/[0.06] p-10 lg:flex xl:p-14">
        <div className="flex items-center gap-2.5">
          <LogoMark size={34} />
          <div>
            <p className="text-[15px] font-semibold text-white">
              Fraud<span className="text-mint-400">Lens</span>
            </p>
            <p className="text-[8.5px] uppercase tracking-[0.24em] text-slate-500">Risk intelligence</p>
          </div>
        </div>

        <div className="max-w-[520px]">
          <p className="eyebrow mb-4">Explainable fraud operations</p>
          <h1 className="text-[34px] font-semibold leading-[1.15] tracking-tight text-white xl:text-[42px]">
            Bắt đúng giao dịch gian lận.
            <br />
            <span className="bg-gradient-to-r from-mint-300 via-mint-400 to-emerald-500 bg-clip-text text-transparent">
              Giải thích rõ vì sao.
            </span>
          </h1>
          <p className="mt-5 max-w-[440px] text-[13px] leading-relaxed text-slate-400">
            Kết hợp rule engine, mô hình học máy và AI giải thích cảnh báo — để chuyên viên điều tra hiểu tín hiệu rủi ro
            trước khi đưa ra bất kỳ kết luận nào.
          </p>

          <div className="mt-8 grid grid-cols-3 gap-3">
            {[
              { value: "2.6%", label: "Giao dịch bị gắn cờ" },
              { value: "0.977", label: "AUC tập kiểm thử" },
              { value: "100%", label: "Case có audit trail" },
            ].map((item) => (
              <div key={item.label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3">
                <p className="font-mono text-[18px] text-white">{item.value}</p>
                <p className="mt-1 text-[10px] leading-snug text-slate-500">{item.label}</p>
              </div>
            ))}
          </div>

          <div className="relative mt-10 max-w-[470px] animate-fade-up">
            <div className="panel relative overflow-hidden p-5">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-mint-400/50 to-transparent" />
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-mono text-[10px] text-slate-500">CASE-2026-0134</p>
                  <p className="mt-1 text-[13px] font-medium text-white">Giao dịch 24.800.000 ₫</p>
                  <p className="text-[10.5px] text-slate-500">Binance · Online · 02:14 sáng</p>
                </div>
                <ScoreRing score={92} size={58} stroke={4} />
              </div>
              <div className="mt-4 space-y-2">
                {[
                  ["Lệch quốc gia IP / thẻ", 88, "bg-coral-400"],
                  ["Thiết bị mới + giá trị cao", 74, "bg-amber-400"],
                  ["Tần suất bất thường 1 giờ", 61, "bg-amber-400"],
                ].map(([label, value, color]) => (
                  <div key={String(label)}>
                    <div className="mb-1 flex justify-between text-[10px]">
                      <span className="text-slate-400">{label}</span>
                      <span className="font-mono text-slate-500">{value}</span>
                    </div>
                    <div className="h-1 overflow-hidden rounded-full bg-white/[0.05]">
                      <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex items-center gap-2 rounded-lg border border-mint-400/15 bg-mint-500/[0.06] px-3 py-2">
                <Sparkles size={12} className="text-mint-300" />
                <p className="text-[10px] text-mint-200/90">
                  AI đã tóm tắt 4 tín hiệu · <span className="text-slate-400">chờ analyst xác nhận</span>
                </p>
              </div>
            </div>

            <div className="absolute -right-5 top-16 hidden w-[168px] rotate-2 animate-fade-up rounded-xl border border-amber-400/20 bg-ink-850/95 p-3 shadow-panel xl:block">
              <div className="flex items-center gap-1.5 text-amber-400">
                <TriangleAlert size={12} />
                <p className="text-[10px] font-medium">P1 · quá hạn 2h</p>
              </div>
              <p className="mt-1.5 text-[9.5px] leading-relaxed text-slate-500">
                SLA 4 giờ cho case rủi ro rất cao. Leo thang tự động cho trưởng nhóm.
              </p>
            </div>

            <div className="absolute -bottom-5 -left-4 hidden items-center gap-2 rounded-xl border border-white/10 bg-ink-900/95 px-3 py-2 shadow-panel xl:flex">
              <ShieldCheck size={13} className="text-mint-400" />
              <p className="text-[10px] text-slate-300">Con người quyết định cuối cùng</p>
            </div>
          </div>
        </div>

        <p className="text-[10px] text-slate-600">
          Dữ liệu demo tổng hợp · Không chứa thông tin khách hàng thật
        </p>
      </section>

      <section className="relative flex flex-1 items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-[380px]">
          <div className="mb-9 flex items-center gap-2.5 lg:hidden">
            <LogoMark size={32} />
            <p className="text-[15px] font-semibold text-white">
              Fraud<span className="text-mint-400">Lens</span>
            </p>
          </div>

          <p className="eyebrow mb-2">Đăng nhập hệ thống</p>
          <h2 className="text-[24px] font-semibold tracking-tight text-white">Chào mừng trở lại</h2>
          <p className="mt-2 text-[12px] leading-relaxed text-slate-400">
            Sử dụng tài khoản nội bộ để truy cập hàng chờ điều tra và audit trail.
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <div>
              <label className="label" htmlFor="email">
                Email công việc
              </label>
              <div className="relative">
                <Mail size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="field pl-10"
                  placeholder="ten@congty.vn"
                  required
                />
              </div>
            </div>
            <div>
              <label className="label" htmlFor="password">
                Mật khẩu
              </label>
              <div className="relative">
                <Lock size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="field px-10"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-500 transition hover:text-slate-300"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-xl border border-coral-400/25 bg-coral-500/[0.08] px-3.5 py-3 text-[11.5px] text-coral-400">
                <TriangleAlert size={14} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button type="submit" className="btn-primary w-full py-3" disabled={loading}>
              {loading ? "Đang xác thực…" : "Đăng nhập"}
              {!loading && <ArrowRight size={15} />}
            </button>
          </form>

          {/* Danh sách tài khoản demo chỉ tồn tại ở bản dev: Vite loại bỏ nhánh
              `import.meta.env.DEV` khi build production nên mật khẩu demo
              không nằm trong bundle phát hành. */}
          {import.meta.env.DEV && (
            <Disclosure
              title="Tài khoản demo"
              subtitle="3 vai trò · bấm để điền nhanh"
              icon={KeyRound}
              className="mt-7"
              bodyClassName="p-2"
            >
              <div className="space-y-1">
                {DEMO_ACCOUNTS.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    onClick={() => {
                      setEmail(account.email);
                      setPassword(account.password);
                      setError(null);
                    }}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition hover:bg-white/60"
                  >
                    <span className={`w-[76px] shrink-0 text-[10.5px] font-medium ${account.tone}`}>{account.label}</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-slate-500">{account.email}</span>
                    <ArrowRight size={12} className="shrink-0 text-slate-600" />
                  </button>
                ))}
              </div>
            </Disclosure>
          )}

          <p className="mx-auto mt-7 max-w-[320px] rounded-xl border border-white/70 bg-white/60 px-3 py-2 text-center text-[10px] leading-relaxed text-slate-600 backdrop-blur-sm">
            Phiên đăng nhập được bảo vệ bằng refresh token HTTP-only.
            <br />
            FraudLens v1.0 · Demo nội bộ
          </p>
        </div>
      </section>
    </div>
  );
}

import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { LogoMark } from "@/components/Logo";
import { LoginPage } from "@/pages/Login";
import { ForbiddenPage } from "@/pages/NotFound";

// Tách bundle theo trang: dashboard/case kéo thêm recharts, các trang quản trị
// hiếm khi mở nên không cần nằm trong gói JS tải ban đầu.
const DashboardPage = lazy(() => import("@/pages/Dashboard").then((m) => ({ default: m.DashboardPage })));
const QueuePage = lazy(() => import("@/pages/Queue").then((m) => ({ default: m.QueuePage })));
const CaseDetailPage = lazy(() => import("@/pages/CaseDetail").then((m) => ({ default: m.CaseDetailPage })));
const TransactionsPage = lazy(() => import("@/pages/Transactions").then((m) => ({ default: m.TransactionsPage })));
const RulesPage = lazy(() => import("@/pages/Rules").then((m) => ({ default: m.RulesPage })));
const UsersPage = lazy(() => import("@/pages/Users").then((m) => ({ default: m.UsersPage })));
const AuditPage = lazy(() => import("@/pages/Audit").then((m) => ({ default: m.AuditPage })));
const SettingsPage = lazy(() => import("@/pages/Settings").then((m) => ({ default: m.SettingsPage })));
const NotFoundPage = lazy(() => import("@/pages/NotFound").then((m) => ({ default: m.NotFoundPage })));

function BootSplash() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <div className="animate-pulse-soft">
        <LogoMark size={42} />
      </div>
      <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-600">Đang kiểm tra phiên…</p>
    </div>
  );
}

function PageFallback() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-white/10 border-t-mint-400" />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, booting } = useAuth();
  const location = useLocation();
  if (booting) return <BootSplash />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <ForbiddenPage />;
  return <>{children}</>;
}

export default function App() {
  const { user, booting } = useAuth();

  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route
          path="/login"
          element={booting ? <BootSplash /> : user ? <Navigate to="/" replace /> : <LoginPage />}
        />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="queue" element={<QueuePage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="cases/:id" element={<CaseDetailPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route
            path="rules"
            element={
              <RequireAdmin>
                <RulesPage />
              </RequireAdmin>
            }
          />
          <Route
            path="users"
            element={
              <RequireAdmin>
                <UsersPage />
              </RequireAdmin>
            }
          />
          <Route
            path="audit"
            element={
              <RequireAdmin>
                <AuditPage />
              </RequireAdmin>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

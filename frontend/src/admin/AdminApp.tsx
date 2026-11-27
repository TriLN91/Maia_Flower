import { useState, type FormEvent, type ReactNode } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router";
import { Button, ErrorBox } from "../components/ui";
import { friendlyError } from "../lib/errors";
import { login, logout, useSession } from "./api";
import { DashboardPage } from "./pages/DashboardPage";
import { ForecastPage } from "./pages/ForecastPage";
import { InventoryPage } from "./pages/InventoryPage";
import { OrderDetailPage, OrdersPage } from "./pages/OrdersPage";
import { PricingPage } from "./pages/PricingPage";
import { SettingsPage } from "./pages/SettingsPage";

const NAV = [
  { to: "/admin", label: "Tổng quan", icon: "📊", end: true },
  { to: "/admin/don-hang", label: "Đơn hàng", icon: "🧾" },
  { to: "/admin/kho", label: "Kho", icon: "🌷" },
  { to: "/admin/gia", label: "Mẫu & giá", icon: "🏷️" },
  { to: "/admin/du-bao", label: "Dự báo", icon: "📈" },
  { to: "/admin/cai-dat", label: "Cài đặt", icon: "⚙️", ownerOnly: true },
];

function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(
        err instanceof Error && "status" in err && err.status === 401
          ? "Email hoặc mật khẩu không đúng."
          : friendlyError(err),
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex min-h-dvh items-center justify-center bg-stone-50 p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-stone-200">
        <h1 className="text-xl font-extrabold text-rose-700">🌸 Maia Flower · Quản trị</h1>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Email</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username"
            className="min-h-11 w-full rounded-xl border-0 px-3 ring-1 ring-stone-200 focus:ring-2 focus:ring-rose-400" />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Mật khẩu</span>
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
            className="min-h-11 w-full rounded-xl border-0 px-3 ring-1 ring-stone-200 focus:ring-2 focus:ring-rose-400" />
        </label>
        {error && <ErrorBox message={error} />}
        <Button type="submit" className="w-full" loading={busy}>Đăng nhập</Button>
      </form>
    </div>
  );
}

function AdminLayout() {
  const session = useSession()!;
  const nav = NAV.filter((n) => !n.ownerOnly || session.role === "owner");
  return (
    <div className="min-h-dvh bg-stone-50 pb-20 text-stone-800 md:pb-0 md:pl-56">
      <aside className="fixed inset-y-0 left-0 hidden w-56 flex-col border-r border-stone-200 bg-white p-4 md:flex">
        <p className="mb-6 text-lg font-extrabold text-rose-700">🌸 Quản trị</p>
        <nav className="space-y-1">
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => `flex min-h-11 items-center gap-2 rounded-xl px-3 font-medium ${isActive ? "bg-rose-50 text-rose-700" : "text-stone-600 hover:bg-stone-100"}`}>
              <span aria-hidden>{n.icon}</span>{n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-1 text-sm">
          <p className="font-semibold">{session.fullName}</p>
          <p className="text-stone-500">{session.role === "owner" ? "Chủ shop" : "Thợ bó"}</p>
          <button onClick={logout} className="font-semibold text-rose-700">Đăng xuất</button>
        </div>
      </aside>
      <header className="sticky top-0 z-[1001] flex h-14 items-center justify-between border-b border-stone-200 bg-white/95 px-4 md:hidden">
        <span className="font-extrabold text-rose-700">🌸 Quản trị</span>
        <button onClick={logout} className="min-h-11 text-sm font-semibold text-rose-700">Đăng xuất</button>
      </header>
      <main className="mx-auto max-w-5xl p-4 md:p-6">
        <Outlet />
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-[1001] flex border-t border-stone-200 bg-white md:hidden">
        {nav.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
            className={({ isActive }) => `flex min-h-14 flex-1 flex-col items-center justify-center text-[11px] ${isActive ? "text-rose-700" : "text-stone-500"}`}>
            <span className="text-lg" aria-hidden>{n.icon}</span>{n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function RequireOwner({ children }: { children: ReactNode }) {
  return useSession()?.role === "owner" ? children : <Navigate to="/admin" replace />;
}

export default function AdminApp() {
  const session = useSession();
  const location = useLocation();
  if (!session) return location.pathname === "/admin" ? <LoginPage /> : <Navigate to="/admin" replace />;
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="don-hang" element={<OrdersPage />} />
        <Route path="don-hang/:id" element={<OrderDetailPage />} />
        <Route path="kho" element={<InventoryPage />} />
        <Route path="gia" element={<PricingPage />} />
        <Route path="du-bao" element={<ForecastPage />} />
        <Route path="cai-dat" element={<RequireOwner><SettingsPage /></RequireOwner>} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Route>
    </Routes>
  );
}


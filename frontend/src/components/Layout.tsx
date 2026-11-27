import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useEffect } from "react";
import { cartCount, useCart } from "../lib/cart";
import { ServerWakeBanner } from "./ServerWakeBanner";

export function Layout() {
  const count = cartCount(useCart());
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="min-h-dvh pb-28 text-stone-800">
      <ServerWakeBanner />
      <header className="sticky top-0 z-[1001] border-b border-rose-100 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-2xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-1.5 text-lg font-extrabold text-rose-700">
            <span aria-hidden>🌸</span> Maia Flower
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink
              to="/don-cua-toi"
              className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 hover:bg-rose-50"
            >
              Đơn của tôi
            </NavLink>
            <NavLink
              to="/gio-hang"
              className="relative rounded-lg px-3 py-2 text-xl hover:bg-rose-50"
              aria-label={`Giỏ hàng, ${count} bó`}
            >
              🛒
              {count > 0 && (
                <span className="absolute right-0.5 top-0.5 min-w-5 rounded-full bg-rose-600 px-1 text-center text-xs font-bold leading-5 text-white">
                  {count}
                </span>
              )}
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-4 py-5">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-2xl px-4 pb-6 text-center text-xs text-stone-400">
        Maia Flower · Dự án demo · Thanh toán qua cổng giả lập
      </footer>
    </div>
  );
}

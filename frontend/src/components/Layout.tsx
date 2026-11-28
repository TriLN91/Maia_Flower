import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useEffect } from "react";
import { cartCount, useCart } from "../lib/cart";
import { BagIcon, LeafIcon, ReceiptIcon } from "./icons";
import { ServerWakeBanner } from "./ServerWakeBanner";

export function Logo({ light }: { light?: boolean }) {
  return (
    <Link to="/" className="group flex items-center gap-2" aria-label="Maia Flower — trang chủ">
      <span
        className={`flex size-9 items-center justify-center rounded-full ${light ? "bg-white/10 text-white" : "bg-brand-700 text-white"}`}
      >
        <LeafIcon className="size-[18px]" />
      </span>
      <span className="leading-none">
        <span className={`block font-display text-xl font-semibold ${light ? "text-white" : "text-ink"}`}>
          Maia
        </span>
        <span
          className={`block text-[10px] font-semibold uppercase tracking-[.25em] ${light ? "text-white/60" : "text-sage-700"}`}
        >
          Flower studio
        </span>
      </span>
    </Link>
  );
}

const navCls = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3.5 py-2 text-sm font-medium transition ${isActive ? "bg-brand-50 text-brand-800" : "text-stone-600 hover:text-brand-700"}`;

export function Layout() {
  const count = cartCount(useCart());
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
    } else {
      window.scrollTo(0, 0);
    }
  }, [pathname, hash]);

  return (
    <div className="flex min-h-dvh flex-col">
      <ServerWakeBanner />
      <div className="bg-brand-800 px-4 py-2 text-center text-xs font-medium tracking-wide text-brand-50">
        Hoa nhập mỗi sáng · Giao nhanh trong 2 giờ<span className="hidden sm:inline"> tại TP.HCM · Không cần tạo tài khoản</span>
      </div>
      <header className="sticky top-0 z-[1001] border-b border-stone-200/70 bg-cream/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
          <Logo />
          <nav className="hidden items-center gap-1 md:flex" aria-label="Chính">
            <NavLink to="/" end className={navCls}>
              Cửa hàng
            </NavLink>
            <Link to="/#uu-dai" className={navCls({ isActive: false })}>
              Ưu đãi hôm nay
            </Link>
            <Link to="/#cach-dat" className={navCls({ isActive: false })}>
              Cách đặt hoa
            </Link>
          </nav>
          <div className="flex items-center gap-1">
            <NavLink
              to="/don-cua-toi"
              className="flex min-h-11 items-center gap-2 rounded-full px-3 text-sm font-medium text-stone-700 hover:bg-white"
            >
              <ReceiptIcon />
              <span className="hidden sm:inline">Đơn của tôi</span>
            </NavLink>
            <NavLink
              to="/gio-hang"
              className="relative flex min-h-11 items-center gap-2 rounded-full px-3 text-sm font-medium text-stone-700 hover:bg-white"
              aria-label={`Giỏ hàng, ${count} bó`}
            >
              <BagIcon />
              <span className="hidden sm:inline">Giỏ hàng</span>
              {count > 0 && (
                <span
                  key={count}
                  className="absolute left-6 top-1 min-w-5 animate-fade-up rounded-full bg-brand-700 px-1 text-center text-[11px] font-bold leading-5 text-white ring-2 ring-cream"
                >
                  {count}
                </span>
              )}
            </NavLink>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8">
        <Outlet />
      </main>

      <footer className="mt-16 bg-ink text-stone-300">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-3">
            <Logo light />
            <p className="text-sm leading-relaxed text-stone-400">
              Tiệm hoa bó thủ công. Mỗi bó được thợ cắm từ những cành tươi nhất trong kho ngay khi
              bạn đặt.
            </p>
          </div>
          <div className="space-y-2 text-sm">
            <h3 className="font-semibold text-white">Mua hoa</h3>
            <Link to="/" className="block hover:text-white">
              Tất cả mẫu hoa
            </Link>
            <Link to="/#uu-dai" className="block hover:text-white">
              Ưu đãi hoa tươi hôm nay
            </Link>
            <Link to="/don-cua-toi" className="block hover:text-white">
              Theo dõi đơn hàng
            </Link>
          </div>
          <div className="space-y-2 text-sm">
            <h3 className="font-semibold text-white">Giao hàng</h3>
            <p>Giao theo khung giờ bạn chọn, mỗi ngày</p>
            <p>Phí ship tính theo quãng đường thực tế</p>
            <p>Giữ hoa 15 phút trong lúc bạn thanh toán</p>
          </div>
          <div className="space-y-2 text-sm">
            <h3 className="font-semibold text-white">Về dự án</h3>
            <p className="text-stone-400">
              Maia Flower là dự án demo. Thanh toán chạy qua cổng giả lập, không trừ tiền thật.
            </p>
          </div>
        </div>
        <div className="border-t border-white/10 py-5 text-center text-xs text-stone-500">
          © {new Date().getFullYear()} Maia Flower studio
        </div>
      </footer>
    </div>
  );
}

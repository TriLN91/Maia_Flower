import { Link, NavLink, Outlet, useLocation } from "react-router";
import { toast, useToast } from "../lib/toast";
import { useEffect, useState } from "react";
import { cartCount, useCart } from "../lib/cart";
import { BagIcon, CheckIcon, LeafIcon, ReceiptIcon } from "./icons";
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

function Toaster() {
  const t = useToast();
  const { pathname } = useLocation();
  if (!t) return null;
  return (
    <div
      role="status"
      key={t.id}
      className="pb-safe fixed inset-x-0 bottom-24 z-[1002] flex justify-center px-4 lg:bottom-6"
    >
      <div className="flex w-full max-w-sm animate-fade-up items-center gap-3 rounded-2xl bg-ink py-2.5 pl-4 pr-2 text-sm text-white shadow-2xl">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sage-500">
          <CheckIcon className="size-4" />
        </span>
        <span className="min-w-0 flex-1 truncate">{t.text}</span>
        {pathname !== "/gio-hang" && (
          <Link
            to="/gio-hang"
            onClick={() => toast.hide()}
            className="shrink-0 rounded-xl px-3 py-2 font-semibold text-brand-200 hover:bg-white/10"
          >
            Xem giỏ
          </Link>
        )}
      </div>
    </div>
  );
}

export function Layout() {
  const count = cartCount(useCart());
  const { pathname, hash } = useLocation();
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => {
    if (hash) {
      document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
    } else {
      window.scrollTo(0, 0);
    }
  }, [pathname, hash]);

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#noi-dung"
        className="sr-only z-[2000] rounded-full bg-ink px-4 py-2 text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Bỏ qua tới nội dung
      </a>
      <ServerWakeBanner />
      <div className="bg-brand-800 px-4 py-2 text-center text-xs font-medium tracking-wide text-brand-50">
        Hoa nhập mỗi sáng · Giao nhanh trong 2 giờ<span className="hidden sm:inline"> tại TP.HCM · Không cần tạo tài khoản</span>
      </div>
      <header
        className={`sticky top-0 z-[1001] border-b bg-cream/90 backdrop-blur-md transition-shadow ${scrolled ? "border-stone-200/70 shadow-[0_8px_24px_-16px_rgba(67,24,36,.25)]" : "border-transparent"}`}
      >
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
              <span className="relative">
                <BagIcon />
                {count > 0 && (
                  <span
                    key={count}
                    className="absolute -right-2.5 -top-2 min-w-[18px] animate-fade-up rounded-full bg-brand-700 px-1 text-center text-[10px] font-bold leading-[18px] text-white ring-2 ring-cream"
                  >
                    {count}
                  </span>
                )}
              </span>
              <span className="ml-1 hidden sm:inline">Giỏ hàng</span>
            </NavLink>
          </div>
        </div>
      </header>

      <main id="noi-dung" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8">
        <Outlet />
      </main>

      <Toaster />

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
            <a
              href="https://github.com/TriLN91/Maia_Flower"
              target="_blank"
              rel="noreferrer"
              className="block hover:text-white"
            >
              Mã nguồn trên GitHub ↗
            </a>
            <Link to="/admin" className="block hover:text-white">
              Trang quản trị (demo)
            </Link>
          </div>
        </div>
        <div className="border-t border-white/10 py-5 text-center text-xs text-stone-500">
          © {new Date().getFullYear()} Maia Flower studio
        </div>
      </footer>
    </div>
  );
}

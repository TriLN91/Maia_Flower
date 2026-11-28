import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { ApiError } from "./api/client";
import { LeafIcon } from "./components/icons";
import { Layout } from "./components/Layout";
import { Empty, Loading } from "./components/ui";
import "./index.css";
import { CartPage } from "./pages/CartPage";
import { HomePage } from "./pages/HomePage";
import { MyOrdersPage } from "./pages/MyOrdersPage";
import { PaymentResultPage } from "./pages/PaymentResultPage";
import { TemplatePage } from "./pages/TemplatePage";
import { TrackPage } from "./pages/TrackPage";

// Tải tách riêng: khu quản trị và trang đặt hàng (có Leaflet) chỉ tải khi cần
const AdminApp = lazy(() => import("./admin/AdminApp"));
const CheckoutPage = lazy(() =>
  import("./pages/CheckoutPage").then((m) => ({ default: m.CheckoutPage })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Không thử lại lỗi 4xx (dữ liệu sai / không tìm thấy / bị giới hạn) — chỉ lỗi mạng & 5xx
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

function NotFound() {
  return (
    <Empty icon={<LeafIcon className="size-9" />} title="Không tìm thấy trang">
      <p>Đường dẫn này không tồn tại hoặc đã thay đổi.</p>
      <Link
        to="/"
        className="mt-5 inline-flex min-h-12 items-center rounded-full bg-brand-700 px-6 font-semibold text-white hover:bg-brand-800"
      >
        Về cửa hàng
      </Link>
    </Empty>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route
            path="admin/*"
            element={
              <Suspense fallback={<Loading />}>
                <AdminApp />
              </Suspense>
            }
          />
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="mau/:slug" element={<TemplatePage />} />
            <Route path="gio-hang" element={<CartPage />} />
            <Route
              path="dat-hang"
              element={
                <Suspense fallback={<Loading />}>
                  <CheckoutPage />
                </Suspense>
              }
            />
            <Route path="payment-result" element={<PaymentResultPage />} />
            <Route path="don/:token" element={<TrackPage />} />
            <Route path="don-cua-toi" element={<MyOrdersPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);

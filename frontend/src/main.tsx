import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { ApiError } from "./api/client";
import { Layout } from "./components/Layout";
import { Empty } from "./components/ui";
import "./index.css";
import { CartPage } from "./pages/CartPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { HomePage } from "./pages/HomePage";
import { MyOrdersPage } from "./pages/MyOrdersPage";
import { PaymentResultPage } from "./pages/PaymentResultPage";
import { TemplatePage } from "./pages/TemplatePage";
import { TrackPage } from "./pages/TrackPage";

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
    <Empty icon="🥀" title="Không tìm thấy trang">
      <Link to="/" className="font-semibold text-rose-700">
        Về trang chủ
      </Link>
    </Empty>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="mau/:slug" element={<TemplatePage />} />
            <Route path="gio-hang" element={<CartPage />} />
            <Route path="dat-hang" element={<CheckoutPage />} />
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

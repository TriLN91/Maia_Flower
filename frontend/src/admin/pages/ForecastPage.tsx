import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button, ErrorBox, Loading } from "../../components/ui";
import { friendlyError } from "../../lib/errors";
import { money } from "../../lib/format";
import { admin, useSession, type FlowerForecast } from "../api";
import { Card, PageTitle, inputCls } from "../ui";

const BAR = "#e11d48"; // một chuỗi -> một màu thương hiệu; tiêu đề gọi tên chuỗi, không cần chú giải

/** Biểu đồ cột 14 ngày: cột mảnh bo 4px ở đầu, khe 2px, lưới nhạt, rê/chạm để xem giá trị,
 * ngày lễ ghi chú bằng nhãn (không dùng màu thứ hai). */
function ForecastChart({ f }: { f: FlowerForecast }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 220, padL = 36, padB = 34, padT = 24;
  const max = Math.max(1, ...f.days.map((d) => d.predicted_qty));
  const nice = Math.ceil(max / 10) * 10;
  const plotW = W - padL - 8, plotH = H - padT - padB;
  const slot = plotW / f.days.length;
  const barW = Math.min(28, slot - 2);
  const y = (v: number) => padT + plotH - (v / nice) * plotH;
  const ticks = [0, nice / 2, nice];
  const d = hover != null ? f.days[hover] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Dự báo số cành ${f.name} 14 ngày tới`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - 8} y1={y(t)} y2={y(t)} stroke="#e7e5e4" strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="#78716c">{t}</text>
          </g>
        ))}
        {f.days.map((day, i) => {
          const x = padL + i * slot + (slot - barW) / 2;
          const top = y(day.predicted_qty);
          const h = Math.max(0, padT + plotH - top);
          const r = Math.min(4, h, barW / 2);
          const date = new Date(`${day.target_date}T12:00:00+07:00`);
          return (
            <g key={day.target_date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => setHover(i)}>
              {/* vùng bắt chuột rộng hơn cột */}
              <rect x={padL + i * slot} y={padT} width={slot} height={plotH} fill="transparent" />
              <path
                d={`M${x},${padT + plotH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${padT + plotH} Z`}
                fill={BAR}
                opacity={hover == null || hover === i ? 1 : 0.45}
              />
              {day.holiday && <text x={x + barW / 2} y={top - 6} textAnchor="middle" fontSize={10} fill="#44403c">★</text>}
              <text x={x + barW / 2} y={H - 18} textAnchor="middle" fontSize={10} fill="#78716c">{date.getDate()}</text>
              <text x={x + barW / 2} y={H - 6} textAnchor="middle" fontSize={9} fill="#a8a29e">
                {date.toLocaleDateString("vi-VN", { weekday: "narrow", timeZone: "Asia/Ho_Chi_Minh" })}
              </text>
            </g>
          );
        })}
      </svg>
      {d && (
        <div className="pointer-events-none absolute right-2 top-0 rounded-lg bg-stone-900 px-3 py-2 text-xs text-white shadow">
          <p className="font-semibold">{new Date(`${d.target_date}T12:00:00+07:00`).toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit" })}</p>
          <p>Dự báo: <b>{d.predicted_qty.toFixed(1)}</b> cành</p>
          <p className="opacity-80">Nền {d.base_qty.toFixed(1)} × hệ số {d.multiplier}{d.holiday ? ` (${d.holiday})` : ""}</p>
        </div>
      )}
      <p className="mt-1 text-xs text-stone-500">★ = ngày lễ (áp hệ số). Rê hoặc chạm vào cột để xem cách tính.</p>
    </div>
  );
}

export function ForecastPage() {
  const owner = useSession()?.role === "owner";
  const qc = useQueryClient();
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: admin.forecast });
  const restock = useQuery({ queryKey: ["restock"], queryFn: admin.restock });
  const backtest = useQuery({ queryKey: ["backtest"], queryFn: admin.backtest, enabled: owner, staleTime: 600_000 });
  const recompute = useMutation({ mutationFn: admin.recomputeForecast, onSuccess: () => qc.invalidateQueries({ queryKey: ["forecast"] }) });
  const [flowerId, setFlowerId] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  useEffect(() => {
    if (flowerId == null && forecast.data?.length) setFlowerId(forecast.data[0].flower_type_id);
  }, [forecast.data, flowerId]);

  if (forecast.isPending) return <Loading />;
  if (forecast.error) return <ErrorBox message={friendlyError(forecast.error)} />;
  const f = forecast.data.find((x) => x.flower_type_id === flowerId);
  const restockTotal = (restock.data ?? []).reduce((n, r) => n + r.est_cost, 0);

  return (
    <div className="space-y-4">
      <PageTitle action={owner && <Button variant="secondary" loading={recompute.isPending} onClick={() => recompute.mutate()}>Tính lại dự báo</Button>}>
        Dự báo nhu cầu
      </PageTitle>

      {forecast.data.length === 0 ? (
        <Card><p className="text-sm text-stone-500">Chưa có dự báo. Bấm “Tính lại dự báo” (job đêm cũng tự chạy lúc 00:15).</p></Card>
      ) : (
        <Card
          title={f ? `${f.name}: dự báo 14 ngày (tổng ${Math.round(f.total)} cành)` : "Dự báo"}
          action={
            <div className="flex items-center gap-2">
              <select value={flowerId ?? ""} onChange={(e) => setFlowerId(+e.target.value)} className={`${inputCls} w-auto`} aria-label="Loại hoa">
                {forecast.data.map((x) => <option key={x.flower_type_id} value={x.flower_type_id}>{x.name}</option>)}
              </select>
              <button onClick={() => setAsTable((v) => !v)} className="min-h-11 rounded-xl px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50">
                {asTable ? "Biểu đồ" : "Bảng"}
              </button>
            </div>
          }
        >
          {f && !asTable && <ForecastChart f={f} />}
          {f && asTable && (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-stone-500"><tr><th className="pb-1">Ngày</th><th>Nền</th><th>Hệ số</th><th>Dự báo</th></tr></thead>
              <tbody>
                {f.days.map((d) => (
                  <tr key={d.target_date} className="border-t border-stone-100">
                    <td className="py-1">{d.target_date}{d.holiday && <span className="ml-1 text-xs text-stone-500">({d.holiday})</span>}</td>
                    <td className="tabular-nums">{d.base_qty.toFixed(1)}</td>
                    <td className="tabular-nums">×{d.multiplier}</td>
                    <td className="font-semibold tabular-nums">{d.predicted_qty.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      <Card title="Gợi ý nhập hàng sáng mai" action={restockTotal > 0 && <span className="text-sm text-stone-600">≈ {money(restockTotal)}</span>}>
        {restock.isPending && <Loading />}
        {restock.data && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="text-left text-xs text-stone-500">
                <tr><th className="pb-2">Loại hoa</th><th>Phủ</th><th>Dự báo</th><th>Còn dùng được</th><th>Nên nhập</th><th>Ước tính</th></tr>
              </thead>
              <tbody>
                {restock.data.map((r) => (
                  <tr key={r.flower_type_id} className="border-t border-stone-100">
                    <td className="py-2 font-medium">{r.name}{r.holidays.length > 0 && <span className="ml-1 text-xs text-stone-500">★ {r.holidays.join(", ")}</span>}</td>
                    <td className="tabular-nums text-stone-500">{r.cover_days} ngày</td>
                    <td className="tabular-nums">{Math.round(r.forecast_total)}</td>
                    <td className="tabular-nums">{r.usable_stock}</td>
                    <td className={`tabular-nums ${r.suggested_qty ? "font-bold" : "text-stone-400"}`}>{r.suggested_qty || "—"}</td>
                    <td className="tabular-nums text-stone-600">{r.est_cost ? money(r.est_cost) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-stone-500">= dự báo × 1,15 (an toàn) − tồn còn hạn trong khoảng phủ, làm tròn theo bó 10 cành.</p>
          </div>
        )}
      </Card>

      {owner && backtest.data && (
        <Card title="Độ chính xác (backtest 56 ngày × 7 ngày tới)">
          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              { label: "Mô hình", s: backtest.data.model, strong: true },
              { label: "TB 14 ngày", s: backtest.data.moving_avg_14 },
              { label: "Cùng thứ tuần trước", s: backtest.data.naive_last_week },
            ].map((x) => (
              <div key={x.label} className={`rounded-xl p-3 ${x.strong ? "bg-brand-50" : "bg-stone-50"}`}>
                <p className="text-xs text-stone-500">{x.label}</p>
                <p className="text-xl font-extrabold tabular-nums">{x.s.wape?.toFixed(1)}%</p>
                <p className="text-xs text-stone-500">WAPE</p>
              </div>
            ))}
          </div>
          {backtest.data.improvement_vs_moving_avg_pct != null && (
            <p className="mt-2 text-sm text-stone-600">Sai số thấp hơn {backtest.data.improvement_vs_moving_avg_pct}% so với cách lấy trung bình 14 ngày ({backtest.data.model.points.toLocaleString("vi-VN")} điểm dữ liệu).</p>
          )}
        </Card>
      )}
    </div>
  );
}

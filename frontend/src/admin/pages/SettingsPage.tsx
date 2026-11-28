import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button, ErrorBox, Loading } from "../../components/ui";
import { friendlyError } from "../../lib/errors";
import { vnDate } from "../../lib/format";
import { admin, type PricingSettings, type SlotDay } from "../api";
import { Card, PageTitle, inputCls } from "../ui";

function PricingCard() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["pricing-settings"], queryFn: admin.pricingSettings });
  const [form, setForm] = useState<PricingSettings | null>(null);
  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);
  const save = useMutation({
    mutationFn: (s: PricingSettings) => admin.savePricingSettings(s),
    onSuccess: (s) => {
      qc.setQueryData(["pricing-settings"], s);
      qc.invalidateQueries({ queryKey: ["admin-templates"] });
      qc.invalidateQueries({ queryKey: ["urgency"] });
    },
  });
  if (!form) return <Loading />;
  const num = (k: keyof PricingSettings, label: string, suffix = "%") => (
    <label className="block space-y-1">
      <span className="text-sm text-stone-600">{label}</span>
      <span className="flex items-center gap-2">
        <input type="number" value={form[k] as number} onChange={(e) => setForm({ ...form, [k]: +e.target.value })} className={inputCls} />
        <span className="text-sm text-stone-500">{suffix}</span>
      </span>
    </label>
  );
  return (
    <Card title="Giảm giá động">
      <label className="mb-3 flex min-h-11 items-center gap-3 rounded-xl bg-stone-50 px-3">
        <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} className="size-5 accent-brand-600" />
        <span><b>Bật giảm giá tự động</b><span className="block text-xs text-stone-500">Tắt = mọi mẫu về giá gốc ngay khi lưu</span></span>
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        {num("max_discount_pct", "Trần giảm cho một mẫu")}
        {num("min_margin_pct", "Biên lợi nhuận tối thiểu")}
        {num("max_step_pct", "Mỗi lần đổi tối đa", "điểm %")}
        {num("horizon_days", "Coi là “sắp hết hạn” trong", "ngày")}
        {num("min_surplus_stems", "Chỉ giảm khi dư ít nhất", "cành")}
      </div>
      <p className="mt-3 text-xs text-stone-500">
        Bậc giảm theo số ngày còn lại: {form.tiers.map((t) => `≤${t.days_left_max} ngày: ${t.pct}%`).join(" · ")}
      </p>
      {save.error && <div className="mt-3"><ErrorBox message={friendlyError(save.error)} /></div>}
      {save.isSuccess && <p className="mt-3 text-sm text-emerald-700">✓ Đã lưu và tính lại giá.</p>}
      <Button className="mt-3" loading={save.isPending} onClick={() => save.mutate(form)}>Lưu & áp dụng</Button>
    </Card>
  );
}

function SlotRow({ s, date }: { s: SlotDay; date: string }) {
  const qc = useQueryClient();
  const [cap, setCap] = useState(s.capacity);
  const save = useMutation({
    mutationFn: (body: { capacity?: number; is_closed?: boolean }) => admin.overrideSlotDay(s.slot_id, date, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["slot-days", date] }),
  });
  return (
    <tr className="border-t border-stone-100">
      <td className="py-2 font-medium">{s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}</td>
      <td className="tabular-nums">{s.reserved_count}</td>
      <td><input type="number" min={s.reserved_count} value={cap} onChange={(e) => setCap(+e.target.value)} className={`${inputCls} w-20`} aria-label="Sức chứa" /></td>
      <td>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" checked={s.is_closed} onChange={(e) => save.mutate({ is_closed: e.target.checked })} className="size-5 accent-brand-600" />Nghỉ
        </label>
      </td>
      <td className="text-right">
        <Button variant="ghost" disabled={cap === s.capacity} loading={save.isPending} onClick={() => save.mutate({ capacity: cap })}>Lưu</Button>
        {save.error && <span className="block text-xs text-red-600">{friendlyError(save.error)}</span>}
      </td>
    </tr>
  );
}

function SlotsCard() {
  const [date, setDate] = useState(vnDate(1));
  const days = useQuery({ queryKey: ["slot-days", date], queryFn: () => admin.slotDays(date) });
  return (
    <Card title="Khung giờ giao theo ngày" action={<input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${inputCls} w-auto`} aria-label="Ngày" />}>
      <p className="mb-2 text-xs text-stone-500">Ngày lễ tăng sức chứa, ngày nghỉ đóng khung. Không hạ dưới số đơn đã đặt.</p>
      {days.isPending && <Loading />}
      {days.data && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-stone-500"><tr><th className="pb-1">Khung</th><th>Đã đặt</th><th>Sức chứa</th><th /><th /></tr></thead>
          <tbody>{days.data.map((s) => <SlotRow key={`${s.slot_id}-${date}-${s.capacity}-${s.is_closed}`} s={s} date={date} />)}</tbody>
        </table>
      )}
    </Card>
  );
}

export function SettingsPage() {
  return (
    <div className="space-y-4">
      <PageTitle>Cài đặt</PageTitle>
      <div className="grid gap-4 md:grid-cols-2">
        <PricingCard />
        <SlotsCard />
      </div>
    </div>
  );
}

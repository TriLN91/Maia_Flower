import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { api } from "../api/client";
import type { PlaceSuggestion, ShopInfo } from "../api/types";

export interface LatLng {
  lat: number;
  lng: number;
}

// Icon bằng emoji: tránh lỗi đường dẫn ảnh marker mặc định của Leaflet khi đóng gói bằng Vite
const pin = L.divIcon({
  html: '<div style="font-size:34px;line-height:34px;transform:translate(-4px,-30px)">📍</div>',
  className: "",
  iconSize: [34, 34],
});
const shopIcon = L.divIcon({
  html: '<div style="font-size:26px;line-height:26px;transform:translate(-2px,-20px)">🌸</div>',
  className: "",
  iconSize: [26, 26],
});

function ClickToPin({ onPick }: { onPick: (p: LatLng) => void }) {
  useMapEvents({ click: (e) => onPick({ lat: e.latlng.lat, lng: e.latlng.lng }) });
  return null;
}

function FlyTo({ target }: { target: LatLng | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lng], Math.max(map.getZoom(), 15), { duration: 0.6 });
  }, [target, map]);
  return null;
}

export function AddressMap({
  shop,
  value,
  onChange,
  onAddressFound,
}: {
  shop: ShopInfo;
  value: LatLng | null;
  onChange: (p: LatLng) => void;
  onAddressFound: (address: string) => void;
}) {
  const [flyTarget, setFlyTarget] = useState<LatLng | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  const pick = (p: LatLng, fly = false) => {
    onChange(p);
    if (fly) setFlyTarget(p);
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) return setGeoError("Trình duyệt không hỗ trợ định vị.");
    setLocating(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        pick({ lat: pos.coords.latitude, lng: pos.coords.longitude }, true);
      },
      () => {
        setLocating(false);
        setGeoError("Không lấy được vị trí — bạn chạm vào bản đồ để ghim nhé.");
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  return (
    <div className="space-y-2">
      {shop.address_search_enabled && (
        <AddressSearch
          onPick={(p, address) => {
            pick(p, true);
            onAddressFound(address);
          }}
        />
      )}
      <div className="overflow-hidden rounded-2xl ring-1 ring-stone-200">
        <MapContainer
          center={[shop.shop_lat, shop.shop_lng]}
          zoom={13}
          className="h-64 w-full"
          scrollWheelZoom={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Circle
            center={[shop.shop_lat, shop.shop_lng]}
            radius={shop.max_delivery_km * 1000 / 1.3}
            pathOptions={{ color: "#e11d48", weight: 1, fillOpacity: 0.04 }}
          />
          <Marker position={[shop.shop_lat, shop.shop_lng]} icon={shopIcon} />
          {value && (
            <Marker
              position={[value.lat, value.lng]}
              icon={pin}
              draggable
              eventHandlers={{
                dragend: (e) => {
                  const ll = (e.target as L.Marker).getLatLng();
                  pick({ lat: ll.lat, lng: ll.lng });
                },
              }}
            />
          )}
          <ClickToPin onPick={(p) => pick(p)} />
          <FlyTo target={flyTarget} />
        </MapContainer>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="text-stone-500">
          {value ? "Kéo ghim 📍 để chỉnh vị trí." : "Chạm vào bản đồ để ghim nơi nhận hoa."}
        </span>
        <button
          type="button"
          onClick={useMyLocation}
          className="min-h-11 rounded-xl px-3 font-semibold text-rose-700 hover:bg-rose-50"
        >
          {locating ? "Đang định vị…" : "📡 Dùng vị trí của tôi"}
        </button>
      </div>
      {geoError && <p className="text-sm text-amber-700">{geoError}</p>}
    </div>
  );
}

/** Gợi ý địa chỉ (Goong qua backend). Chỉ hiện khi shop đã cấu hình khóa bản đồ. */
function AddressSearch({ onPick }: { onPick: (p: LatLng, address: string) => void }) {
  const [text, setText] = useState("");
  const [items, setItems] = useState<PlaceSuggestion[]>([]);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (text.trim().length < 3) {
      setItems([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      api.autocomplete(text).then(setItems).catch(() => setItems([]));
    }, 350);
    return () => window.clearTimeout(timer.current);
  }, [text]);

  const list = useMemo(() => items.slice(0, 5), [items]);

  return (
    <div className="relative">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Tìm địa chỉ (vd. 12 Nguyễn Huệ)"
        className="min-h-11 w-full rounded-xl border-0 px-3 ring-1 ring-stone-200 focus:ring-2 focus:ring-rose-400"
        aria-label="Tìm địa chỉ"
      />
      {list.length > 0 && (
        <ul className="absolute z-[1100] mt-1 w-full overflow-hidden rounded-xl bg-white shadow-lg ring-1 ring-stone-200">
          {list.map((s) => (
            <li key={s.place_id}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left hover:bg-rose-50"
                onClick={async () => {
                  const p = await api.place(s.place_id);
                  setItems([]);
                  setText(s.description);
                  onPick({ lat: p.lat, lng: p.lng }, p.address);
                }}
              >
                <span className="block font-medium">{s.main_text}</span>
                <span className="block text-xs text-stone-500">{s.secondary_text}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

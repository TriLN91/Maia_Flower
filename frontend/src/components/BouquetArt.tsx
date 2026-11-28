import { memo, type ReactElement } from "react";
import type { Template } from "../api/types";

/**
 * Minh hoạ bó hoa vẽ bằng SVG từ ĐÚNG thành phần của mẫu (loại hoa, màu, số cành).
 * Shop chưa có ảnh chụp thật -> thay vì emoji, mỗi mẫu có một "chân dung" riêng, nhất quán và
 * nhẹ (không tải ảnh). Vị trí hoa tính tất định từ slug nên mỗi lần render đều giống nhau.
 * Có `image_url` thì dùng ảnh thật.
 */

type Kind =
  | "rose"
  | "tulip"
  | "hydrangea"
  | "daisy"
  | "pompon"
  | "carnation"
  | "baby"
  | "sunflower"
  | "orchid"
  | "filler"
  | "eucalyptus"
  | "leaf";

function kindOf(name: string): Kind {
  const n = name.toLowerCase();
  if (n.startsWith("lá bạch đàn")) return "eucalyptus";
  if (n.startsWith("lá")) return "leaf";
  if (n.includes("tulip")) return "tulip";
  if (n.includes("cẩm tú cầu")) return "hydrangea";
  if (n.includes("tana")) return "daisy";
  if (n.includes("mẫu đơn")) return "pompon";
  if (n.includes("cẩm chướng")) return "carnation";
  if (n.includes("baby")) return "baby";
  if (n.includes("hướng dương")) return "sunflower";
  if (n.includes("lan")) return "orchid";
  if (n.includes("thạch thảo")) return "filler";
  return "rose";
}

const COLOR: Record<string, string> = {
  đỏ: "#c3243b",
  hồng: "#f2a3b6",
  trắng: "#fbf8f2",
  kem: "#f5e1bf",
  vàng: "#f6c445",
  tím: "#a77bd0",
  xanh: "#8fbfe0",
};
const TINT: Record<string, string> = {
  đỏ: "#f8e3e3",
  hồng: "#fbe9ee",
  trắng: "#f1ede6",
  kem: "#f8eedf",
  vàng: "#fbf1d6",
  tím: "#efe7f6",
  xanh: "#e5eff4",
};

function colorFor(kind: Kind, color: string): string {
  if (kind === "tulip") return "#ee7d9d";
  if (kind === "carnation") return "#ec86a4";
  if (kind === "sunflower") return "#f3b51c";
  if (kind === "baby") return "#ffffff";
  if (kind === "filler") return "#8f62bf";
  return COLOR[color] ?? "#e9a0b2";
}

// ---- RNG tất định ----
function seedOf(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}
function rng(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Làm tối màu hex theo tỉ lệ (để vẽ cánh trong, nhụy). */
function shade(hex: string, f: number) {
  const n = parseInt(hex.slice(1), 16);
  const c = (v: number) => Math.max(0, Math.min(255, Math.round(v * f)));
  return `rgb(${c(n >> 16)},${c((n >> 8) & 255)},${c(n & 255)})`;
}

const OUTLINE = "rgba(60,30,30,.18)";

function Bloom({ kind, fill, r, rot, rand }: { kind: Kind; fill: string; r: number; rot: number; rand: () => number }) {
  const dark = shade(fill, 0.82);
  switch (kind) {
    case "rose":
      return (
        <g transform={`rotate(${rot})`}>
          <circle r={r} fill={fill} stroke={OUTLINE} strokeWidth={0.6} />
          <path
            d={`M${-r * 0.62} ${r * 0.1} A${r * 0.62} ${r * 0.62} 0 1 1 ${r * 0.3} ${r * 0.55}`}
            fill="none"
            stroke={dark}
            strokeWidth={1.3}
            strokeLinecap="round"
          />
          <path
            d={`M${-r * 0.3} ${-r * 0.05} A${r * 0.33} ${r * 0.33} 0 1 1 ${r * 0.15} ${r * 0.28}`}
            fill="none"
            stroke={dark}
            strokeWidth={1.2}
            strokeLinecap="round"
          />
          <circle r={r * 0.12} fill={dark} />
        </g>
      );
    case "tulip": {
      const s = r;
      return (
        <g transform={`rotate(${rot * 0.25})`}>
          <path
            d={`M${-s * 0.9} ${-s * 0.5} L${-s * 0.45} ${-s} L0 ${-s * 0.5} L${s * 0.45} ${-s} L${s * 0.9} ${-s * 0.5} Q${s} ${s * 0.9} 0 ${s} Q${-s} ${s * 0.9} ${-s * 0.9} ${-s * 0.5}Z`}
            fill={fill}
            stroke={OUTLINE}
            strokeWidth={0.6}
          />
          <path d={`M0 ${-s * 0.5} Q${s * 0.15} ${s * 0.3} 0 ${s}`} fill="none" stroke={dark} strokeWidth={1} />
        </g>
      );
    }
    case "sunflower":
      return (
        <g transform={`rotate(${rot})`}>
          {Array.from({ length: 14 }, (_, i) => (
            <ellipse
              key={i}
              cx={0}
              cy={-r * 0.68}
              rx={r * 0.2}
              ry={r * 0.42}
              fill={fill}
              stroke={OUTLINE}
              strokeWidth={0.4}
              transform={`rotate(${(360 / 14) * i})`}
            />
          ))}
          <circle r={r * 0.46} fill="#5a3a1b" />
          <circle r={r * 0.3} fill="#47301a" />
        </g>
      );
    case "daisy":
      return (
        <g transform={`rotate(${rot})`}>
          {Array.from({ length: 10 }, (_, i) => (
            <ellipse
              key={i}
              cy={-r * 0.6}
              rx={r * 0.22}
              ry={r * 0.45}
              fill="#fffdf8"
              stroke={OUTLINE}
              strokeWidth={0.4}
              transform={`rotate(${36 * i})`}
            />
          ))}
          <circle r={r * 0.32} fill="#f2c230" />
        </g>
      );
    case "pompon":
      return (
        <g>
          {Array.from({ length: 9 }, (_, i) => {
            const a = (i / 9) * Math.PI * 2;
            return <circle key={i} cx={Math.cos(a) * r * 0.62} cy={Math.sin(a) * r * 0.62} r={r * 0.42} fill={fill} stroke={OUTLINE} strokeWidth={0.4} />;
          })}
          <circle r={r * 0.6} fill={shade(fill, 0.95)} />
          <circle r={r * 0.28} fill={dark} />
        </g>
      );
    case "carnation":
      return (
        <g transform={`rotate(${rot})`}>
          {Array.from({ length: 12 }, (_, i) => {
            const a = (i / 12) * Math.PI * 2;
            return <circle key={i} cx={Math.cos(a) * r * 0.78} cy={Math.sin(a) * r * 0.78} r={r * 0.3} fill={fill} />;
          })}
          <circle r={r * 0.82} fill={fill} stroke={OUTLINE} strokeWidth={0.4} />
          {Array.from({ length: 6 }, (_, i) => {
            const a = (i / 6) * Math.PI * 2;
            return <circle key={i} cx={Math.cos(a) * r * 0.38} cy={Math.sin(a) * r * 0.38} r={r * 0.22} fill={dark} opacity={0.55} />;
          })}
        </g>
      );
    case "hydrangea":
      return (
        <g>
          <circle r={r} fill={shade(fill, 0.92)} />
          {Array.from({ length: 16 }, (_, i) => {
            const a = rand() * Math.PI * 2;
            const d = Math.sqrt(rand()) * r * 0.78;
            const f = 0.88 + rand() * 0.24;
            return (
              <g key={i} transform={`translate(${Math.cos(a) * d} ${Math.sin(a) * d}) rotate(${rand() * 90})`}>
                {[0, 90, 180, 270].map((t) => (
                  <ellipse key={t} cy={-2.4} rx={1.9} ry={2.6} fill={shade(fill, f)} transform={`rotate(${t})`} />
                ))}
                <circle r={0.8} fill="#ffffff" opacity={0.8} />
              </g>
            );
          })}
        </g>
      );
    case "orchid":
      return (
        <g transform={`rotate(${rot})`}>
          {Array.from({ length: 5 }, (_, i) => (
            <ellipse
              key={i}
              cy={-r * 0.55}
              rx={r * 0.42}
              ry={r * 0.58}
              fill={fill}
              stroke={OUTLINE}
              strokeWidth={0.5}
              transform={`rotate(${72 * i})`}
            />
          ))}
          <ellipse cy={r * 0.12} rx={r * 0.24} ry={r * 0.3} fill={shade(fill, 0.6)} />
          <circle r={r * 0.12} fill="#f6d36b" />
        </g>
      );
    default:
      return null;
  }
}

const BLOOM_SIZE: Partial<Record<Kind, number>> = {
  rose: 12.5,
  tulip: 11,
  hydrangea: 21,
  sunflower: 16,
  daisy: 8.5,
  pompon: 10.5,
  carnation: 11.5,
  orchid: 12.5,
};

interface Placed {
  kind: Kind;
  fill: string;
  r: number;
  x: number;
  y: number;
  rot: number;
}

function compose(template: Template) {
  const rand = rng(seedOf(template.slug || template.name));
  const blooms: { kind: Kind; fill: string }[] = [];
  const sprays: { kind: Kind; fill: string; n: number }[] = [];
  const greens: Kind[] = [];
  for (const it of template.items) {
    const kind = kindOf(it.flower_type.name);
    const fill = colorFor(kind, it.flower_type.color);
    if (kind === "eucalyptus" || kind === "leaf") greens.push(kind);
    else if (kind === "baby" || kind === "filler") sprays.push({ kind, fill, n: it.quantity });
    else {
      // Bó lớn thì thu gọn số bông vẽ (giữ tỉ lệ giữa các loại), tối đa ~13 bông
      for (let i = 0; i < it.quantity; i++) blooms.push({ kind, fill });
    }
  }
  const MAX = 13;
  let main = blooms;
  if (blooms.length > MAX) {
    const step = blooms.length / MAX;
    main = Array.from({ length: MAX }, (_, i) => blooms[Math.floor(i * step)]);
  }
  // Trộn tất định để các loại hoa xen kẽ tự nhiên
  for (let i = main.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [main[i], main[j]] = [main[j], main[i]];
  }

  const cx = 100;
  const cy = 92;
  const area = main.reduce((s, b) => s + (BLOOM_SIZE[b.kind] ?? 11) ** 2, 0);
  const natural = Math.max(12, Math.sqrt(area) * 0.95);
  // Bó ít bông thì phóng to bông lên để cụm hoa luôn tròn đầy, cân với giấy gói
  const R = Math.min(58, Math.max(44, natural));
  const grow = Math.min(1.7, Math.max(1, R / natural));
  const placed: Placed[] = main.map((b, i) => {
    // Xếp kiểu hoa hướng dương (phyllotaxis): đều, tròn đầy như bó hoa thật
    const t = main.length === 1 ? 0 : Math.sqrt((i + 0.5) / main.length);
    const a = i * 2.39996 + rand() * 0.3;
    const r = (BLOOM_SIZE[b.kind] ?? 11) * grow * (0.92 + rand() * 0.16);
    return {
      ...b,
      r,
      x: cx + Math.cos(a) * (R - r * 0.5) * t,
      y: cy + Math.sin(a) * (R - r * 0.5) * t * 0.8,
      rot: rand() * 360,
    };
  });
  // Bông ở dưới vẽ sau (đè lên) -> có chiều sâu
  placed.sort((p, q) => p.y - q.y);

  return { rand, placed, sprays, greens, R, cx, cy };
}

function Art({ template }: { template: Template }) {
  const { rand, placed, sprays, greens, R, cx, cy } = compose(template);
  const main = template.items[0]?.flower_type.color ?? "hồng";
  const bg = TINT[main] ?? "#f6ecee";
  const id = `b${seedOf(template.slug)}`;

  // Lá: các cành toả ra phía sau cụm hoa
  const leafEls: ReactElement[] = [];
  const nLeaves = greens.length ? 7 + greens.length * 2 : 6;
  for (let i = 0; i < nLeaves; i++) {
    const kind = greens.length ? greens[i % greens.length] : "leaf";
    const a = Math.PI * (1.05 + (i / (nLeaves - 1 || 1)) * 0.9) + (rand() - 0.5) * 0.25;
    const len = R + 14 + rand() * 10;
    const ex = cx + Math.cos(a) * len;
    const ey = cy + 6 + Math.sin(a) * len * 0.9;
    const green = kind === "eucalyptus" ? "#8aa596" : "#5f8a4e";
    const leaves: ReactElement[] = [];
    for (let k = 1; k <= 4; k++) {
      const f = 0.35 + k * 0.16;
      const lx = cx + (ex - cx) * f;
      const ly = cy + 6 + (ey - cy - 6) * f;
      const deg = (a * 180) / Math.PI;
      for (const side of [-1, 1]) {
        leaves.push(
          kind === "eucalyptus" ? (
            <circle key={`${k}${side}`} cx={lx + Math.cos(a + side * 1.4) * 4.2} cy={ly + Math.sin(a + side * 1.4) * 4.2} r={3.9} fill={green} stroke="rgba(0,0,0,.08)" strokeWidth={0.4} />
          ) : (
            // Lá nhọn mọc chếch hai bên cành
            <path
              key={`${k}${side}`}
              d="M0 0 Q3.4 -5.5 0 -12 Q-3.4 -5.5 0 0Z"
              fill={side > 0 ? green : "#6f9a5c"}
              transform={`translate(${lx} ${ly}) rotate(${deg + 90 + side * 42})`}
            />
          ),
        );
      }
    }
    leafEls.push(
      <g key={i}>
        <path d={`M${cx} ${cy + 6} L${ex} ${ey}`} stroke={green} strokeWidth={1.1} />
        {leaves}
      </g>,
    );
  }

  // Hoa phụ (baby, thạch thảo): chùm chấm nhỏ ở mép cụm hoa
  const sprayEls: ReactElement[] = [];
  sprays.forEach((s, si) => {
    const groups = Math.min(9, 3 + s.n);
    for (let g = 0; g < groups; g++) {
      const a = Math.PI * 2 * (g / groups) + si * 0.6 + rand() * 0.4;
      const d = R * (0.8 + rand() * 0.3);
      const gx = cx + Math.cos(a) * d;
      const gy = cy + Math.sin(a) * d * 0.8;
      for (let k = 0; k < 6; k++) {
        sprayEls.push(
          <circle
            key={`${si}-${g}-${k}`}
            cx={gx + (rand() - 0.5) * 11}
            cy={gy + (rand() - 0.5) * 9}
            r={s.kind === "baby" ? 1.7 : 1.5}
            fill={s.fill}
            stroke={s.kind === "baby" ? "rgba(0,0,0,.12)" : "none"}
            strokeWidth={0.4}
          />,
        );
      }
    }
  });

  return (
    <svg viewBox="0 0 200 250" preserveAspectRatio="xMidYMid slice" className="h-full w-full" role="img" aria-label={`Minh hoạ bó ${template.name}`}>
      <defs>
        <radialGradient id={`${id}g`} cx="50%" cy="38%" r="70%">
          <stop offset="0" stopColor="#ffffff" stopOpacity={0.9} />
          <stop offset="1" stopColor={bg} stopOpacity={1} />
        </radialGradient>
        <linearGradient id={`${id}p`} x1="0" x2="1">
          <stop offset="0" stopColor="#ead8c3" />
          <stop offset="0.5" stopColor="#f6ebdd" />
          <stop offset="1" stopColor="#e2cdb5" />
        </linearGradient>
      </defs>
      <rect width="200" height="250" fill={`url(#${id}g)`} />
      <ellipse cx="100" cy="238" rx="46" ry="5" fill="rgba(60,30,20,.08)" />
      {/* Cuống hoa lộ dưới giấy gói */}
      {[-6, -2, 2, 6].map((d) => (
        <path key={d} d={`M${100 + d} 190 L${100 + d * 1.6} 236`} stroke="#6d8b55" strokeWidth={1.6} strokeLinecap="round" />
      ))}
      {/* Giấy gói phía sau */}
      <path d="M44 96 L100 222 L156 96 Q100 76 44 96Z" fill="#eadbc8" />
      {leafEls}
      {sprayEls.slice(0, Math.floor(sprayEls.length / 2))}
      {placed.map((p, i) => (
        <g key={i} transform={`translate(${p.x} ${p.y})`}>
          <Bloom kind={p.kind} fill={p.fill} r={p.r} rot={p.rot} rand={rand} />
        </g>
      ))}
      {sprayEls.slice(Math.floor(sprayEls.length / 2))}
      {/* Giấy gói phía trước + nơ */}
      <path d="M52 132 Q100 150 148 132 L104 226 Q100 230 96 226Z" fill={`url(#${id}p)`} stroke="rgba(90,60,30,.15)" strokeWidth={0.6} />
      <path d="M52 132 Q78 142 100 146 L98 226 Q97 228 96 226Z" fill="rgba(255,255,255,.25)" />
      <g transform="translate(100 176)">
        <path d="M0 0 C-14 -12 -24 -4 -18 4 C-13 9 -6 4 0 0Z" fill="#94354b" />
        <path d="M0 0 C14 -12 24 -4 18 4 C13 9 6 4 0 0Z" fill="#94354b" />
        <path d="M-2 1 L-9 22 L-4 20 L0 3Z M2 1 L9 22 L4 20 L0 3Z" fill="#7a2b3e" />
        <circle r={3.2} fill="#7a2b3e" />
      </g>
    </svg>
  );
}

const MemoArt = memo(Art, (a, b) => a.template.slug === b.template.slug);

export function BouquetArt({
  template,
  className = "aspect-[4/5]",
}: {
  template: Template;
  className?: string;
}) {
  if (template.image_url)
    return <img src={template.image_url} alt={template.name} className={`w-full object-cover ${className}`} loading="lazy" />;
  return (
    <div className={`w-full overflow-hidden ${className}`}>
      <MemoArt template={template} />
    </div>
  );
}

/** Màu chấm đại diện cho một loại hoa (dùng trong danh sách thành phần, bộ lọc). */
export function flowerDot(name: string, color: string) {
  const k = kindOf(name);
  if (k === "eucalyptus") return "#8aa596";
  if (k === "leaf") return "#5f8a4e";
  return colorFor(k, color);
}

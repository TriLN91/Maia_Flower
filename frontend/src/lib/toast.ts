import { useSyncExternalStore } from "react";

/** Thông báo nhỏ "Đã thêm vào giỏ" — một store tối giản, không cần thư viện. */
type Toast = { id: number; text: string } | null;

let current: Toast = null;
let timer: number | undefined;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const toast = {
  show(text: string) {
    current = { id: Date.now(), text };
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      current = null;
      emit();
    }, 2800);
    emit();
  },
  hide() {
    current = null;
    emit();
  },
};

export function useToast() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => current,
  );
}

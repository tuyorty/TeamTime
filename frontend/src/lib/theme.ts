import { useCallback, useEffect, useSyncExternalStore } from "react";

export type ThemePref = "system" | "light" | "dark";
const KEY = "tt-theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");
const listeners = new Set<() => void>();

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function apply(pref: ThemePref) {
  const dark = pref === "dark" || (pref === "system" && media().matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function useTheme() {
  const pref = useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    read,
    () => "system" as ThemePref,
  );

  useEffect(() => {
    apply(pref);
    if (pref !== "system") return;
    const m = media();
    const onChange = () => apply("system");
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [pref]);

  const setPref = useCallback((next: ThemePref) => {
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      /* приватный режим */
    }
    apply(next);
    for (const l of listeners) l();
  }, []);

  const isDark = pref === "dark" || (pref === "system" && typeof window !== "undefined" && media().matches);
  return { pref, setPref, isDark };
}

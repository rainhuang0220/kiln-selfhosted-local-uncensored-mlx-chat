export type ThemePref = "light" | "dark" | "system";

const KEY = "kiln-theme";

export function readThemePref(): ThemePref {
  const v = localStorage.getItem(KEY);
  if (v === "dark" || v === "light" || v === "system") return v;
  return "light";
}

export function applyTheme(pref: ThemePref): void {
  const dark =
    pref === "dark" ||
    (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  localStorage.setItem(KEY, pref);
}

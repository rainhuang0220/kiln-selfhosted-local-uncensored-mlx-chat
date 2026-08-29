export function relativeTime(ms: number): string {
  const delta = Date.now() - ms;
  const sec = Math.max(0, Math.floor(delta / 1000));
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  const day = Math.floor(hr / 24);
  if (day < 14) return `${day}d`;
  return new Date(ms).toLocaleDateString();
}

export function formatTokens(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

export function formatTokensShort(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Math.abs(n) < 1000) return String(n);
  if (Math.abs(n) < 10_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${Math.round(n / 1000)}k`;
}

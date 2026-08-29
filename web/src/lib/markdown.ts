export function splitOpenFence(text: string): { complete: string; openFence: string } {
  const ticks = text.split("```").length - 1;
  if (ticks % 2 === 0) return { complete: text, openFence: "" };
  const idx = text.lastIndexOf("```");
  return { complete: text.slice(0, idx), openFence: text.slice(idx) };
}

export function heuristicTitle(text: string): string {
  const collapsed = text.trim().replace(/\s+/g, " ");
  if (!collapsed) return "New conversation";
  return collapsed.length <= 48 ? collapsed : collapsed.slice(0, 48).trimEnd() + "…";
}

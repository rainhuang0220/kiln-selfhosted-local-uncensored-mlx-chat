import type { ConversationSummary } from "../types/chat";

function startOfDay(ms: number): number {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export function groupConversations(list: ConversationSummary[]): { label: string; items: ConversationSummary[] }[] {
  const now = startOfDay(Date.now());
  const yday = now - 86400000;
  const buckets: Record<string, ConversationSummary[]> = {
    Today: [],
    Yesterday: [],
    Older: [],
  };
  for (const c of list) {
    const day = startOfDay(c.updated_at);
    if (day >= now) buckets.Today.push(c);
    else if (day >= yday) buckets.Yesterday.push(c);
    else buckets.Older.push(c);
  }
  return Object.entries(buckets)
    .filter(([, items]) => items.length)
    .map(([label, items]) => ({ label, items }));
}

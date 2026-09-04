import { apiFetch } from "./http";

export type MediaKind = "image" | "video";

export interface MediaBackend {
  id: string;
  label: string;
  ready: boolean;
  default?: boolean;
}

export interface VideoPreset {
  id: string;
  label: string;
  width: number;
  height: number;
  frames: number;
  steps: number;
  fps: number;
  clip_s: number;
  typical_wall_s: number;
  typical_note: string;
  hint: string;
  recommended: boolean;
}

export interface MediaJob {
  id: string;
  kind: MediaKind;
  backend: string;
  status: string;
  prompt: string;
  params: Record<string, unknown>;
  output_url: string | null;
  error: string | null;
  metrics: Record<string, unknown>;
  created_at: number;
  updated_at: number;
  started_at: number | null;
  finished_at: number | null;
}

export async function fetchBackends(): Promise<{
  image: MediaBackend[];
  video: MediaBackend[];
  video_presets?: VideoPreset[];
}> {
  const r = await apiFetch("/generate/backends");
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function createJob(body: {
  kind: MediaKind;
  prompt: string;
  backend?: string;
  width?: number;
  height?: number;
  steps?: number;
  seed?: number;
  frames?: number;
  fps?: number;
  preset?: string;
  output_resolution?: string;
}): Promise<MediaJob> {
  const r = await apiFetch("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getJob(id: string): Promise<MediaJob> {
  const r = await apiFetch(`/generate/${id}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function cancelJob(id: string): Promise<MediaJob> {
  const r = await apiFetch(`/generate/${id}/cancel`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function listJobs(): Promise<MediaJob[]> {
  const r = await apiFetch("/generate");
  if (!r.ok) throw new Error(await r.text());
  const body = await r.json();
  return body.data || [];
}

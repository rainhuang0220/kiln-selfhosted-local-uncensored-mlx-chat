import { useEffect, useState } from "react";
import {
  cancelJob,
  createJob,
  fetchBackends,
  getJob,
  listJobs,
  type MediaBackend,
  type MediaJob,
  type MediaKind,
  type VideoPreset,
} from "./api/generate";
import { useChatStore } from "./stores/chat-store";

const IMAGE_PRESET = { width: 1024, height: 1024, steps: 9 };

const FALLBACK_VIDEO: Record<string, VideoPreset> = {
  fast: {
    id: "fast",
    label: "Fast",
    width: 832,
    height: 480,
    frames: 17,
    steps: 8,
    fps: 16,
    clip_s: 1.1,
    typical_wall_s: 230,
    typical_note: "Typically about 3–4 minutes on M4 24GB.",
    hint: "Fewer denoise steps. Faster; slightly softer motion.",
    recommended: false,
  },
  standard: {
    id: "standard",
    label: "Standard",
    width: 832,
    height: 480,
    frames: 17,
    steps: 10,
    fps: 16,
    clip_s: 1.1,
    typical_wall_s: 210,
    typical_note: "Typically about 3–4 minutes on M4 24GB.",
    hint: "Default quality. T5 bfloat16 + TeaCache.",
    recommended: true,
  },
  long: {
    id: "long",
    label: "Long",
    width: 832,
    height: 480,
    frames: 33,
    steps: 10,
    fps: 16,
    clip_s: 2.1,
    typical_wall_s: 585,
    typical_note: "Typically about 8–12 minutes on M4 24GB.",
    hint: "About 2 seconds of video. Noticeably slower; chat parks for the job.",
    recommended: false,
  },
};

const STATUS_LABEL: Record<string, string> = {
  queued: "Waiting",
  parking_chat: "Preparing",
  loading: "Preparing",
  generating: "Generating",
  decoding: "Decoding",
  exporting: "Finishing",
  restoring_chat: "Restoring chat",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
  interrupted: "interrupted",
};

const ACTIVE = new Set([
  "queued",
  "parking_chat",
  "loading",
  "generating",
  "decoding",
  "exporting",
  "restoring_chat",
]);

function elapsedLabel(job: MediaJob): string | null {
  const start = job.started_at || job.created_at;
  if (!start) return null;
  const end = job.finished_at || Date.now();
  const s = Math.max(0, Math.round((end - start) / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m > 0 ? `${m}m ${r}s elapsed` : `${r}s elapsed`;
}

export function GenerateStudio() {
  const loadHealth = useChatStore((s) => s.loadHealth);
  const [kind, setKind] = useState<MediaKind>("image");
  const [prompt, setPrompt] = useState("");
  const [seed, setSeed] = useState(42);
  const [width, setWidth] = useState(1024);
  const [height, setHeight] = useState(1024);
  const [steps, setSteps] = useState(9);
  const [frames, setFrames] = useState(17);
  const [videoPreset, setVideoPreset] = useState("standard");
  const [output720, setOutput720] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [presets, setPresets] = useState<VideoPreset[]>(Object.values(FALLBACK_VIDEO));
  const [backends, setBackends] = useState<{ image: MediaBackend[]; video: MediaBackend[] }>({
    image: [],
    video: [],
  });
  const [backend, setBackend] = useState<string>("");
  const [job, setJob] = useState<MediaJob | null>(null);
  const [history, setHistory] = useState<MediaJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    void fetchBackends()
      .then((b) => {
        setBackends(b);
        if (b.video_presets && b.video_presets.length) setPresets(b.video_presets);
        const def = (kind === "image" ? b.image : b.video).find((x) => x.default) || (kind === "image" ? b.image[0] : b.video[0]);
        if (def) setBackend(def.id);
      })
      .catch((e) => setError(String(e)));
    void listJobs().then(setHistory).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (kind === "image") {
      setWidth(IMAGE_PRESET.width);
      setHeight(IMAGE_PRESET.height);
      setSteps(IMAGE_PRESET.steps);
    } else {
      const p = presets.find((x) => x.id === videoPreset) || FALLBACK_VIDEO.standard;
      setWidth(p.width);
      setHeight(p.height);
      setSteps(p.steps);
      setFrames(p.frames);
    }
    const list = kind === "image" ? backends.image : backends.video;
    const def = list.find((x) => x.default) || list[0];
    if (def) setBackend(def.id);
  }, [kind, backends, videoPreset, presets]);

  const running = Boolean(job && ACTIVE.has(job.status));

  useEffect(() => {
    if (!job || !ACTIVE.has(job.status)) return;
    const t = window.setInterval(() => {
      void getJob(job.id)
        .then((j) => {
          setJob(j);
          if (!ACTIVE.has(j.status)) {
            void listJobs().then(setHistory);
            void loadHealth();
          }
        })
        .catch((e) => setError(String(e)));
      void loadHealth();
      setNow(Date.now());
    }, 1200);
    return () => window.clearInterval(t);
  }, [job?.id, job?.status, loadHealth]);

  const currentPreset = presets.find((p) => p.id === videoPreset) || FALLBACK_VIDEO.standard;

  return (
    <div className="gen-studio">
      <div className="gen-mode" role="tablist" aria-label="Generate kind">
        {(["image", "video"] as const).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={kind === k}
            className={kind === k ? "on" : ""}
            onClick={() => setKind(k)}
            disabled={running}
          >
            {k === "image" ? "Image" : "Video"}
          </button>
        ))}
      </div>
      <p className="gen-lede">
        {kind === "image"
          ? "Text-to-image on this Mac. Chat stays on the 9B worker; the image worker loads only for the job."
          : "Text-to-video on this Mac. Image and video jobs run one at a time. Chat parks during video, then resumes automatically."}
      </p>
      {kind === "video" ? (
        <div className="gen-mode" role="tablist" aria-label="Video length preset">
          {presets.map((p) => (
            <button
              key={p.id}
              type="button"
              role="tab"
              aria-selected={videoPreset === p.id}
              className={videoPreset === p.id ? "on" : ""}
              disabled={running}
              onClick={() => setVideoPreset(p.id)}
            >
              {p.label}
              {p.recommended ? " · Recommended" : ""}
            </button>
          ))}
        </div>
      ) : null}
      {kind === "video" ? (
        <p className="gen-lede">
          {currentPreset.width}×{currentPreset.height} · {currentPreset.frames} frames · {currentPreset.steps} steps · ~{currentPreset.clip_s}s clip.
          {" "}
          {currentPreset.hint} {currentPreset.typical_note}
        </p>
      ) : null}
      <textarea
        className="gen-prompt"
        rows={5}
        value={prompt}
        placeholder={kind === "image" ? "Describe the still." : "Describe the shot, motion, and camera."}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <div className="gen-bar">
        <select value={backend} onChange={(e) => setBackend(e.target.value)} disabled={running}>
          {(kind === "image" ? backends.image : backends.video).map((b) => (
            <option key={b.id} value={b.id} disabled={!b.ready}>
              {b.label}
              {b.ready ? "" : " (weights missing)"}
            </option>
          ))}
        </select>
        <button className="btn ghost" type="button" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? "Hide settings" : "Advanced"}
        </button>
        {running ? (
          <button
            className="btn ghost"
            type="button"
            disabled={busy}
            onClick={async () => {
              if (!job) return;
              setBusy(true);
              try {
                const j = await cancelJob(job.id);
                setJob(j);
                void loadHealth();
              } catch (e) {
                setError(String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Cancel
          </button>
        ) : (
          <button
            className="btn primary"
            disabled={busy || !prompt.trim()}
            onClick={async () => {
              setError(null);
              setBusy(true);
              try {
                const created = await createJob({
                  kind,
                  prompt: prompt.trim(),
                  backend,
                  width,
                  height,
                  steps,
                  seed,
                  ...(kind === "video"
                    ? {
                        frames,
                        preset: videoPreset,
                        output_resolution: output720 ? "720p" : "native",
                      }
                    : {}),
                });
                setJob(created);
                void loadHealth();
              } catch (e) {
                setError(String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Generate
          </button>
        )}
      </div>
      {advanced ? (
        <div className="gen-adv">
          <label>
            width
            <input type="number" value={width} min={256} max={2048} step={64} onChange={(e) => setWidth(Number(e.target.value))} />
          </label>
          <label>
            height
            <input type="number" value={height} min={256} max={2048} step={64} onChange={(e) => setHeight(Number(e.target.value))} />
          </label>
          <label>
            steps
            <input type="number" value={steps} min={1} max={80} onChange={(e) => setSteps(Number(e.target.value))} />
          </label>
          <label>
            seed
            <input type="number" value={seed} min={0} onChange={(e) => setSeed(Number(e.target.value))} />
          </label>
          {kind === "video" ? (
            <>
              <label>
                frames
                <input type="number" value={frames} min={17} max={33} step={4} onChange={(e) => setFrames(Number(e.target.value))} />
              </label>
              <label className="gen-check">
                <input type="checkbox" checked={output720} onChange={(e) => setOutput720(e.target.checked)} />
                Output 720p (ffmpeg scale after 480p generation, not native 720p)
              </label>
            </>
          ) : null}
        </div>
      ) : null}
      {error ? <div className="banner" role="alert">{error}</div> : null}
      {job ? (
        <div className="gen-job">
          <div className="gen-status">
            <span className={job.status === "failed" || job.status === "interrupted" ? "dot" : "dot on"} />
            {STATUS_LABEL[job.status] || job.status}
            {job.metrics?.steps != null && ACTIVE.has(job.status) && job.status === "generating" ? (
              <span> · {String(job.metrics.steps)} steps</span>
            ) : null}
            {elapsedLabel({ ...job, finished_at: job.finished_at || now }) ? (
              <span> · {elapsedLabel({ ...job, finished_at: job.finished_at || now })}</span>
            ) : null}
            {job.metrics?.wall_s != null ? <span> · {Number(job.metrics.wall_s).toFixed(1)}s</span> : null}
          </div>
          {kind === "video" && ACTIVE.has(job.status) ? (
            <p className="gen-lede">{currentPreset.typical_note} No live countdown — wall time varies with thermal and memory pressure.</p>
          ) : null}
          {job.error ? <div className="banner">{job.error}</div> : null}
          {job.status === "done" && job.output_url && job.kind === "image" ? (
            <>
              <img className="gen-out" src={job.output_url} alt="" />
              <a className="btn ghost" href={job.output_url} download>Download</a>
            </>
          ) : null}
          {job.status === "done" && job.output_url && job.kind === "video" ? (
            <>
              <video className="gen-out" src={job.output_url} controls />
              <a className="btn ghost" href={job.output_url} download>Download</a>
            </>
          ) : null}
        </div>
      ) : null}
      {history.length > 0 ? (
        <div className="gen-hist">
          <h3>Recent</h3>
          {history.slice(0, 8).map((h) => (
            <button key={h.id} className="gen-hist-item" onClick={() => setJob(h)}>
              <strong>{h.kind}</strong> {h.prompt.slice(0, 72)}
              <span>{STATUS_LABEL[h.status] || h.status}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Download,
  ExternalLink,
  LoaderCircle,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useChatStore } from "../stores/chat-store";

function compact(n: number) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n || 0);
}

export function ModelWorkbench({ open, onClose }: { open: boolean; onClose: () => void }) {
  const localModels = useChatStore((s) => s.localModels);
  const activeModelId = useChatStore((s) => s.activeModelId);
  const modelCatalog = useChatStore((s) => s.modelCatalog);
  const modelJobs = useChatStore((s) => s.modelJobs);
  const loadModels = useChatStore((s) => s.loadModels);
  const loadModelJobs = useChatStore((s) => s.loadModelJobs);
  const searchModelCatalog = useChatStore((s) => s.searchModelCatalog);
  const queueModelDownload = useChatStore((s) => s.queueModelDownload);
  const activateModel = useChatStore((s) => s.activateModel);
  const [query, setQuery] = useState("qwen3.5");
  const [mlxOnly, setMlxOnly] = useState(false);

  useEffect(() => {
    if (!open) return;
    void Promise.all([loadModels(), loadModelJobs(), searchModelCatalog(query, mlxOnly)]);
  }, [open]);

  useEffect(() => {
    if (!open || !modelJobs.some((job) => job.status === "queued" || job.status === "downloading")) return;
    const interval = window.setInterval(() => {
      void Promise.all([loadModelJobs(), loadModels()]);
    }, 1800);
    return () => window.clearInterval(interval);
  }, [open, modelJobs]);

  const running = useMemo(
    () => new Set(modelJobs.filter((job) => job.status === "queued" || job.status === "downloading").map((job) => job.repo_id)),
    [modelJobs],
  );

  if (!open) return null;
  return (
    <div className="workbench-layer" role="presentation" onMouseDown={onClose}>
      <section
        className="model-workbench"
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-workbench-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="workbench-head">
          <div>
            <p className="eyebrow">MODEL WORKBENCH</p>
            <h2 id="model-workbench-title">Choose what burns.</h2>
            <p>检索 Hugging Face，下载到本机模型库，再一键切换到 Kiln。</p>
          </div>
          <button className="icon-btn" type="button" onClick={onClose} aria-label="Close model workbench">
            <X size={17} strokeWidth={1.8} />
          </button>
        </header>

        <div className="workbench-grid">
          <section className="model-library" aria-labelledby="library-title">
            <div className="section-title">
              <div>
                <p className="eyebrow">ON THIS MACHINE</p>
                <h3 id="library-title">Your models</h3>
              </div>
              <span>{localModels.length}</span>
            </div>
            <div className="library-list">
              {localModels.map((model) => {
                const active = model.id === activeModelId || model.status === "active";
                return (
                  <article className={active ? "model-card active" : "model-card"} key={model.id}>
                    <div className="model-card-top">
                      <div className="model-mark" aria-hidden="true">{model.name.slice(0, 1).toUpperCase()}</div>
                      <div>
                        <h4>{model.name}</h4>
                        <p>{model.repo_id || (model.source === "configured" ? "configured local profile" : "local checkpoint")}</p>
                      </div>
                    </div>
                    <div className="model-card-foot">
                      {active ? (
                        <span className="active-label"><Check size={13} /> active</span>
                      ) : (
                        <button className="text-action" type="button" onClick={() => void activateModel(model.id)}>
                          Use this model
                        </button>
                      )}
                      {model.revision ? <code>{model.revision.slice(0, 8)}</code> : null}
                    </div>
                  </article>
                );
              })}
            </div>
            {modelJobs.length ? (
              <div className="jobs-list" aria-live="polite">
                {modelJobs.slice(0, 4).map((job) => (
                  <div className={job.status === "error" ? "job error" : "job"} key={job.id}>
                    {job.status === "queued" || job.status === "downloading" ? <LoaderCircle size={14} className="spin" /> : <Download size={14} />}
                    <span>{job.repo_id}</span>
                    <b>{job.status === "downloading" ? "downloading" : job.status}</b>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <section className="hub-catalog" aria-labelledby="catalog-title">
            <div className="section-title catalog-title">
              <div>
                <p className="eyebrow">HUGGING FACE HUB</p>
                <h3 id="catalog-title">Find an open model</h3>
              </div>
              <a href="https://huggingface.co/models" target="_blank" rel="noreferrer" aria-label="Open Hugging Face models">
                <ExternalLink size={16} />
              </a>
            </div>
            <form
              className="model-search"
              onSubmit={(event) => {
                event.preventDefault();
                void searchModelCatalog(query, mlxOnly);
              }}
            >
              <Search size={17} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search models…" />
              <button className="btn primary" type="submit">Search</button>
            </form>
            <label className="mlx-filter">
              <input type="checkbox" checked={mlxOnly} onChange={(event) => setMlxOnly(event.target.checked)} />
              <SlidersHorizontal size={14} />
              MLX-ready only
            </label>
            <div className="catalog-list">
              {modelCatalog.map((model) => {
                const busy = running.has(model.id);
                return (
                  <article className="catalog-row" key={model.id}>
                    <div className="catalog-copy">
                      <h4>{model.name}</h4>
                      <p>{model.id}</p>
                      <div className="catalog-meta">
                        <span>↓ {compact(model.downloads)}</span>
                        <span>♡ {compact(model.likes)}</span>
                        {model.pipeline_tag ? <span>{model.pipeline_tag}</span> : null}
                        <span className={model.mlx_compatible ? "tag mlx-ready" : "tag"}>
                          {model.mlx_compatible ? "MLX-ready" : "conversion needed"}
                        </span>
                      </div>
                    </div>
                    <div className="catalog-actions">
                      <a href={`https://huggingface.co/${model.id}`} target="_blank" rel="noreferrer" aria-label={`Open ${model.id} on Hugging Face`}>
                        <ExternalLink size={15} />
                      </a>
                      <button className="btn ghost" type="button" disabled={busy || !model.mlx_compatible} title={model.mlx_compatible ? "" : "Choose an MLX-ready model to install directly"} onClick={() => void queueModelDownload(model.id)}>
                        {busy ? <LoaderCircle size={15} className="spin" /> : <Download size={15} />}
                        Download
                      </button>
                      <button className="btn primary" type="button" disabled={busy || !model.mlx_compatible} title={model.mlx_compatible ? "" : "This repository needs MLX conversion before Kiln can run it"} onClick={() => void queueModelDownload(model.id, true)}>
                        {busy ? "Queued" : model.mlx_compatible ? "Download + use" : "Needs MLX"}
                      </button>
                    </div>
                  </article>
                );
              })}
              {!modelCatalog.length ? <p className="catalog-empty">No models found. Try a broader search or disable the MLX filter.</p> : null}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}

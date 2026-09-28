import { useEffect, useRef, useState } from "react";
import { Check, Plus, Sparkles, Trash2, X } from "lucide-react";
import {
  emptyPresetPayload,
  getContextPreset,
  listContextPresets,
  previewContextPreset,
  saveContextPreset,
} from "../api/context-presets";
import { useChatStore } from "../stores/chat-store";
import type { ContextPresetPayload, ContextPresetRecord, SimpleCharacter } from "../types/context-preset";

function displaySlot(value: string): string {
  return value?.trim() ? value : "暂无";
}

interface EditorProps {
  payload: ContextPresetPayload;
  onChange: (value: ContextPresetPayload) => void;
}

export function PresetEditor({ payload, onChange }: EditorProps) {
  const patch = (value: Partial<ContextPresetPayload>) => onChange({ ...payload, ...value });
  const patchMe = (key: keyof ContextPresetPayload["me"], value: string) => {
    patch({ me: { ...payload.me, [key]: value } });
  };
  const patchCharacter = (index: number, value: Partial<SimpleCharacter>) => {
    patch({
      characters: payload.characters.map((item, at) => (at === index ? { ...item, ...value } : item)),
    });
  };
  const patchTimeline = (index: number, value: Partial<ContextPresetPayload["timeline"][number]>) => {
    patch({ timeline: payload.timeline.map((item, at) => at === index ? { ...item, ...value } : item) });
  };
  const moveTimeline = (index: number, direction: number) => {
    const next = [...payload.timeline];
    const to = index + direction;
    if (to < 0 || to >= next.length) return;
    [next[index], next[to]] = [next[to], next[index]];
    patch({ timeline: next.map((item, at) => ({ ...item, order: at + 1 })) });
  };

  return (
    <div className="preset-editor preset-editor-simple">
      <section className="preset-section" aria-labelledby="preset-scene-title">
        <div className="preset-section-head">
          <h3 id="preset-scene-title">当前场景</h3>
          <p>这一会话在哪里、正在发生什么。幻想素材不会出现在这里。</p>
        </div>
        <label className="preset-field wide">
          <textarea
            rows={3}
            value={payload.current_scene}
            onChange={(event) => patch({ current_scene: event.target.value })}
            placeholder="现在在哪里，正在发生什么？"
          />
        </label>
      </section>

      <section className="preset-section" aria-labelledby="preset-me-title">
        <div className="preset-section-head">
          <h3 id="preset-me-title">我</h3>
          <p>账号级身份与偏好。长文里没有时显示「暂无」。</p>
        </div>
        <div className="preset-fields">
          <label className="preset-field wide">
            <span>用户身份</span>
            <textarea rows={2} value={displaySlot(payload.me.identity) === "暂无" && !payload.me.identity ? "暂无" : payload.me.identity} onChange={(event) => patchMe("identity", event.target.value)} />
            {payload.me_identity_helper ? <span className="preset-field-hint">{payload.me_identity_helper}</span> : null}
          </label>
          <label className="preset-field wide">
            <span>现实背景</span>
            <textarea rows={2} value={payload.me.real_background || "暂无"} onChange={(event) => patchMe("real_background", event.target.value)} />
          </label>
          <label className="preset-field wide">
            <span>明确偏好</span>
            <textarea rows={2} value={payload.me.explicit_prefs || "暂无"} onChange={(event) => patchMe("explicit_prefs", event.target.value)} />
          </label>
        </div>
      </section>

      <section className="preset-section" aria-labelledby="preset-people-title">
        <div className="preset-section-head preset-subhead-row">
          <div>
            <h3 id="preset-people-title">人物</h3>
            <p>名称、身份，可选一件已绑定的事。</p>
          </div>
          <button
            type="button"
            className="btn ghost preset-small-action"
            onClick={() => patch({ characters: [...payload.characters, { name: "", identity: "", one_event: undefined }] })}
          >
            <Plus size={13} /> 添加
          </button>
        </div>
        <div className="preset-rows">
          {payload.characters.length === 0 ? <p className="preset-empty-row">暂无人物。粘贴长文解析，或手动添加短行。</p> : null}
          {payload.characters.map((person, index) => (
            <div className="preset-person-row preset-person-simple" key={person.id || index}>
              <div className="preset-row-grid">
                <label className="preset-field">
                  <span>名称</span>
                  <input value={person.name} onChange={(event) => patchCharacter(index, { name: event.target.value })} placeholder="称呼" />
                </label>
                <label className="preset-field">
                  <span>身份</span>
                  <input value={person.identity} onChange={(event) => patchCharacter(index, { identity: event.target.value })} placeholder="是谁" />
                </label>
                <label className="preset-field">
                  <span>一件事（可选）</span>
                  <input value={person.one_event || ""} onChange={(event) => patchCharacter(index, { one_event: event.target.value || undefined })} placeholder="可空" />
                </label>
                <button
                  type="button"
                  className="preset-remove"
                  aria-label={`移除人物 ${person.name || index + 1}`}
                  onClick={() => patch({ characters: payload.characters.filter((_, at) => at !== index) })}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="preset-section" aria-labelledby="preset-timeline-title">
        <div className="preset-section-head preset-subhead-row">
          <div>
            <h3 id="preset-timeline-title">已绑定事件</h3>
            <p>每条事件已挂到已知人物。点名该人物时才会召回对应回忆。</p>
          </div>
          <button type="button" className="btn ghost preset-small-action" onClick={() => patch({
            timeline: [...payload.timeline, {
              id: "manual-" + Date.now(),
              order: payload.timeline.length + 1,
              who: payload.characters[0]?.name ? [payload.characters[0].name] : [],
              summary: "", when: "未注明",
              chronology: "source_order", scope: "reference",
              evidence: "",
            }],
          })}><Plus size={13} /> 添加事件</button>
        </div>
        <div className="preset-rows">
          {payload.timeline.length === 0 ? <p className="preset-empty-row">暂无已绑定事件。解析长文后会显示有主语的事件。</p> : null}
          {payload.timeline.map((event, index) => (
            <div className="preset-person-row preset-timeline-row" key={event.id}>
              <div className="preset-timeline-heading">
                <strong>{(event.who[0] || "人物")} · {event.summary || "未填写事件"}</strong>
                <div className="preset-timeline-actions">
                  <button type="button" className="preset-small-icon" aria-label={"上移事件 " + (index + 1)} disabled={index === 0} onClick={() => moveTimeline(index, -1)}>↑</button>
                  <button type="button" className="preset-small-icon" aria-label={"下移事件 " + (index + 1)} disabled={index === payload.timeline.length - 1} onClick={() => moveTimeline(index, 1)}>↓</button>
                  <button type="button" className="preset-remove" aria-label={"移除事件 " + (index + 1)} onClick={() => patch({ timeline: payload.timeline.filter((_, at) => at !== index) })}><Trash2 size={15} /></button>
                </div>
              </div>
              <div className="preset-row-grid">
                <label className="preset-field"><span>涉及人物</span><input value={event.who.join("、")} onChange={(change) => {
                  const names = change.target.value.split(/[、,，]/).map((name) => name.trim()).filter(Boolean);
                  patchTimeline(index, { who: names });
                }} placeholder="人名" /></label>
                <label className="preset-field"><span>时间线索</span><input value={event.when} onChange={(change) => patchTimeline(index, { when: change.target.value })} /></label>
              </div>
              <label className="preset-field wide"><span>发生的事</span><textarea rows={2} value={event.summary} onChange={(change) => patchTimeline(index, { summary: change.target.value })} /></label>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function ContextPresetStudio({ onClose, onStartNewChat }: { onClose: () => void; onStartNewChat: () => void }) {
  const selectedId = useChatStore((state) => state.contextPresetId);
  const activeId = useChatStore((state) => state.activeId);
  const setContextPreset = useChatStore((state) => state.setContextPreset);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [records, setRecords] = useState<ContextPresetRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"preview" | "save" | "load" | null>(null);
  const [recordId, setRecordId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [payload, setPayload] = useState<ContextPresetPayload>(emptyPresetPayload);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    void listContextPresets().then((items) => {
      if (current) setRecords(items);
    }).catch((reason: unknown) => {
      if (current) setError(`无法读取预设：${(reason as Error).message}`);
    }).finally(() => {
      if (current) setLoading(false);
    });
    headingRef.current?.focus();
    return () => { current = false; };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function startBlank() {
    setRecordId(null);
    setTitle("");
    setSourceText("");
    setPayload(emptyPresetPayload());
    setError(null);
    setNotice("已开始新预设。");
  }

  async function openRecord(id: string) {
    setBusy("load");
    setError(null);
    setNotice(null);
    try {
      const item = await getContextPreset(id);
      setRecordId(item.id);
      setTitle(item.title);
      setPayload(item.payload);
      setSourceText(item.source_text || "");
    } catch (reason) {
      setError(`无法打开预设：${(reason as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function analyze() {
    if (!sourceText.trim()) {
      setError("请先粘贴要解析的长文本。");
      return;
    }
    setBusy("preview");
    setError(null);
    setNotice(null);
    try {
      const draft = await previewContextPreset(sourceText);
      setPayload(draft);
      setNotice(
        draft.characters.length
          ? `已拆出 ${draft.characters.length} 个人物和 ${draft.timeline.length} 条已绑定事件。`
          : "未识别出人物行。可手改当前场景与「我」，或手动添加人物。",
      );
    } catch (reason) {
      setError(`解析失败：${(reason as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    if (!title.trim()) {
      setError("请为预设填写一个名称。");
      return;
    }
    if (!payload.current_scene.trim()) {
      setError("请填写当前场景。");
      return;
    }
    if (payload.current_scene.length > 1600) {
      setError("当前场景过长。请缩短到场景本身，不要粘贴整段幻想。");
      return;
    }
    setBusy("save");
    setError(null);
    setNotice(null);
    try {
      const item = await saveContextPreset(
        {
          title: title.trim(),
          payload,
          source_text: sourceText,
          conversation_id: activeId || undefined,
        },
        recordId || undefined,
      );
      setRecords((current) => [item, ...current.filter((old) => old.id !== item.id)]);
      setRecordId(item.id);
      setTitle(item.title);
      setPayload(item.payload);
      setContextPreset(item.id, item.title);
      setNotice("已保存到账号人物库，并选用为新会话预设。");
    } catch (reason) {
      setError(`保存失败：${(reason as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="preset-layer" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="preset-workspace" role="dialog" aria-modal="true" aria-labelledby="preset-workspace-title">
        <header className="preset-workspace-head">
          <div>
            <p className="eyebrow">KILN / 人物预设</p>
            <h2 id="preset-workspace-title" tabIndex={-1} ref={headingRef}>人物预设</h2>
            <p>粘贴长文，拆成当前场景、人物关系与可核对原文的事件顺序。</p>
          </div>
          <button type="button" className="icon-btn" aria-label="关闭人物预设" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="preset-workspace-body">
          <aside className="preset-source">
            <div className="preset-source-top">
              <span className="preset-index">LIBRARY</span>
              <button type="button" className="btn ghost preset-small-action" onClick={startBlank}><Plus size={13} /> 新建</button>
            </div>
            <h3>已保存</h3>
            <div className="preset-library" aria-label="已保存的预设">
              {loading ? <p className="preset-muted">正在读取…</p> : null}
              {!loading && records.length === 0 ? <p className="preset-muted">暂无。先粘贴长文解析。</p> : null}
              {records.map((item) => (
                <div className={item.id === recordId ? "preset-library-item editing" : "preset-library-item"} key={item.id}>
                  <button type="button" className="preset-library-open" onClick={() => void openRecord(item.id)} disabled={busy !== null}>
                    <strong>{item.title || "未命名预设"}</strong>
                    <span>{item.payload.characters[0]?.name || item.payload.current_scene || "未填写"}</span>
                  </button>
                  <button
                    type="button"
                    className={selectedId === item.id ? "preset-use selected" : "preset-use"}
                    aria-label={`选用预设 ${item.title}`}
                    onClick={() => { setContextPreset(item.id, item.title); setNotice("已选用，新会话生效。"); }}
                  >
                    {selectedId === item.id ? <Check size={15} /> : <Plus size={15} />}
                  </button>
                </div>
              ))}
            </div>
            <div className="preset-source-input">
              <span className="preset-index">SOURCE</span>
              <label htmlFor="preset-source-text">粘贴长文本</label>
              <p>一框到底。先定位人物和事件，再由本机小模型补足语义。</p>
              <textarea
                id="preset-source-text"
                value={sourceText}
                onChange={(event) => setSourceText(event.target.value)}
                rows={12}
                placeholder="例如：你是……我是……以下内容是我的信息背景和性瘾参考……"
              />
              <div className="preset-source-actions">
                <span>{sourceText.length.toLocaleString()} 字</span>
                <button type="button" className="btn" onClick={() => void analyze()} disabled={busy !== null || !sourceText.trim()}>
                  <Sparkles size={14} /> {busy === "preview" ? "正在拆人物…" : "解析并预览"}
                </button>
              </div>
            </div>
          </aside>
          <div className="preset-structured">
            <div className="preset-structured-head">
              <div><span className="preset-index">PREVIEW</span><h3>预览与编辑</h3></div>
              <span className="preset-version">{recordId ? "已保存" : "新草稿"}</span>
            </div>
            <label className="preset-field preset-title-field"><span>预设名称</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：风俗店 · 第一次" /></label>
            <PresetEditor payload={payload} onChange={setPayload} />
          </div>
        </div>
        <footer className="preset-workspace-foot">
          <div className="preset-foot-copy">
            <strong>人物存账号，场景属会话</strong>
            <span>保存写入人物库；当前场景可绑定本会话。幻想素材只在内部。</span>
            {notice ? <span role="status" className="preset-notice">{notice}</span> : null}
            {error ? <span role="alert" className="preset-error">{error}</span> : null}
          </div>
          <div className="preset-foot-actions">
            {selectedId ? <button type="button" className="btn ghost" onClick={() => { setContextPreset(null); setNotice("已取消选用。"); }}>取消选用</button> : null}
            {selectedId ? <button type="button" className="btn ghost" onClick={onStartNewChat}>开始新会话</button> : null}
            <button type="button" className="btn primary" onClick={() => void save()} disabled={busy !== null}>
              {busy === "save" ? "保存中…" : recordId ? "更新" : "保存"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

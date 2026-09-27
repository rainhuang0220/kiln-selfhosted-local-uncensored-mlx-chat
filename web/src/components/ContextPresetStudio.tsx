import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Check, Plus, Sparkles, Trash2, X } from "lucide-react";
import {
  emptyPresetPayload,
  getContextPreset,
  listContextPresets,
  previewContextPreset,
  saveContextPreset,
} from "../api/context-presets";
import { useChatStore } from "../stores/chat-store";
import type { ContextPresetPayload, ContextPresetRecord } from "../types/context-preset";

type CharacterField = Exclude<keyof ContextPresetPayload["active_character"], "immutable_json" | "scenario">;

function lines(text: string): string[] {
  return text.split("\n").map((line) => line.trim()).filter(Boolean);
}

function facts(text: string): string[] {
  return text.split(/[\n,，]/).map((entry) => entry.trim()).filter(Boolean);
}

function ArrayTextArea({ values, onChange, rows, splitCommas = false, placeholder }: {
  values: string[];
  onChange: (values: string[]) => void;
  rows: number;
  splitCommas?: boolean;
  placeholder?: string;
}) {
  const [raw, setRaw] = useState(() => values.join("\n"));
  const focused = useRef(false);
  useEffect(() => {
    if (!focused.current) setRaw(values.join("\n"));
  }, [values]);
  return (
    <textarea
      rows={rows}
      value={raw}
      placeholder={placeholder}
      onFocus={() => { focused.current = true; }}
      onBlur={() => { focused.current = false; setRaw(values.join("\n")); }}
      onChange={(event) => {
        const next = event.target.value;
        setRaw(next);
        onChange(splitCommas ? facts(next) : lines(next));
      }}
    />
  );
}

interface EditorProps {
  payload: ContextPresetPayload;
  onChange: (value: ContextPresetPayload) => void;
}

export function PresetEditor({ payload, onChange }: EditorProps) {
  const patch = (value: Partial<ContextPresetPayload>) => onChange({ ...payload, ...value });
  const patchCharacter = (key: CharacterField, value: string) => {
    patch({ active_character: { ...payload.active_character, [key]: value } });
  };
  const patchCharacterRow = (index: number, value: Partial<ContextPresetPayload["characters"][number]>) => {
    patch({ characters: payload.characters.map((item, at) => at === index ? { ...item, ...value } : item) });
  };
  const patchEvent = (index: number, value: Partial<ContextPresetPayload["references"]["events"][number]>) => {
    patch({ references: {
      ...payload.references,
      events: payload.references.events.map((item, at) => at === index ? { ...item, ...value } : item),
    } });
  };

  return (
    <div className="preset-editor">
      <section className="preset-section preset-current" aria-labelledby="preset-current-title">
        <div className="preset-section-head">
          <span className="preset-index">01 / CURRENT</span>
          <h3 id="preset-current-title">当前对话锚点</h3>
          <p>这部分是此刻要扮演的关系和场景。请把幻想或往事放到下面的参考区。</p>
        </div>
        <div className="preset-fields">
          <label className="preset-field wide">
            <span>当前场景</span>
            <textarea rows={3} value={payload.active_scene} onChange={(event) => patch({ active_scene: event.target.value })} placeholder="现在在哪里，正在发生什么？" />
          </label>
          <label className="preset-field wide">
            <span>用户身份</span>
            <textarea rows={2} value={payload.user_persona} onChange={(event) => patch({ user_persona: event.target.value })} placeholder="用户在当前场景中的身份与背景" />
          </label>
          <label className="preset-field wide">
            <span>已确认的现实背景 · 逗号或换行分隔</span>
            <ArrayTextArea rows={3} values={payload.background_facts} onChange={(values) => patch({ background_facts: values })} splitCommas placeholder="仅填写明确陈述的事实，不把幻想当成现实" />
          </label>
          <label className="preset-field wide">
            <span>明确偏好 · 逗号或换行分隔</span>
            <ArrayTextArea rows={3} values={payload.preferences} onChange={(values) => patch({ preferences: values })} splitCommas placeholder="明确提出、可用于当前对话的偏好" />
          </label>
        </div>
        <div className="preset-subhead">
          <h4>当前扮演人物</h4>
          <p>对话应回到这个人物，而非自动进入参考段落里的情节。</p>
        </div>
        <div className="preset-fields">
          <label className="preset-field">
            <span>名称</span>
            <input value={payload.active_character.name} onChange={(event) => patchCharacter("name", event.target.value)} placeholder="称呼或名字" />
          </label>
          <label className="preset-field">
            <span>与用户的关系</span>
            <input value={payload.active_character.relationship_to_user} onChange={(event) => patchCharacter("relationship_to_user", event.target.value)} placeholder="例如：初次见面" />
          </label>
          <label className="preset-field wide">
            <span>人物描述</span>
            <textarea rows={2} value={payload.active_character.description} onChange={(event) => patchCharacter("description", event.target.value)} />
          </label>
          <label className="preset-field">
            <span>性格</span>
            <textarea rows={2} value={payload.active_character.personality} onChange={(event) => patchCharacter("personality", event.target.value)} />
          </label>
          <label className="preset-field">
            <span>说话风格</span>
            <textarea rows={2} value={payload.active_character.speech_style} onChange={(event) => patchCharacter("speech_style", event.target.value)} />
          </label>
          <label className="preset-field">
            <span>边界 / 禁忌</span>
            <textarea rows={2} value={payload.active_character.taboos} onChange={(event) => patchCharacter("taboos", event.target.value)} />
          </label>
          <label className="preset-field">
            <span>不可改动的设定 · 每行一条</span>
            <ArrayTextArea rows={2} values={payload.active_character.immutable_json} onChange={(values) => patch({ active_character: { ...payload.active_character, immutable_json: values } })} />
          </label>
        </div>
      </section>

      <section className="preset-section preset-reference" aria-labelledby="preset-reference-title">
        <div className="preset-section-head">
          <span className="preset-index">02 / REFERENCE</span>
          <h3 id="preset-reference-title">参考人物与素材</h3>
          <p>人物和事件仅作参考，不等于当前正在发生的剧情。上方确认的事实与明确偏好属于活跃资料。</p>
        </div>
        <div className="preset-subhead preset-subhead-row">
          <div>
            <h4>其他人物</h4>
            <p>上方是主要扮演人物。这里可指定额外在场人物，或保存仅供查阅的参考人物。</p>
          </div>
          <button type="button" className="btn ghost preset-small-action" onClick={() => patch({ characters: [...payload.characters, { name: "", role: "", scope: "reference", notes: "" }] })}>
            <Plus size={13} /> 添加人物
          </button>
        </div>
        <div className="preset-rows">
          {payload.characters.length === 0 ? <p className="preset-empty-row">尚未添加其他人物。当前扮演人物可在上方单独编辑。</p> : null}
          {payload.characters.map((person, index) => (
            <div className="preset-person-row" key={index}>
              <div className="preset-row-grid">
                <label className="preset-field"><span>名称</span><input value={person.name} onChange={(event) => patchCharacterRow(index, { name: event.target.value })} /></label>
                <label className="preset-field"><span>角色</span><input value={person.role} onChange={(event) => patchCharacterRow(index, { role: event.target.value })} /></label>
                <label className="preset-field"><span>作用域</span>
                  <select value={person.scope} onChange={(event) => patchCharacterRow(index, { scope: event.target.value as "active" | "reference" })}>
                    <option value="active">当前人物</option>
                    <option value="reference">参考人物</option>
                  </select>
                </label>
                <button type="button" className="preset-remove" aria-label={`移除人物 ${person.name || index + 1}`} onClick={() => patch({ characters: payload.characters.filter((_, at) => at !== index) })}><Trash2 size={15} /></button>
              </div>
              <label className="preset-field"><span>备注</span><textarea rows={2} value={person.notes} onChange={(event) => patchCharacterRow(index, { notes: event.target.value })} /></label>
            </div>
          ))}
        </div>
        <div className="preset-subhead preset-subhead-row">
          <div><h4>参考事件</h4><p>记住发生过什么，不把它重演为当前场景。</p></div>
          <button type="button" className="btn ghost preset-small-action" onClick={() => patch({ references: { ...payload.references, events: [...payload.references.events, { label: "", who: "", gist: "" }] } })}><Plus size={13} /> 添加事件</button>
        </div>
        <div className="preset-rows">
          {payload.references.events.map((event, index) => (
            <div className="preset-person-row" key={index}>
              <div className="preset-row-grid">
                <label className="preset-field"><span>标题</span><input value={event.label} onChange={(change) => patchEvent(index, { label: change.target.value })} /></label>
                <label className="preset-field"><span>涉及人物</span><input value={event.who} onChange={(change) => patchEvent(index, { who: change.target.value })} /></label>
                <button type="button" className="preset-remove" aria-label={`移除参考事件 ${event.label || index + 1}`} onClick={() => patch({ references: { ...payload.references, events: payload.references.events.filter((_, at) => at !== index) } })}><Trash2 size={15} /></button>
              </div>
              <label className="preset-field"><span>简述</span><textarea rows={2} value={event.gist} onChange={(change) => patchEvent(index, { gist: change.target.value })} /></label>
            </div>
          ))}
        </div>
        <div className="preset-fields preset-tail-fields">
          <label className="preset-field"><span>表达语域 · 每行一条</span><ArrayTextArea rows={3} values={payload.references.register} onChange={(values) => patch({ references: { ...payload.references, register: values } })} /></label>
          <label className="preset-field"><span>叙述技巧 · 每行一条</span><ArrayTextArea rows={3} values={payload.references.techniques} onChange={(values) => patch({ references: { ...payload.references, techniques: values } })} /></label>
          <label className="preset-field wide"><span>尚不确定 · 每行一条</span><ArrayTextArea rows={2} values={payload.uncertain} onChange={(values) => patch({ uncertain: values })} /></label>
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
  const [deepAnalysis, setDeepAnalysis] = useState(false);
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
    setNotice("已开始新预设；可粘贴长文解析，也可直接编辑结构化信息。");
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
      const draft = await previewContextPreset(sourceText, { deep: deepAnalysis });
      setPayload(draft);
      setNotice(draft.uncertain.some((item) => item.includes("没有明确的参考边界"))
        ? "长文本未识别出参考边界。请先核对并缩短当前场景，再保存。"
        : "解析完成。请核对当前场景、人物作用域与参考素材，再保存。");
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
    if (!payload.active_scene.trim() || !payload.active_character.name.trim()) {
      setError("请填写当前场景和主要扮演人物的名称。");
      return;
    }
    if (payload.active_scene.length > 1600) {
      setError("当前场景超过 1600 字。请检查参考边界，把参考资料移到下方。");
      return;
    }
    setBusy("save");
    setError(null);
    setNotice(null);
    try {
      const item = await saveContextPreset({ title: title.trim(), payload, source_text: sourceText }, recordId || undefined);
      setRecords((current) => [item, ...current.filter((old) => old.id !== item.id)]);
      setRecordId(item.id);
      setTitle(item.title);
      setPayload(item.payload);
      setContextPreset(item.id, item.title);
      setNotice("已保存并选中。仅在新会话开始时生效；当前会话保持原有设定。");
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
            <p className="eyebrow">KILN / CONTEXT STUDIO</p>
            <h2 id="preset-workspace-title" tabIndex={-1} ref={headingRef}>人物与场景预设</h2>
            <p>把长文本整理成可检查的当前设定与参考材料。保存后再选择用于新会话。</p>
          </div>
          <button type="button" className="icon-btn" aria-label="关闭人物预设" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="preset-workspace-body">
          <aside className="preset-source">
            <div className="preset-source-top">
              <span className="preset-index">LIBRARY</span>
              <button type="button" className="btn ghost preset-small-action" onClick={startBlank}><Plus size={13} /> 新建</button>
            </div>
            <h3>已保存的预设</h3>
            <div className="preset-library" aria-label="已保存的预设">
              {loading ? <p className="preset-muted">正在读取…</p> : null}
              {!loading && records.length === 0 ? <p className="preset-muted">暂无预设。先从一段长文本开始，或直接编辑右侧。</p> : null}
              {records.map((item) => (
                <div className={item.id === recordId ? "preset-library-item editing" : "preset-library-item"} key={item.id}>
                  <button type="button" className="preset-library-open" onClick={() => void openRecord(item.id)} disabled={busy !== null}>
                    <strong>{item.title || "未命名预设"}</strong>
                    <span>{item.payload.active_character.name || item.payload.active_scene || "未填写场景"}</span>
                  </button>
                  <button type="button" className={selectedId === item.id ? "preset-use selected" : "preset-use"} aria-label={`选用预设 ${item.title}`} onClick={() => { setContextPreset(item.id, item.title); setNotice("已选用保存的版本，仅在新会话开始时生效。"); }}>
                    {selectedId === item.id ? <Check size={15} /> : <ArrowUpRight size={15} />}
                  </button>
                </div>
              ))}
            </div>
            <div className="preset-source-input">
              <span className="preset-index">SOURCE</span>
              <label htmlFor="preset-source-text">粘贴长文本</label>
              <p>可以混合现实人设、幻想、往事和偏好，最多 5 万字。解析结果只是草稿，右侧可逐项修正。</p>
              <textarea id="preset-source-text" value={sourceText} onChange={(event) => setSourceText(event.target.value)} rows={12} placeholder="例如：你是……我是……以下内容只是背景和幻想参考……" />
              <label className="preset-deep-option">
                <input type="checkbox" checked={deepAnalysis} onChange={(event) => setDeepAnalysis(event.target.checked)} />
                <span><strong>深度分析</strong><small>调用本机模型补充人物描述，并提出待确认的事实候选。超过 1.2 万字时使用规则预览。</small></span>
              </label>
              <div className="preset-source-actions">
                <span>{sourceText.length.toLocaleString()} 字</span>
                <button type="button" className="btn" onClick={() => void analyze()} disabled={busy !== null || !sourceText.trim()}><Sparkles size={14} /> {busy === "preview" ? "解析中…" : "解析并预览"}</button>
              </div>
            </div>
          </aside>
          <div className="preset-structured">
            <div className="preset-structured-head">
              <div><span className="preset-index">STRUCTURED DRAFT</span><h3>直接编辑结构化信息</h3></div>
              <span className="preset-version">{recordId ? "编辑已保存预设" : "新预设"}</span>
            </div>
            <label className="preset-field preset-title-field"><span>预设名称</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：茶室 · 第一次会面" /></label>
            <PresetEditor payload={payload} onChange={setPayload} />
          </div>
        </div>
        <footer className="preset-workspace-foot">
          <div className="preset-foot-copy">
            <strong>仅在新会话开始时生效</strong>
            <span>{activeId ? "当前会话不会切换；打开 New chat 后使用已选预设。" : "发送新会话的第一条消息时，将附上已选预设。"}</span>
            <span>活跃：当前场景、人物、确认事实与明确偏好。参考：其他人物和事件不自动入场。</span>
            {notice ? <span role="status" className="preset-notice">{notice}</span> : null}
            {error ? <span role="alert" className="preset-error">{error}</span> : null}
          </div>
          <div className="preset-foot-actions">
            {selectedId ? <button type="button" className="btn ghost" onClick={() => { setContextPreset(null); setNotice("已取消选用；下个新会话不使用人物预设。"); }}>取消选用</button> : null}
            {selectedId ? <button type="button" className="btn ghost" onClick={onStartNewChat}>开始新会话</button> : null}
            <button type="button" className="btn primary" onClick={() => void save()} disabled={busy !== null}>{busy === "save" ? "保存中…" : recordId ? "更新预设" : "保存预设"}</button>
          </div>
        </footer>
      </div>
    </div>
  );
}

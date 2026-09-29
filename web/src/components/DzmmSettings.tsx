import { useEffect, useState } from "react";
import { apiFetch } from "../api/http";
import { useChatStore } from "../stores/chat-store";

type ModelRow = {
  id: string; label: string; quality: string; speed: string;
  long_card: string; privacy: string; price: string; quota: string;
};
type CardRow = { id: string; name: string; description: string; tags?: string[] };

export function DzmmSettings() {
  const selected = useChatStore((s) => s.selectedChatModel);
  const select = useChatStore((s) => s.setSelectedChatModel);
  const activeLocalModel = useChatStore((s) => s.activeModelId);
  const selectedCard = useChatStore((s) => s.characterCardId);
  const selectCard = useChatStore((s) => s.setCharacterCardId);
  const [configured, setConfigured] = useState(false);
  const [token, setToken] = useState("");
  const [rows, setRows] = useState<ModelRow[]>([]);
  const [wallet, setWallet] = useState("未配置 Token");
  const [connection, setConnection] = useState("");
  const [cards, setCards] = useState<CardRow[]>([]);
  const [cardQuery, setCardQuery] = useState("");
  const [tagQuery, setTagQuery] = useState("");
  const [cardUrl, setCardUrl] = useState("");
  const [cardStatus, setCardStatus] = useState("");

  async function loadCards() {
    const response = await apiFetch("/context/cards/library");
    if (response.ok) setCards((await response.json()).data || []);
  }

  async function load() {
    const settings = await apiFetch("/models/dzmm/settings");
    if (!settings.ok) return;
    const state = await settings.json();
    setConfigured(!!state.token_configured);
    setWallet(state.wallet);
    // Only replace the initial local default. A manual mid-thread switch stays selected.
    if (useChatStore.getState().selectedChatModel === "local:9b" && state.token_configured) {
      select(state.default_model);
    }
    const catalog = await apiFetch("/models/dzmm");
    if (catalog.ok) {
      const body = await catalog.json();
      setRows(body.data || []);
      setConnection(body.reachable ? "模型目录已连接" : "模型目录暂不可用；价格见充值页");
    }
    await loadCards();
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    const response = await apiFetch("/models/dzmm/settings", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_token: token }),
    });
    if (!response.ok) { setConnection("Token 保存失败"); return; }
    setToken("");
    const state = await response.json();
    select(state.default_model);
    await load();
  }

  async function clearToken() {
    const response = await apiFetch("/models/dzmm/settings", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_token: "" }),
    });
    if (response.ok) { select("local:9b"); await load(); }
  }

  async function importFile(file: File) {
    const response = await apiFetch(`/context/cards/import?filename=${encodeURIComponent(file.name)}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: await file.arrayBuffer(),
    });
    if (!response.ok) { setCardStatus("导入失败：请检查 Tavern V2/V3 JSON/PNG"); return; }
    const card = await response.json();
    setCardStatus(`已导入 ${card.name}；新会话可选用`);
    await loadCards();
  }

  async function importUrl() {
    const response = await apiFetch("/context/cards/import-url", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: cardUrl }),
    });
    if (!response.ok) { setCardStatus("请导出 JSON/PNG 后导入"); return; }
    setCardStatus("角色卡已导入；新会话可选用");
    setCardUrl("");
    await loadCards();
  }

  return <div className="dzmm-settings">
    <label>对话模型 <select value={selected} onChange={(e) => select(e.target.value)}>
      <optgroup label="推荐云端">
        {(rows.length ? rows.filter((row) => row.id.startsWith("nalang-")) : [
          { id: "nalang-turbo-0826", label: "免费档" }, { id: "nalang-xl-0826", label: "推荐付费" },
        ]).map((row) => <option key={row.id} value={row.id} disabled={!configured}>{row.id} · {row.label}</option>)}
      </optgroup>
      <optgroup label="本机"><option value="local:9b">本机 9B</option><option value="local:27b" disabled={!activeLocalModel?.includes("27b")}>本机 27B · 先在 Models 启用</option></optgroup>
    </select></label>
    <details>
      <summary>模型表与 DZMM 设置</summary>
      <p>选云端模型时，人设与对话会离开本机。云端额度用尽会改用本机 9B。</p>
      <p>{wallet}。积分与网页、酒馆AI、小说AI 同一钱包；Token 是调用凭证。</p>
      <label>DZMM API Token <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} /></label>
      <button type="button" disabled={!token.trim()} onClick={() => void save()}>保存 Token</button>
      {configured ? <button type="button" onClick={() => void clearToken()}>清除 Token</button> : null}
      <button type="button" onClick={() => void load()}>测试连接</button>
      <p>{connection}</p>
      <p><a href="https://www.dzmm.ai/settings/api" target="_blank" rel="noreferrer">获取 Token</a> · <a href="https://www.dzmm.ai/" target="_blank" rel="noreferrer">去充值</a>（官网顶栏「去充值」；支付页 payweld.com 需从官网或应用内进入）</p>
      <p>TG 签到仅同一 DZMM / 酒馆AI 账号通用：确认手机号或邮箱相同，在官网核对钱包，再到 API 设置生成 Token。未绑定官网的群积分不通用；余额不符请在官网账户页查绑定或合并。Kiln 不提供 TG 签到。</p>
      <p>首充 $3、标价 $5 套餐得 500 积分是页面可见促销，可能变动；支付宝/微信按人民币，信用卡按美元。充值积分永久有效，到账可能需几分钟；限时赠分以钱包到期日为准。会员/VIP 另行计费。</p>
      <p>Turbo 有社区提及每天约 50 条，实际以官网当日配额为准。XL / Max 按积分扣费。以下为本站评分；价格是估价，以钱包为准。</p>
      <div className="dzmm-table-wrap"><table><thead><tr><th>模型</th><th>文爱/指令</th><th>速度</th><th>长卡</th><th>隐私</th><th>计价</th><th>额度</th></tr></thead><tbody>
        {rows.map((r) => <tr key={r.id}><td>{r.id}<br />{r.label}</td><td>{r.quality}</td><td>{r.speed}</td><td>{r.long_card}</td><td>{r.privacy}</td><td>{r.price}</td><td>{r.quota}</td></tr>)}
      </tbody></table></div>
      <h3>本机角色卡</h3>
      <p>导入 Tavern V2/V3 JSON 或 PNG；角色身份与当前预设场景可同时使用。</p>
      <input type="file" accept=".json,.png" onChange={(e) => { const file = e.target.files?.[0]; if (file) void importFile(file); }} />
      <label>DZMM 角色链接 <input type="url" value={cardUrl} onChange={(e) => setCardUrl(e.target.value)} placeholder="https://www.dzmm.ai/character/…" /></label>
      <button type="button" onClick={() => void importUrl()}>导入链接</button>
      <p>{cardStatus}</p>
      <label>搜索角色卡 <input value={cardQuery} onChange={(e) => setCardQuery(e.target.value)} /></label>
      <label>标签 <input value={tagQuery} onChange={(e) => setTagQuery(e.target.value)} /></label>
      <select aria-label="选择角色卡" value={selectedCard || ""} onChange={(e) => selectCard(e.target.value || null)}>
        <option value="">不使用角色卡</option>
        {cards.filter((card) => `${card.name} ${card.description}`.includes(cardQuery) &&
          (!tagQuery || (card.tags || []).some((tag) => tag.includes(tagQuery)))).map((card) => <option key={card.id} value={card.id}>{card.name}</option>)}
      </select>
    </details>
  </div>;
}

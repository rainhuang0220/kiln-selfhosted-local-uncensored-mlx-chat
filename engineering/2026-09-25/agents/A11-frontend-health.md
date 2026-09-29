# A11 前端健康横幅与登录门

## 结论

认证开启时，未登录用户**看不到**「模型暂时离线」横幅。

`App` 在主界面之前就返回 `<AuthGate />`。横幅只写在通过这道门之后的聊天壳里。`AuthGate` 本身没有这条文案。

`login()` 只在登录**成功**之后 `await get().loadHealth()`。失败直接返回，不调用 `loadHealth`。

## 未登录为什么看不到横幅

初始状态是未登录且尚未核对会话：`health` 为 `null`，`authRequired: true`，`authOk: false`，`authChecked: false`（`web/src/stores/chat-store.ts` 78、91–93 行）。

`web/src/app.tsx` 146–157 行：

```tsx
if (!store.authChecked || (store.authRequired && !store.authOk)) {
  return (
    <AuthGate
      authChecked={store.authChecked}
      authReady={store.authReady}
      authSetup={store.authSetup}
      authError={store.authError}
      lockedUser={store.lockedUser}
      login={store.login}
      register={store.register}
    />
  );
}
```

`!authChecked`，或 `authRequired && !authOk`，都会在这里结束渲染。主界面从 160 行才开始。横幅在 464–468 行：

```tsx
{!store.health?.provider.reachable ? (
  <div className="banner" role="status">
    模型暂时离线。Mac 上的 mlx 由 LaunchAgent 常驻，通常会在一两分钟内自动拉起，请稍后再发。
  </div>
) : null}
```

`health` 为 `null` 或 `provider.reachable` 为假时，这个条件为真。但未登录走不到这段 JSX。`web/src/components/AuthGate.tsx` 没有「模型暂时离线」；未核对完时只显示「正在确认登录状态…」（35–44 行），核对完则是登录 / 注册表单。

`loadHealth` 在未登录时也不会去拉 `/health`（`web/src/stores/chat-store.ts` 264–283 行）：

```ts
const auth = await apiFetch("/auth/status");
if (auth.ok) {
  const s = await auth.json();
  set({ /* authRequired, authOk, authChecked, ... */ });
  if (s.required && !s.ok) return;
} else {
  set({ authChecked: true, authRequired: true, authOk: false });
  return;
}
const r = await apiFetch("/health");
```

`required && !ok`，或 `/auth/status` 本身失败，都在 `/health` 之前返回。`health` 保持 `null`（或登出前的旧值）。挂载时、每 10 秒、以及页签重新可见，都会调用 `loadHealth`（`web/src/app.tsx` 39–49 行），但同样被 279 / 282 行截断，横幅仍不挂载。

`logout` / `lock` / `wipePrivateState` 也不清 `health`（160–174、235–261 行）。登出后 `authOk` 为假，146 行再次换成 `AuthGate`，横幅卸载。

唯一例外：服务端 `required === false`，即 `authRequired` 为假。此时 146 行的第二项不成立，没有会话也会进入主界面。若 `health` 仍空或 `provider.reachable` 为假，就会看到这条横幅。默认初始值是 `authRequired: true`；产品路径上的未登录用户停在 `AuthGate`。

## `login()` 对 `loadHealth` 做了什么

`web/src/stores/chat-store.ts` 176–199 行：

```ts
login: async (username, password, rememberMe = false) => {
  get().wipePrivateState();
  const r = await apiFetch("/auth/login", { /* POST */ });
  if (!r.ok) {
    set({ authOk: false, authRequired: true, authChecked: true, authError: "用户名或密码不对" });
    return false;
  }
  set({
    authOk: true,
    authRequired: true,
    authChecked: true,
    authError: null,
    lockedUser: null,
    username: body.username || username,
    role: body.role || "owner",
  });
  await get().loadHealth();
  await get().loadConversations();
  return true;
},
```

- 失败（183–185 行）：只把 `authOk` 置假并返回 `false`，**不**调用 `loadHealth`。用户仍停在 `AuthGate`。
- 成功（188–198 行）：先 `set` 令 `authOk: true`，再 `await get().loadHealth()`，然后 `loadConversations()`。没有向 `loadHealth` 传参。

这次 `loadHealth` 会再请求 `/auth/status`。会话已成立时，279 行的 `required && !ok` 不成立，于是请求 `/health` 并 `set({ health })`（284–287 行）。请求抛错则写入一份 `status: "down"`、`provider.reachable: false` 的占位健康状态（288–301 行）。后者会让刚进入主界面的已登录用户看到离线横幅。

成功 `set({ authOk: true })` 发生在 `await loadHealth()` 之前。门禁一放开，若 `health` 仍是初始 `null`，464 行的条件为真，横幅可能在 `/health` 返回前闪一下。那是登录成功之后，不是未登录界面。

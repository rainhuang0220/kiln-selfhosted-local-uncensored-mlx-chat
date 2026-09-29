import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";

export type AuthGateProps = {
  authChecked: boolean;
  authReady: boolean;
  authSetup: boolean;
  authError: string | null;
  lockedUser: string | null;
  login: (username: string, password: string, rememberMe: boolean) => Promise<boolean>;
  register: (username: string, password: string) => Promise<boolean>;
};

export function AuthGate({
  authChecked,
  authReady,
  authSetup,
  authError,
  lockedUser,
  login,
  register,
}: AuthGateProps) {
  const uid = useId();
  const userId = `auth-username`;
  const passId = `auth-password`;
  const rememberId = `auth-remember`;
  const errorId = `${uid}-error`;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const locked = Boolean(lockedUser);

  if (!authChecked) {
    return (
      <div className="auth-gate">
        <div className="auth-card" aria-busy="true">
          <p className="auth-kicker">Kiln / Private</p>
          <h1>Private local AI</h1>
          <p>正在确认登录状态…</p>
        </div>
      </div>
    );
  }

  const canSubmit =
    Boolean(password) && (locked || Boolean(username.trim())) && (authReady || authSetup) && !submitting;

  return (
    <div className="auth-gate">
      <form
        className="auth-card"
        noValidate
        aria-describedby={authError ? errorId : undefined}
        onSubmit={(e) => {
          e.preventDefault();
          if (!canSubmit || submitting) return;
          const user = authSetup ? username : username || lockedUser || "";
          setSubmitting(true);
          const done = authSetup ? register(user, password) : login(user, password, rememberMe);
          void done
            .then((ok) => {
              if (ok) {
                setPassword("");
                setRememberMe(false);
              }
            })
            .finally(() => setSubmitting(false));
        }}
      >
        <p className="auth-kicker">Kiln / Private</p>
        <h1>{authSetup ? "创建账号" : locked ? "已锁定" : "Private local AI"}</h1>
        <p className="auth-lede">
          {!authReady
            ? "本机尚未完成所有者设置。请在这台 Mac 上创建 owner，而不是从公网注册。"
            : authSetup
              ? "还没有用户。用户名 3–32 位（小写字母数字下划线），密码至少 10 位。"
              : locked
                ? "输入密码继续。默认只在关闭浏览器前保持登录。"
                : "私有远端访问：仅已发放账号可登录。新账号须由本机所有者在 Mac 上创建（python -m app.cli create-user），公网不能自助注册。"}
        </p>
        {!authReady ? (
          <pre className="auth-cli">python -m app.cli create-owner --username YOURNAME</pre>
        ) : null}
        {authReady && !authSetup ? (
          <pre className="auth-cli">python -m app.cli create-user --username NEWUSER</pre>
        ) : null}

        <div className="auth-field">
          <label htmlFor={userId}>{locked && !authSetup ? "当前账号" : "用户名"}</label>
          {authSetup || !locked ? (
            <input
              id={userId}
              name="username"
              type="text"
              autoFocus
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="请输入用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          ) : (
            <input
              id={userId}
              name="username"
              type="text"
              readOnly
              className="is-readonly"
              value={lockedUser || ""}
              autoComplete="username"
            />
          )}
        </div>

        <div className="auth-field">
          <label htmlFor={passId}>密码</label>
          <div className="auth-password">
            <input
              id={passId}
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete={authSetup ? "new-password" : "current-password"}
              placeholder="请输入密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              className="auth-peek"
              aria-label={showPassword ? "隐藏密码" : "显示密码"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((v) => !v)}
            >
              {showPassword ? <EyeOff size={18} strokeWidth={1.75} /> : <Eye size={18} strokeWidth={1.75} />}
            </button>
          </div>
        </div>

        {!authSetup ? (
          <label className="auth-remember" htmlFor={rememberId}>
            <input
              id={rememberId}
              name="remember"
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
            />
            <span>
              在此设备保持登录 7 天
            </span>
          </label>
        ) : null}

        {authError ? (
          <p className="auth-error" id={errorId} role="alert">
            {authError}
          </p>
        ) : null}

        <button className="btn primary auth-submit" type="submit" disabled={!canSubmit}>
          {submitting ? "正在进入…" : authSetup ? "创建并进入" : locked ? "解锁" : "进入"}
        </button>
      </form>
    </div>
  );
}

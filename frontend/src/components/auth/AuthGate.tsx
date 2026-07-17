import { useEffect, useState, type ReactNode } from 'react';
import { Button, Input, MessagePlugin } from 'tdesign-react';
import {
  getAppSession,
  loginAppSession,
  logoutAppSession,
  registerAppSession,
  type AppSession,
} from '../../services/auth';
import { SessionContext } from './session';

function storeScope(session: AppSession) {
  try { sessionStorage.setItem('yuanbao.userScope', session.user.id); } catch { /* cache isolation is best effort */ }
}

export default function AuthGate({ children }: { children: (session: AppSession) => ReactNode }) {
  const [session, setSession] = useState<AppSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    getAppSession().then((value) => { storeScope(value); setSession(value); }).catch(() => setSession(null)).finally(() => setLoading(false));
  }, []);

  const submit = async () => {
    setSubmitting(true); setError('');
    try {
      const value = registering
        ? await registerAppSession(username, password)
        : await loginAppSession(username, password);
      storeScope(value); setSession(value); setPassword('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '登录失败');
    } finally { setSubmitting(false); }
  };

  if (loading) return <div className="auth-loading">正在确认身份…</div>;
  if (!session) {
    return (
      <main className="auth-page">
        <section className="auth-card">
          <h1>元宝 Agent</h1>
          <p>{registering ? '创建独立的 Agent 工作区' : '登录你的主动式 AI 工作区'}</p>
          <Input value={username} onChange={(value) => setUsername(String(value))} placeholder="用户名（至少 3 位）" autocomplete="username" />
          <Input type="password" value={password} onChange={(value) => setPassword(String(value))} placeholder="密码（至少 12 位）" autocomplete={registering ? 'new-password' : 'current-password'} onEnter={submit} />
          {error && <div className="auth-error" role="alert">{error}</div>}
          <Button block theme="primary" loading={submitting} onClick={submit}>{registering ? '注册并进入' : '登录'}</Button>
          <Button block variant="text" onClick={() => { setRegistering((value) => !value); setError(''); }}>
            {registering ? '已有账户？返回登录' : '没有账户？创建账户'}
          </Button>
        </section>
      </main>
    );
  }

  const logout = async () => {
    try { await logoutAppSession(); } catch { MessagePlugin.warning('退出请求未确认，本地会话仍将清除'); }
    try { sessionStorage.removeItem('yuanbao.userScope'); } catch { /* ignore */ }
    setSession(null);
  };
  return <SessionContext.Provider value={{ ...session, logout }}>{children(session)}</SessionContext.Provider>;
}

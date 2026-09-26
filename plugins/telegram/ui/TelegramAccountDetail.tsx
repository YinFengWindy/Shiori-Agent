import { EyeIcon, EyeSlashIcon } from "@phosphor-icons/react";
import { useEffect, useId, useState } from "react";
import { createPluginBridgeClient, type PluginConfigSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { createAccountClient } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import type { PluginAccountDetailComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { InlineError } from "../../../apps/desktop/renderer/src/shared/feedback/InlineError";
import { ghostButtonClass, iconButtonClass, inputClass, primaryButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { telegramBots, withTelegramBot } from "./telegramConfig";

const configClient = createPluginBridgeClient();
const accountsClient = createAccountClient();

type KnownChat = { chat_id: string; chat_type: string; title: string; username: string; topics: number[]; last_seen: string };
type BotIdentity = { bot_id: string; name: string; username: string };

/** Platform-owned Token, polling and observed-target controls in the shared account detail. */
export function TelegramAccountDetail({ account, onChanged, client }: PluginAccountDetailComponentProps) {
  const [config, setConfig] = useState<PluginConfigSnapshot | null>(null);
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [known, setKnown] = useState<KnownChat[]>([]);
  const [identity, setIdentity] = useState<BotIdentity | null>(null);
  const tokenId = useId();
  const accountRef = account?.configRef;
  useEffect(() => {
    void configClient.getConfig("telegram").then(setConfig).catch((failure) => setError(String(failure)));
  }, []);
  useEffect(() => {
    if (!accountRef) return;
    void client.call<{ chats: KnownChat[] }>("known.list", { ref: accountRef })
      .then((result) => setKnown(result.chats)).catch((failure) => setError(String(failure)));
    void client.call<BotIdentity>("identity.get", { ref: accountRef })
      .then(setIdentity).catch((failure) => setError(String(failure)));
  }, [accountRef, client]);

  const saved = config && account ? telegramBots(config).find((bot) => bot.ref === account.configRef) : null;

  async function save(enabled: boolean) {
    if (!config || busy) return;
    setBusy(true);
    setError("");
    try {
      let identity: { bot_id: string } | undefined;
      if (token.trim()) {
        identity = await client.call<{ bot_id: string }>("token.verify", { token: token.trim() });
        const botId = identity.bot_id;
        if (account && botId !== account.platformAccountId) {
          throw new Error("新 Token 属于另一个 Bot，请添加新账号");
        }
        if (!account && (await accountsClient.list()).some((item) => item.pluginId === "telegram" && item.platformAccountId === botId)) {
          throw new Error("此 Bot 已添加");
        }
      }
      const ref = account?.configRef ?? crypto.randomUUID().replaceAll("-", "");
      const values = withTelegramBot(config, ref, token.trim() || undefined, enabled);
      const result = await configClient.setConfig("telegram", values, { operationId: crypto.randomUUID() });
      setConfig({ ...config, values: result.values, envStatus: result.envStatus });
      setToken("");
      const created = account ?? (await accountsClient.list()).find((item) => item.pluginId === "telegram" && item.configRef === ref);
      onChanged(created?.id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return <div className="grid gap-4">
    {error ? <InlineError message={error} /> : null}
    {identity?.username ? <p className="m-0 text-body-sm text-ink-secondary">@{identity.username}</p> : null}
    <div className="grid gap-2 text-body-sm text-ink-secondary">
      <label htmlFor={tokenId}>Bot Token</label>
      <span className="flex items-center gap-2">
        <input id={tokenId} className={inputClass} type={showToken ? "text" : "password"} value={token}
          autoComplete="off" placeholder={saved ? "保留当前 Token" : ""}
          onChange={(event) => setToken(event.target.value)} />
        <button type="button" className={iconButtonClass} onClick={() => setShowToken((value) => !value)}
          aria-label={showToken ? "隐藏 Token" : "显示 Token"} title={showToken ? "隐藏 Token" : "显示 Token"}>
          {showToken ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
        </button>
      </span>
    </div>
    <div className="flex flex-wrap gap-2">
      <button type="button" className={primaryButtonClass} disabled={!config || busy || (!saved && !token.trim())}
        onClick={() => void save(true)}>保存并连接</button>
      {saved?.enabled && <button type="button" className={ghostButtonClass} disabled={busy}
        onClick={() => void save(false)}>断开连接</button>}
      {saved && !saved.enabled && <button type="button" className={ghostButtonClass} disabled={busy}
        onClick={() => void save(true)}>重新连接</button>}
    </div>
    {account && <section className="grid gap-2 border-t border-line-soft pt-4">
      <h3 className="m-0 text-body font-semibold text-ink">已知会话</h3>
      <ul className="m-0 grid gap-1 p-0 text-body-sm text-ink-secondary">
        {known.map((chat) => <li key={chat.chat_id} className="flex justify-between gap-3">
          <span className="truncate">{chat.title || (chat.username ? `@${chat.username}` : chat.chat_id)}</span>
          <span className="shrink-0 text-ink-muted">{chat.chat_type} · {chat.chat_id}{chat.topics?.length ? ` · ${chat.topics.join(", ")}` : ""}</span>
        </li>)}
      </ul>
      <p className="m-0 text-body-xs text-ink-muted">仅显示此 Bot 已收到消息的会话；群消息可见性受 Telegram 隐私模式限制。</p>
    </section>}
  </div>;
}

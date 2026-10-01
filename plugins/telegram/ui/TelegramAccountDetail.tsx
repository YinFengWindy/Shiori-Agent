import { EyeIcon, EyeSlashIcon, InfoIcon } from "@phosphor-icons/react";
import { useEffect, useId, useState } from "react";
import { iconButtonClass, inputClass, useAccountAction, type PluginAccountDetailComponentProps } from "@shiori/plugin-sdk";

type KnownChat = { chat_id: string; chat_type: string; title: string; username: string; topics: number[]; last_seen: string };
type BotIdentity = { bot_id: string; name: string; username: string };

/** Platform-owned Token, polling and observed-target controls in the shared account detail. */
export function TelegramAccountDetail({ account, roleId, onChanged, client, host }: PluginAccountDetailComponentProps) {
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const { pending, error, errorDetail, reportError, run } = useAccountAction(onChanged);
  const [known, setKnown] = useState<KnownChat[]>([]);
  const [identity, setIdentity] = useState<BotIdentity | null>(null);
  const tokenId = useId();
  const accountRef = account?.configRef;
  const connected = account?.connection === "online" || account?.connection === "connecting";
  useEffect(() => {
    if (!accountRef) return;
    void client.call<{ chats: KnownChat[] }>("known.list", { ref: accountRef })
      .then((result) => setKnown(result.chats)).catch((failure) => reportError(failure, "会话列表加载失败"));
    void client.call<BotIdentity>("identity.get", { ref: accountRef })
      .then(setIdentity).catch((failure) => reportError(failure, "账号身份加载失败"));
  }, [accountRef, client, reportError]);

  // An offline saved Bot reconnects with its kept Token unless a new one is typed.
  const save = () => run("connect", async () => {
    const result = await client.call<{ account_id: string }>("bot.save", {
      role_id: roleId, token: token.trim(), ...(account ? { account_id: account.id } : {}),
    });
    setToken("");
    return result.account_id;
  });
  const disconnect = () => run("disconnect", async () => {
    if (!account) return undefined;
    await client.call("bot.disconnect", { account_id: account.id, role_id: roleId });
    return account.id;
  });

  return <div className="grid gap-4">
    <host.ui.AccountStatusCard account={account} pending={pending}
      action={account && connected
        ? { kind: "disconnect", onClick: () => void disconnect() }
        : { kind: "connect", onClick: () => void save(), disabled: !account && !token.trim() }}>
      <host.ui.Reveal show={Boolean(error)} className="pt-3"><host.ui.InlineError message={error} detail={errorDetail} /></host.ui.Reveal>
    </host.ui.AccountStatusCard>
    {identity?.username ? <p className="m-0 text-body-sm text-ink-secondary">@{identity.username}</p> : null}
    <div className="grid gap-2 text-body-sm text-ink-secondary">
      <label htmlFor={tokenId}>Bot Token</label>
      <span className="flex items-center gap-2">
        <input id={tokenId} className={inputClass} type={showToken ? "text" : "password"} value={token}
          autoComplete="off" placeholder={account ? "保留当前 Token" : ""}
          onChange={(event) => setToken(event.target.value)} />
        <button type="button" className={iconButtonClass} onClick={() => setShowToken((value) => !value)}
          aria-label={showToken ? "隐藏 Token" : "显示 Token"} title={showToken ? "隐藏 Token" : "显示 Token"}>
          {showToken ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
        </button>
      </span>
    </div>
    {account && <section className="grid gap-2 border-t border-line-soft pt-4">
      <h3 className="m-0 flex items-center gap-2 text-body font-semibold text-ink">
        已知会话
        <span role="note" aria-label="Telegram 隐私模式可能限制普通群消息接收" title="Telegram 隐私模式可能限制普通群消息接收">
          <InfoIcon className="h-4 w-4 text-ink-muted" />
        </span>
      </h3>
      <ul className="m-0 grid gap-1 p-0 text-body-sm text-ink-secondary">
        {known.map((chat) => <li key={chat.chat_id} className="flex justify-between gap-3">
          <span className="truncate">{chat.title || (chat.username ? `@${chat.username}` : chat.chat_id)}</span>
          <span className="shrink-0 text-ink-muted">{chat.chat_type} · {chat.chat_id}{chat.topics?.length ? ` · ${chat.topics.join(", ")}` : ""}</span>
        </li>)}
      </ul>
    </section>}
  </div>;
}

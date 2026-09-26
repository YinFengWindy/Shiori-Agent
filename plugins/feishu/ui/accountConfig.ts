/** One regional Feishu/Lark custom app saved in plugin configuration. */
export type FeishuApp = {
  app_id: string; app_secret: string; domain: "feishu" | "lark";
  connection_enabled?: boolean; connection_revision?: number;
};

/** Preserves the legacy single-app config until the first explicit save. */
export function configuredApps(values: Record<string, unknown>): FeishuApp[] {
  const accounts = Array.isArray(values.accounts) ? values.accounts.flatMap((value) => parseApp(value) ?? []) : [];
  const legacy = parseApp(values);
  return legacy && !accounts.some((app) => app.domain === legacy.domain && app.app_id === legacy.app_id)
    ? [legacy, ...accounts]
    : accounts;
}

function parseApp(value: unknown): FeishuApp | null {
  if (!value || typeof value !== "object") return null;
  const appId = "app_id" in value ? value.app_id : undefined;
  const secret = "app_secret" in value ? value.app_secret : undefined;
  const rawDomain = "domain" in value ? value.domain : undefined;
  const enabled = "connection_enabled" in value ? value.connection_enabled : undefined;
  const revision = "connection_revision" in value ? value.connection_revision : undefined;
  if (typeof appId !== "string" || !appId || typeof secret !== "string") return null;
  const regionalDomain = typeof rawDomain === "string" ? rawDomain.trim().replace(/\/$/, "") : "";
  const domain = regionalDomain === "https://open.feishu.cn" ? "feishu"
    : regionalDomain === "https://open.larksuite.com" ? "lark" : regionalDomain;
  return domain === "feishu" || domain === "lark"
    ? { app_id: appId, app_secret: secret, domain,
      ...(typeof enabled === "boolean" ? { connection_enabled: enabled } : {}),
      ...(typeof revision === "number" ? { connection_revision: revision } : {}),
    }
    : null;
}

function migratedValues(values: Record<string, unknown>, accounts: FeishuApp[]) {
  const legacy = parseApp(values);
  const legacyRef = typeof values.legacy_channel_ref === "string" && values.legacy_channel_ref
    ? values.legacy_channel_ref : legacy ? `${legacy.domain}:${legacy.app_id}` : "";
  return { ...values, app_id: "", app_secret: "", domain: "feishu", legacy_channel_ref: legacyRef, accounts };
}

/** Builds one atomic config update and clears migrated single-app fields. */
export function withSavedApp(values: Record<string, unknown>, app: FeishuApp): Record<string, unknown> {
  const apps = configuredApps(values);
  const ref = `${app.domain}:${app.app_id}`;
  const index = apps.findIndex((item) => `${item.domain}:${item.app_id}` === ref);
  const updated = [...apps];
  const connected = { ...app, connection_enabled: true, connection_revision: (index < 0 ? 0 : apps[index].connection_revision ?? 0) + 1 };
  if (index < 0) updated.push(connected);
  else updated[index] = connected;
  return migratedValues(values, updated);
}

/** Persists a manual disconnect without touching another app's credential. */
export function withConnection(values: Record<string, unknown>, ref: string, enabled: boolean): Record<string, unknown> {
  const apps = configuredApps(values);
  const index = apps.findIndex((app) => `${app.domain}:${app.app_id}` === ref);
  if (index < 0) throw new Error("飞书账号配置不存在");
  const updated = [...apps];
  updated[index] = { ...apps[index], connection_enabled: enabled };
  return migratedValues(values, updated);
}

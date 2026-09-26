/** One regional Feishu/Lark custom app saved in plugin configuration. */
export type FeishuApp = { app_id: string; app_secret: string; domain: "feishu" | "lark" };

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
  if (typeof appId !== "string" || !appId || typeof secret !== "string") return null;
  const regionalDomain = typeof rawDomain === "string" ? rawDomain.trim().replace(/\/$/, "") : "";
  const domain = regionalDomain === "https://open.feishu.cn" ? "feishu"
    : regionalDomain === "https://open.larksuite.com" ? "lark" : regionalDomain;
  return domain === "feishu" || domain === "lark"
    ? { app_id: appId, app_secret: secret, domain }
    : null;
}

/** Builds one atomic config update and clears migrated single-app fields. */
export function withSavedApp(values: Record<string, unknown>, app: FeishuApp): Record<string, unknown> {
  const apps = configuredApps(values);
  const ref = `${app.domain}:${app.app_id}`;
  const index = apps.findIndex((item) => `${item.domain}:${item.app_id}` === ref);
  const updated = [...apps];
  if (index < 0) updated.push(app);
  else updated[index] = app;
  return { ...values, app_id: "", app_secret: "", domain: "feishu", accounts: updated };
}

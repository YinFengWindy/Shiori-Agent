/** One regional Feishu/Lark custom app saved in plugin configuration. */
export type FeishuApp = { app_id: string; app_secret: string; domain: "feishu" | "lark" };

/** Preserves the legacy single-app config until the first explicit save. */
export function configuredApps(values: Record<string, unknown>): FeishuApp[] {
  const accounts = Array.isArray(values.accounts) ? values.accounts.filter(isApp) : [];
  const legacy = isApp(values) ? values : null;
  return legacy && !accounts.some((app) => app.domain === legacy.domain && app.app_id === legacy.app_id)
    ? [legacy, ...accounts]
    : accounts;
}

function isApp(value: unknown): value is FeishuApp {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<FeishuApp>;
  return typeof item.app_id === "string" && typeof item.app_secret === "string"
    && (item.domain === "feishu" || item.domain === "lark") && Boolean(item.app_id && item.app_secret);
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

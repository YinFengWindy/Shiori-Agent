import type { ManagedStatus } from "./useManagedNapCat";

/** Concise user-facing state; QR waiting is a normal login step. */
export function managedQQStatus(status: ManagedStatus): { label: string; tone: "success" | "accent" | "muted" | "danger" } {
  if (status.connection === "online") return { label: "在线", tone: "success" };
  if (status.preparation.stage === "error" || status.connection === "error") return { label: "连接失败", tone: "danger" };
  if (["downloading", "extracting", "verifying"].includes(status.preparation.stage)) {
    return { label: "正在准备", tone: "accent" };
  }
  if (status.login.qrcode) return { label: "等待扫码登录", tone: "accent" };
  if (status.login.phase === "login_required") return { label: "正在获取二维码", tone: "accent" };
  if (status.login.phase === "starting" || status.connection === "connecting") return { label: "正在启动", tone: "accent" };
  return { label: "已停止", tone: "muted" };
}

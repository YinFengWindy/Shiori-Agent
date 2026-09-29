import type { AccountStatusView } from "@shiori/plugin-sdk";
import type { ManagedStatus } from "./useManagedNapCat";

const preparationLabels = {
  idle: "等待启动", downloading: "下载中", extracting: "解压中",
  verifying: "校验中", ready: "已就绪", error: "准备失败",
} as const;

/** Whether NapCat is still being downloaded, unpacked or verified. */
export function napCatPreparing(status: ManagedStatus) {
  const { stage } = status.preparation;
  return stage === "downloading" || stage === "extracting" || stage === "verifying";
}

/** Whether the QQ login itself has succeeded, whatever the connection is doing. */
export function managedLoginOnline(status: ManagedStatus) {
  return status.connection === "online" || status.login.phase === "online";
}

/**
 * Concise user-facing state; QR waiting is a normal login step. A finished
 * login only reads 在线 once the host account is online too — until the
 * plugin reports the connection it is 登录成功，正在连接, not 需要登录.
 */
export function managedQQStatus(status: ManagedStatus, hostOnline: boolean): AccountStatusView {
  if (status.preparation.stage === "error" || status.connection === "error") return { label: "连接失败", tone: "danger" };
  if (managedLoginOnline(status)) {
    return hostOnline ? { label: "在线", tone: "success" } : { label: "登录成功，正在连接", tone: "warning" };
  }
  if (napCatPreparing(status)) return { label: "正在准备", tone: "warning" };
  if (status.login.qrcode) return { label: "等待扫码登录", tone: "warning" };
  if (status.login.phase === "login_required") return { label: "正在获取二维码", tone: "warning" };
  if (status.login.phase === "starting" || status.connection === "connecting") return { label: "正在启动", tone: "warning" };
  return { label: "已停止", tone: "muted" };
}

/** Short NapCat progress for the status card, e.g. `NapCat v4 · 下载中 42%`; empty once connected. */
export function napCatDetail(status: ManagedStatus | null) {
  if (!status || status.connection === "online") return "";
  const { stage, version, percent } = status.preparation;
  const stageText = stage !== "ready" ? ` · ${preparationLabels[stage]}` : "";
  const percentText = stage === "downloading" || stage === "extracting" ? ` ${percent}%` : "";
  return `NapCat ${version}${stageText}${percentText}`;
}

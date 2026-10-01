import { errorMessage } from "@shiori/sdk";

/** Converts browser microphone failures while the native exception name is still available. */
export function microphoneFailure(error: unknown, phase: "devices" | "start" | "stop") {
  const name = error instanceof Error ? error.name : "";
  const cause = errorMessage(error);
  const message = name === "NotAllowedError" || name === "SecurityError" ? "麦克风权限未开启，请在系统设置中允许访问麦克风"
    : name === "NotFoundError" || name === "OverconstrainedError" ? "找不到所选麦克风，请重新选择设备"
    : name === "NotReadableError" ? "麦克风无法使用，请检查设备连接或关闭占用它的应用"
    : { devices: "麦克风设备读取失败", start: "麦克风启动失败", stop: "录音处理失败" }[phase];
  return `${message}\n${cause}`;
}

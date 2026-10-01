import type { DesktopUpdateState } from "../../../src/updateContract.js";

const statusLabels = {
  unsupported: null, idle: "尚未检查更新", checking: "正在检查更新…",
  current: "已是最新版本", unavailable: "暂无可用更新", downloading: "正在下载更新…",
  downloaded: "更新已就绪", installing: "正在重启安装…", error: "更新失败",
};

/** Resolves the actual recoverable update step and its matching action label. */
export function updatePresentation(state: DesktopUpdateState | null, error?: string | null) {
  const install = state?.phase === "downloaded" || (state?.phase === "error" && state.errorPhase === "installing");
  let actionLabel = error || state?.phase === "error" ? "重新检查" : "检查更新";
  if (install) actionLabel = state?.phase === "error" ? "重试安装" : "重启并安装";
  else if (state?.phase === "error" && state.errorPhase === "downloading") actionLabel = "重新下载";
  return {
    install, actionLabel,
    busy: state ? ["unsupported", "checking", "downloading", "installing"].includes(state.phase) : !error,
    status: state ? state.phase === "error" ? state.error : statusLabels[state.phase] : "正在读取版本…",
  };
}

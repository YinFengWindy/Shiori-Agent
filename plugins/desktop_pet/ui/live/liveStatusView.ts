import type { BilibiliAccountStatus, LiveConnection, LiveRunState, LiveStatus } from "./liveContracts";

const runStateLabels: Record<LiveRunState, string> = {
  idle: "未开始",
  running: "运行中",
  paused: "已暂停",
  stopped: "已结束",
};

const connectionLabels: Record<LiveConnection, string> = {
  connecting: "连接中",
  connected: "已连接",
  reconnecting: "重连中",
  closed: "已断开",
  login_invalid: "登录失效",
  rejected: "被拒绝",
};

/** A run that exists and can be paused, resumed or stopped. */
export function isRunActive(status: LiveStatus | null) {
  return status?.state === "running" || status?.state === "paused";
}

/** What the start button needs that the dialog already knows; null or undefined means not known yet. */
export type LiveStartFacts = {
  /** The saved (not drafted) pet switch of the role. */
  petEnabled: boolean;
  /** The saved room; undefined while the settings load or failed to, null when none is set. */
  roomId: number | null | undefined;
  /** Whether the pet speaks replies (`useSpeechReady`); null while it loads or failed to. */
  speechReady: boolean | null;
  /** The account status; null while it loads or failed to. */
  account: BilibiliAccountStatus | null;
};

/**
 * Why 开始 is unavailable, checked in the backend gate's order (pet, room,
 * TTS, login); null when it may be pressed. A fact not known yet blocks
 * without a reason, since it is still loading or its error is already shown;
 * the backend's own refusal is shown after an attempt.
 */
export function startBlockedReason({ petEnabled, roomId, speechReady, account }: LiveStartFacts) {
  if (!petEnabled) return "未启用桌宠";
  if (roomId === undefined) return "";
  if (roomId === null) return "未配置直播间";
  if (speechReady === null) return "";
  if (!speechReady) return "未开启桌宠语音";
  if (account === null) return "";
  if (account.state === "logged_out") return "未登录 B 站";
  if (account.state === "invalid") return "B 站登录已失效";
  return null;
}

/** One labelled row of the run status. */
export type LiveStatusRow = { label: string; value: string };

function roomText(room: { room_id: number; title: string }) {
  return room.title ? `${room.title}（${room.room_id}）` : String(room.room_id);
}

/**
 * The rows of the run status. The running room and the saved room are both
 * listed when the saved one changed mid-run (it applies at the next start).
 */
export function liveStatusRows(status: LiveStatus): LiveStatusRow[] {
  const rows: LiveStatusRow[] = [{ label: "状态", value: runStateLabels[status.state] }];
  if (status.state === "idle") return rows;
  if (status.connection && status.state !== "stopped") rows.push({ label: "连接", value: connectionLabels[status.connection] });
  if (status.room) {
    rows.push({ label: "直播间", value: roomText(status.room) });
    if (status.configured_room_id !== status.room.room_id) {
      rows.push({ label: "已配置直播间", value: status.configured_room_id === null ? "未配置" : String(status.configured_room_id) });
    }
  }
  if (isRunActive(status)) rows.push({ label: "待处理", value: String(status.queue_length) });
  rows.push({ label: "收到弹幕", value: String(status.counters.received ?? 0) });
  rows.push({ label: "已回复", value: String(status.counters.replied ?? 0) });
  if (status.state === "stopped" && status.stop_reason) rows.push({ label: "结束原因", value: status.stop_reason });
  return rows;
}

/** Current problems of the run; each clears in the backend once it recovers. */
export function liveStatusErrors(status: LiveStatus) {
  return [status.connection_error, status.reply_error].filter((message) => message !== "");
}

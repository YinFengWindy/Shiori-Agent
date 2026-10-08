/**
 * Wire shapes of the pet's `bilibili.*` and `live.*` RPCs (#722, #724), as
 * served by `backend/bilibili_login.py`, `backend/live_config.py` and
 * `backend/live_status.py`. Every request carries `role_id`.
 */

/** The Bilibili account a role is logged in as. */
export type BilibiliAccount = { uid: number; uname: string };

/** `bilibili.account.status` / `bilibili.account.logout`: `invalid` keeps the stored account. */
export type BilibiliAccountStatus =
  | { state: "logged_out" }
  | { state: "logged_in" | "invalid"; account: BilibiliAccount };

/** The scan progress of the QR code being shown. */
export type BilibiliScanState = "waiting_scan" | "waiting_confirm" | "expired";

/** `bilibili.login.start`: a fresh QR as a PNG data URI. */
export type BilibiliLoginStart = { state: "waiting_scan"; qrcode: string };

/** `bilibili.login.poll`: the scan progress, or the account once confirmed. */
export type BilibiliLoginPoll = { state: BilibiliScanState } | { state: "success"; account: BilibiliAccount };

/** `live.config.get` / `live.config.set`: the role's live settings. */
export type LiveConfig = {
  room_id: number | null;
  reply_interval_seconds: number;
  wait_timeout_seconds: number;
};

/** Whether the run processes danmaku; `idle` means the role never ran. */
export type LiveRunState = "idle" | "running" | "paused" | "stopped";

/** The danmaku stream connection of the run. */
export type LiveConnection = "connecting" | "connected" | "reconnecting" | "closed" | "login_invalid" | "rejected";

/** `live.status` and the run-control replies: one shape for every state. */
export type LiveStatus = {
  role_id: string;
  state: LiveRunState;
  connection: LiveConnection | null;
  /** The room the run uses; it may differ from the saved `configured_room_id`. */
  room: { room_id: number; title: string } | null;
  configured_room_id: number | null;
  run_id: string | null;
  queue_length: number;
  generating: boolean;
  output_pending: boolean;
  connection_error: string;
  reply_error: string;
  stop_reason: string;
  counters: Record<string, number>;
  recent: unknown[];
};

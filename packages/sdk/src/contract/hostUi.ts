/**
 * Props of the host components a plugin UI renders through `host.ui`
 * (runtime API 2.4.0; the account pieces serve `account.detail`). The
 * components stay host-owned; the host derives its own props from these.
 */
import type { ComponentType, ReactNode } from "react";
import type { Dialog } from "@base-ui/react/dialog";
import type { Icon } from "@phosphor-icons/react";
import type { AccountPendingAction, AccountSnapshot, AccountStatusView } from "../account/account";
import type { DraftSavePhase } from "../serialDraftQueue";
import type { PluginPersona } from "./feedback";

/** Props of `host.ui.InlineError`, the host's in-page error block. */
export type HostInlineErrorProps = {
  /** The original, factual message; always shown, persona or not. */
  message: string;
  /** Heading of a `card` (e.g. 「生成失败」); rows and strips have none. */
  title?: string;
  /** Technical cause folded behind 「详情」. */
  detail?: string;
  /** The way out (retry, reload, open settings …), placed after the text. */
  actions?: ReactNode;
  /** Let 吟风 front the block: generically or by scene. Default false. */
  persona?: PluginPersona;
  /**
   * `row`: a compact bordered block inside a form or list. `strip`: a
   * full-width band pinned to a container's edge (a card footer). `card`:
   * a centred glass card that takes over an empty area.
   */
  layout?: "row" | "strip" | "card";
  /** Glyph of the plain block (default the warning circle). */
  glyph?: Icon;
  /** Tint of the plain glyph: `accent` for a problem the user fixes in settings rather than a failure. */
  glyphTone?: "danger" | "accent";
  /**
   * `alert` interrupts assistive tech (default); `status` for results the
   * user just asked for; `false` inside a container that already is a live region.
   */
  role?: "alert" | "status" | false;
  /** Adds a close button (cards). */
  onDismiss?: () => void;
  className?: string;
  testId?: string;
};

/** Props of `host.ui.ConfirmDialog`, the host's confirmation dialog with a non-dismissable in-flight action. */
export type HostConfirmDialogProps = {
  open: boolean; title: string; description: string; confirmLabel: string; children?: ReactNode;
  busy?: boolean; confirmDisabled?: boolean; busyLabel?: string; cancelLabel?: string; error?: string; destructive?: boolean; onClose: () => void; onConfirm: () => void;
  /**
   * Let 吟风 lead the dialog. `true` / `"generic"` picks the host's generic
   * line for a destructive or an ordinary confirmation; a scene key (usually
   * `destructive`, `discard` or `confirm`) that scene's line. Default false.
   */
  persona?: PluginPersona;
  /** Optional stable focus destination when a successful action removes its trigger. */
  finalFocus?: Dialog.Popup.Props["finalFocus"];
};

/** The account status card's one button: 连接 while the account is offline, 断开连接 while it runs. */
export type AccountStatusCardAction = {
  kind: "connect" | "disconnect";
  onClick: () => void;
  /** Blocks the button for a plugin reason (missing credentials, not supported here). */
  disabled?: boolean;
};

/** Props of `host.ui.AccountStatusCard`, one account's connection at a glance. */
export type AccountStatusCardProps = {
  /** The host account, or null while a new one is being added. */
  account: AccountSnapshot | null;
  /** A plugin-known status (e.g. a QR login step) that replaces the host's reading of `account`. */
  status?: AccountStatusView;
  /** A request in flight: its status shows at once and its button spins; every button waits. */
  pending?: AccountPendingAction | null;
  /** Short progress under the status, e.g. `NapCat v4 · 下载中 42%`. */
  detail?: ReactNode;
  action?: AccountStatusCardAction;
  /** Rows below the status (QR code, progress bar); wrap each changing row in `Reveal`. */
  children?: ReactNode;
};

/** One plugin secondary action in the account detail's bottom row (QQ: 退出登录). */
export type AccountDetailAction = {
  label: string;
  onClick: () => void;
  icon?: ComponentType<{ className?: string }>;
  /** Its request is in flight: the button spins and waits. */
  pending?: boolean;
  disabled?: boolean;
};

/** Props of `host.ui.AccountDetailActions`, shown in the host's account danger zone. */
export type AccountDetailActionsProps = { actions: AccountDetailAction[] };

/** Props of `host.ui.Reveal`: fade + height show/hide; `className` styles the content box. */
export type RevealProps = { show: boolean; className?: string; children: ReactNode };

/**
 * Props of `host.ui.SettingsSavedStatus` (runtime API 4.3.0): the save phase
 * of a plugin settings section that autosaves (`usePrivateAutosave().savePhase`).
 */
export type HostSettingsSavedStatusProps = { phase: DraftSavePhase };

/** Host components a plugin UI may render (runtime API 2.4.0; the account pieces serve `account.detail`). */
export type PluginHostUi = {
  /** The host's in-page error block; `persona` (true or a scene key) lets 吟风 front it. */
  InlineError: ComponentType<HostInlineErrorProps>;
  /** The host's confirmation dialog; `persona` (true or a scene key) lets 吟风 lead it. */
  ConfirmDialog: ComponentType<HostConfirmDialogProps>;
  /** The shared account connection card: status, the one connect/disconnect button, plugin rows below. */
  AccountStatusCard: ComponentType<AccountStatusCardProps>;
  /** A plugin's secondary account actions, shown in the account detail's danger zone next to 删除账号. */
  AccountDetailActions: ComponentType<AccountDetailActionsProps>;
  /** Fade + height show/hide for a block that comes and goes with state (QR code, progress). */
  Reveal: ComponentType<RevealProps>;
  /**
   * The host's 「正在保存…」/「已保存」 mark, published in the settings page corner
   * exactly like the schema plugin config page (runtime API 4.3.0). Renders
   * nothing outside a settings page; failures stay with the plugin's own error UI.
   */
  SettingsSavedStatus: ComponentType<HostSettingsSavedStatusProps>;
};

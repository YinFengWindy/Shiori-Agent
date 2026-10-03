import type React from "react";
import type { RoleRecord, SessionPayload } from "@yinfengwindy/shiori-sdk";
import type { FeedbackReporter } from "../shared/feedback/feedbackStore";
import type { ChatSendFailure } from "../chat/chatSendFailure";
import type { RoleSessionCache } from "../chat/roleSessionCache";
import type { AppMainView } from "../shared/types";
import type { NavigationEntry } from "./appState";
import type { SettingsSectionId } from "../settings/SettingsSidebar";

/** State and callbacks assembled by the desktop root for session controllers. */
export type DesktopSessionStateArgs = {
  setRoles: React.Dispatch<React.SetStateAction<RoleRecord[]>>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setActiveSession: React.Dispatch<React.SetStateAction<SessionPayload | null>>;
  feedback: FeedbackReporter;
  /** Surfaces a failed send; the caller attaches remedies (e.g. choosing a model) it can navigate to. */
  reportSendFailure: (failure: ChatSendFailure) => void;
  setUnreadCounts: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  setSelectedAvatarAsset: React.Dispatch<React.SetStateAction<string>>;
  setSelectedChatBackground: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  setSendingSessions: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setCancellingSessions: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  applyRoleSnapshot: (role: RoleRecord, sessionOverride?: SessionPayload | null) => void;
  buildNavigationEntry: (
    view: AppMainView,
    roleId?: string,
    section?: SettingsSectionId,
  ) => NavigationEntry;
  pushNavigationEntry: (entry: NavigationEntry) => void;
  replaceNavigationEntry: (entry: NavigationEntry) => void;
  activeRoleIdRef: React.MutableRefObject<string>;
  activeSessionRef: React.MutableRefObject<SessionPayload | null>;
  roleSessionCacheRef: React.MutableRefObject<RoleSessionCache>;
  mainViewRef: React.MutableRefObject<AppMainView>;
  rolesRef: React.MutableRefObject<RoleRecord[]>;
  sendingSessionsRef: React.MutableRefObject<Record<string, string>>;
  cancellingSessionsRef: React.MutableRefObject<Record<string, string>>;
  unreadCountsRef: React.MutableRefObject<Record<string, number>>;
  openRoleRequestIdRef: React.MutableRefObject<number>;
};

import { errorMessage } from "@yinfengwindy/shiori-sdk";
import { useEffect, useRef, useState } from "react";
import type { RoleRecord } from "@yinfengwindy/shiori-sdk";
import type { useDesktopBridgeLifecycle } from "../app/useDesktopBridgeLifecycle";
import { useOnboardingSnapshot } from "./useOnboardingSnapshot";
import { completeOnboarding, onboardingSkipKey, onboardingStorageKey, onboardingVersion, readOnboardingProgress, reconcileOnboarding } from "./onboardingState";

/** Owns enrollment, per-process dismissal, recovery, and final workspace navigation. */
export function useOnboardingController(
  openRole: (roleId: string, role: RoleRecord, options: { recordHistory: boolean }) => Promise<boolean>,
  bridgeLifecycle: ReturnType<typeof useDesktopBridgeLifecycle>,
) {
  const [progress, setProgress] = useState(() => readOnboardingProgress(window.localStorage));
  const [sessionId, setSessionId] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const [entering, setEntering] = useState(false);
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const pending = useRef(false);
  const finished = progress?.version === onboardingVersion && progress.completed;
  const snapshot = useOnboardingSnapshot(!finished && !dismissed && Boolean(sessionId), bridgeLifecycle);
  useEffect(() => {
    let active = true;
    void window.miraDesktop.applicationSessionId().then((id) => {
      if (!active) return;
      setSessionId(id);
      setDismissed(window.sessionStorage.getItem(onboardingSkipKey) === id);
    }).catch((error: unknown) => { if (active) setError(errorMessage(error, { includeDetail: true })); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!snapshot.data || dismissed || finished) return;
    const next = reconcileOnboarding(progress, snapshot.data.settings.formData.models.registrations.length > 0, snapshot.data.roles.length > 0);
    if (JSON.stringify(next) === JSON.stringify(progress)) return;
    window.localStorage.setItem(onboardingStorageKey, JSON.stringify(next));
    setProgress(next);
  }, [snapshot.data, dismissed, finished, progress]);
  const skip = () => {
    if (!sessionId || pending.current) return;
    // Enroll before leaving so a partially configured first run resumes next launch.
    if (!progress) {
      const next = reconcileOnboarding(null, false, false);
      window.localStorage.setItem(onboardingStorageKey, JSON.stringify(next));
      setProgress(next);
    }
    window.sessionStorage.setItem(onboardingSkipKey, sessionId);
    setDismissed(true);
  };
  const enterWorkspace = async (role: RoleRecord) => {
    if (!progress || pending.current) return;
    pending.current = true;
    setEntering(true);
    setError("");
    try {
      const current = await snapshot.refresh();
      const selected = current?.roles.find((item) => item.id === role.id);
      if (!current || !selected || !current.settings.formData.models.registrations.length) return;
      await bridgeLifecycle.refreshBridge();
      if (!await openRole(selected.id, selected, { recordHistory: true })) throw new Error("无法进入角色工作区，请重试。");
      const completed = completeOnboarding(progress);
      window.localStorage.setItem(onboardingStorageKey, JSON.stringify(completed));
      setProgress(completed);
    } catch (error) {
      setError(errorMessage(error, { includeDetail: true }));
    } finally {
      pending.current = false;
      setEntering(false);
    }
  };
  return {
    visible: !finished && !dismissed,
    progress, ...snapshot, error: error || snapshot.error, entering, skip, enterWorkspace,
    canSkip: Boolean(sessionId) && !entering,
    settingsOpen, setSettingsOpen,
  };
}

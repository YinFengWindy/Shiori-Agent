import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { SettingsFormData, SettingsSnapshot } from "../shared/types";
import {
  cloneSettings,
  loadSettingsPageData,
  saveSettingsPageData,
  settingsEqual,
  shouldRetryFailedSettingsLoad,
} from "./settingsPersistence";
import type { SettingsDraftUpdater, SettingsSavePhase } from "./settingsPageTypes";
import { getSettingsFeedbackTimeoutMs } from "./settingsSaveState";

type UseSettingsPageControllerArgs = {
  bridgeReady: boolean;
};

/** Owns settings loading, immediate persistence, and save feedback. */
export function useSettingsPageController({ bridgeReady }: UseSettingsPageControllerArgs) {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<SettingsFormData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [savePhase, setSavePhase] = useState<SettingsSavePhase>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const loadRequestIdRef = useRef(0);
  const draftRef = useRef<SettingsFormData | null>(null);
  const saveInFlightRef = useRef(false);
  const queuedDraftRef = useRef<SettingsFormData | null>(null);
  const attemptedDraftRef = useRef<string | null>(null);

  const loadPageData = useEffectEvent(async () => {
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    try {
      if (typeof window.miraDesktop.readSettings !== "function") {
        throw new Error("当前桌面进程版本过旧，请完全关闭并重新打开桌面端。");
      }
      const loaded = await loadSettingsPageData(window.miraDesktop);
      if (loadRequestIdRef.current !== requestId) return;
      setSnapshot(loaded.snapshot);
      setDraft(cloneSettings(loaded.snapshot.formData));
      draftRef.current = cloneSettings(loaded.snapshot.formData);
      queuedDraftRef.current = null;
      attemptedDraftRef.current = null;
      setLoadError("");
      setSavePhase("idle");
      setStatusMessage("");
    } catch (error) {
      if (loadRequestIdRef.current !== requestId) return;
      setLoadError(error instanceof Error ? error.message : String(error));
    }
  });

  useEffect(() => {
    void loadPageData();
  }, []);

  useEffect(() => {
    if (!shouldRetryFailedSettingsLoad({ bridgeReady, loadError })) return;
    void loadPageData();
  }, [bridgeReady, loadError]);

  useEffect(() => () => {
    loadRequestIdRef.current += 1;
  }, []);

  useEffect(() => {
    const timeoutMs = getSettingsFeedbackTimeoutMs(savePhase);
    if (timeoutMs === null) return undefined;
    const timer = window.setTimeout(() => {
      setStatusMessage("");
      setSavePhase((current) => (
        getSettingsFeedbackTimeoutMs(current) === null ? current : "idle"
      ));
    }, timeoutMs);
    return () => window.clearTimeout(timer);
  }, [savePhase]);

  const updateDraft: SettingsDraftUpdater = (mutator) => {
    setDraft((current) => {
      if (!current) return current;
      const nextDraft = mutator(cloneSettings(current));
      draftRef.current = nextDraft;
      return nextDraft;
    });
  };

  const persistDraft = useEffectEvent(async (nextDraft: SettingsFormData) => {
    if (saveInFlightRef.current) {
      queuedDraftRef.current = cloneSettings(nextDraft);
      return;
    }
    if (typeof window.miraDesktop.saveSettings !== "function") {
      setSavePhase("error");
      setStatusMessage("当前桌面进程版本过旧，请完全关闭并重新打开桌面端。");
      return;
    }
    saveInFlightRef.current = true;
    attemptedDraftRef.current = JSON.stringify(nextDraft);
    setSavePhase("saving");
    setStatusMessage("");
    try {
      const result = await saveSettingsPageData(window.miraDesktop, nextDraft);
      setSnapshot(result.snapshot);
      const latestDraft = draftRef.current;
      if (!latestDraft || settingsEqual(latestDraft, nextDraft)) {
        setDraft(result.nextDraft);
        draftRef.current = result.nextDraft;
      }
      if (result.saveResult.ok) {
        setSavePhase("idle");
        setStatusMessage("");
      } else {
        setSavePhase("error");
        setStatusMessage(result.saveResult.health.message || "配置保存后的健康检查失败。");
      }
    } catch (error) {
      setSavePhase("error");
      setStatusMessage(error instanceof Error ? error.message : String(error));
    } finally {
      saveInFlightRef.current = false;
      const queuedDraft = queuedDraftRef.current;
      queuedDraftRef.current = null;
      if (queuedDraft && !settingsEqual(queuedDraft, nextDraft)) {
        void persistDraft(queuedDraft);
      }
    }
  });

  useEffect(() => {
    if (!snapshot || !draft || settingsEqual(snapshot.formData, draft)) return undefined;
    const serializedDraft = JSON.stringify(draft);
    if (attemptedDraftRef.current === serializedDraft) return undefined;
    void persistDraft(cloneSettings(draft));
    return undefined;
  }, [draft, snapshot]);

  return {
    draft,
    loadError,
    savePhase,
    statusMessage,
    updateDraft,
  };
}

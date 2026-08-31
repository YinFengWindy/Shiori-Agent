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
import {
  getSettingsFeedbackTimeoutMs,
  resolveSettingsSaveFeedback,
} from "./settingsSaveState";

const SETTINGS_SAVE_DEBOUNCE_MS = 300;

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
    if (saveInFlightRef.current) return;
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
      const feedback = resolveSettingsSaveFeedback(result.saveResult);
      setSavePhase(feedback.phase);
      setStatusMessage(feedback.message);
    } catch (error) {
      setSavePhase("error");
      setStatusMessage(error instanceof Error ? error.message : String(error));
    } finally {
      saveInFlightRef.current = false;
    }
  });

  useEffect(() => {
    if (!snapshot || !draft || settingsEqual(snapshot.formData, draft)) return undefined;
    const serializedDraft = JSON.stringify(draft);
    if (attemptedDraftRef.current === serializedDraft) return undefined;
    const timer = window.setTimeout(() => {
      void persistDraft(cloneSettings(draft));
    }, SETTINGS_SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [draft, snapshot]);

  return {
    draft,
    loadError,
    savePhase,
    statusMessage,
    updateDraft,
  };
}

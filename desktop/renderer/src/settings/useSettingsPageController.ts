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

type UseSettingsPageControllerArgs = {
  bridgeReady: boolean;
  onMetaChange?: (meta: { configPath: string; dirty: boolean }) => void;
};

/** Owns settings loading, draft mutation, save feedback, and reset behavior. */
export function useSettingsPageController({
  bridgeReady,
  onMetaChange,
}: UseSettingsPageControllerArgs) {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<SettingsFormData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [savePhase, setSavePhase] = useState<SettingsSavePhase>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const loadRequestIdRef = useRef(0);

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
      setLoadError("");
      setSavePhase("idle");
      setStatusMessage("");
    } catch (error) {
      if (loadRequestIdRef.current !== requestId) return;
      setLoadError(error instanceof Error ? error.message : String(error));
    }
  });

  const notifyMetaChange = useEffectEvent((meta: { configPath: string; dirty: boolean }) => {
    onMetaChange?.(meta);
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
    if (!snapshot || !draft) return;
    notifyMetaChange({
      configPath: snapshot.configPath,
      dirty: !settingsEqual(snapshot.formData, draft),
    });
  }, [draft, snapshot]);

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
    setDraft((current) => current ? mutator(cloneSettings(current)) : current);
  };

  async function save(): Promise<void> {
    if (!draft) return;
    if (typeof window.miraDesktop.saveSettings !== "function") {
      setSavePhase("error");
      setStatusMessage("当前桌面进程版本过旧，请完全关闭并重新打开桌面端。");
      return;
    }
    setSavePhase("saving");
    setStatusMessage("正在写入 config.toml...");
    try {
      const result = await saveSettingsPageData(window.miraDesktop, draft);
      setSnapshot(result.snapshot);
      setDraft(result.nextDraft);
      const feedback = resolveSettingsSaveFeedback(result.saveResult);
      setSavePhase(feedback.phase);
      setStatusMessage(feedback.message);
    } catch (error) {
      setSavePhase("error");
      setStatusMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function reset(): void {
    if (!snapshot) return;
    setDraft(cloneSettings(snapshot.formData));
    setStatusMessage("");
    setSavePhase("idle");
  }

  return {
    draft,
    isDirty: Boolean(snapshot && draft && !settingsEqual(snapshot.formData, draft)),
    loadError,
    reset,
    save,
    savePhase,
    statusMessage,
    updateDraft,
  };
}

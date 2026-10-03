import { errorFeedbackText } from "@yinfengwindy/shiori-sdk/host-internal";
import { useCallback, useEffect, useState } from "react";
import type { DesktopUpdateState } from "../../../src/updateContract.js";

/** Subscribes to desktop updates without coupling them to backend settings loading. */
export function useDesktopUpdates() {
  const [state, setState] = useState<DesktopUpdateState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const acceptState = useCallback((next: DesktopUpdateState) => {
    setState((current) => current && current.revision >= next.revision ? current : next);
  }, []);

  useEffect(() => {
    let active = true;
    let receivedEvent = false;
    const unsubscribe = window.miraDesktop.updates.onState((next) => {
      receivedEvent = true;
      acceptState(next);
      setError(null);
    });
    void window.miraDesktop.updates.getState().then((snapshot) => {
      if (active) acceptState(snapshot);
    }).catch((reason: unknown) => {
      if (active && !receivedEvent) setError(errorFeedbackText(reason, "更新状态读取失败"));
    });
    return () => { active = false; unsubscribe(); };
  }, [acceptState]);

  async function runCommand(command: "check" | "install") {
    setError(null);
    try {
      if (command === "check") acceptState(await window.miraDesktop.updates.check());
      else await window.miraDesktop.updates.install();
    } catch (reason) {
      setError(errorFeedbackText(reason, command === "check" ? "检查更新失败" : "更新安装失败"));
    }
  }

  return { state, error: state?.error ?? error, check: () => runCommand("check"), install: () => runCommand("install") };
}

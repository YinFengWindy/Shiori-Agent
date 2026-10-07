import { useState } from "react";
import { compactGhostButtonClass, cx, ManagedRuntimePanel, SettingsField, SettingsGroup, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import type { GptSoVitsSettings } from "../shared/contracts";
import type { useServiceHealth } from "./useServiceHealth";

/** Props of `ServiceStatusGroup`; `disabled` holds every action while the settings are not stored. */
export type ServiceStatusGroupProps = Pick<PluginSettingsSectionComponentProps, "client" | "host"> & {
  mode: GptSoVitsSettings["connection_mode"];
  version: GptSoVitsSettings["version"];
  health: ReturnType<typeof useServiceHealth>;
  disabled: boolean;
};

const valueClass = "text-body-sm text-ink-secondary";

/** The 「服务状态」 group: version, reachability check, quarantine recovery and the managed runtime. */
export function ServiceStatusGroup({ client, host, mode, version, health, disabled }: ServiceStatusGroupProps) {
  const [confirmRestart, setConfirmRestart] = useState(false);
  const status = health.health;
  return <>
    <SettingsGroup title="服务状态">
      <SettingsField label="配置版本"><div className={cx("xl:text-right", valueClass)}>{status?.configured_version ?? version}</div></SettingsField>
      <SettingsField label="连接状态">
        <div className="flex flex-wrap items-center gap-3 xl:justify-end">
          {status ? <span role="status" className={valueClass}>{status.reachable ? "服务可达" : "服务不可达"} · {status.busy ? "正在推理" : "空闲"}</span> : null}
          <button type="button" className={compactGhostButtonClass} disabled={disabled || health.busy} onClick={() => void health.check()}>检查连接</button>
        </div>
      </SettingsField>
      {/* The API cannot prove which weights are loaded, so a check never reports a verified model. */}
      {status ? <SettingsField label="模型身份"><div className={cx("xl:text-right", valueClass)}>未验证</div></SettingsField> : null}
      {status?.recovery_required ? <SettingsField label="推理恢复" layout="stack">
        <host.ui.InlineError
          message={mode === "managed" ? "推理状态异常，请停止后重新启动托管环境。" : "上次推理结果不明，请先重启外部服务。"}
          actions={mode === "external" ? <button type="button" className={compactGhostButtonClass} disabled={disabled || health.busy} onClick={() => setConfirmRestart(true)}>我已重启服务</button> : undefined}
        />
      </SettingsField> : null}
      {mode === "managed" ? <SettingsField label="托管环境" layout="stack">
        <ManagedRuntimePanel client={client} host={host} namespace="gpt_sovits_tts-runtime" importExtensions={["7z", "zip"]} disabled={disabled} />
      </SettingsField> : null}
    </SettingsGroup>
    <host.ui.ConfirmDialog open={confirmRestart} title="确认外部服务已重启？" description="仅在已手动重启 GPT-SoVITS 服务后继续。" confirmLabel="确认已重启" destructive={false} persona={true} onClose={() => setConfirmRestart(false)} onConfirm={() => { setConfirmRestart(false); void health.check(true); }} />
  </>;
}

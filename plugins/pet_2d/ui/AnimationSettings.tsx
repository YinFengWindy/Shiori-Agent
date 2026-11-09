import { useEffect, useState } from "react";
import { compactGhostButtonClass, errorMessage, Select, SettingsField, SettingsGroup, settingsGroupStackClass, settingsInputClass, usePrivateAutosave, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import { animationControls, defaultAnimationSettings, type AnimationCatalog, type AnimationSettings as Settings } from "../shared/animation";

type AnimationSettingsProps = Pick<PluginSettingsSectionComponentProps, "client" | "host"> & { roleId: string };
/** Edits a role's installed models; a hidden model takes the values on its next show. */
export function AnimationSettings(props: AnimationSettingsProps) {
  const { client, host, roleId } = props;
  const [catalog, setCatalog] = useState<AnimationCatalog | null>(null), [selected, setSelected] = useState(""), [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try { const next = await client.background.call<AnimationCatalog>("animation.models", { roleId }); if (active) { setCatalog(next); setError(""); } }
      catch (cause) { if (active) setError(errorMessage(cause)); }
    };
    void load(); return () => { active = false; };
  }, [client, roleId, reload]);
  const models = catalog?.models ?? [];
  const preferred = models.some((model) => model.modelId === catalog?.selectedModelId) ? catalog!.selectedModelId : models[0]?.modelId;
  const modelId = models.some((model) => model.modelId === selected) ? selected : preferred ?? "";
  return <div className={settingsGroupStackClass}>
    {error ? <host.ui.InlineError message={error} actions={<button type="button" className={compactGhostButtonClass} onClick={() => setReload((value) => value + 1)}>重新加载</button>} /> : null}
    <SettingsGroup title="动画调节">
      <SettingsField label="形象" hint={catalog && !models.length ? "请先在角色素材中导入 2.5D 形象" : undefined}>
        <Select aria-label="调整动画的形象" className={settingsInputClass} value={modelId} disabled={!models.length} options={models.map((model) => ({ value: model.modelId, label: model.name }))} onValueChange={setSelected} />
      </SettingsField>
    </SettingsGroup>
    {modelId ? <ModelAnimationEditor key={modelId} {...props} modelId={modelId} /> : null}
  </div>;
}

const groups: { title: string; keys: (keyof Settings)[] }[] = [
  { title: "待机", keys: ["idleSway", "breathing", "motionSpeed"] },
  { title: "眨眼", keys: ["blinkInterval"] },
  { title: "头发物理", keys: ["hairSway", "hairStiffness", "hairDamping"] },
  { title: "口型", keys: ["voiceMouthGain", "faceMouthGain"] },
];

function ModelAnimationEditor({ client, host, roleId, modelId }: AnimationSettingsProps & { modelId: string }) {
  const [previewError, setPreviewError] = useState("");
  const state = usePrivateAutosave<Settings>(client, modelId, {
    load: async () => {
      const settings = await client.background.call<Settings>("animation.get", { roleId, modelId });
      await client.background.call("animation.preview", { roleId, modelId, settings });
      return settings;
    },
    save: (settings) => client.background.call<Settings>("animation.save", { roleId, modelId, settings }),
  });
  const preview = (settings: Settings) => {
    // Send each edited draft before its debounced disk save; a late save must
    // never replace a newer slider position on the running avatar.
    void client.background.call("animation.preview", { roleId, modelId, settings }).then(() => setPreviewError(""), (cause: unknown) => setPreviewError(errorMessage(cause)));
  };
  const change = (key: keyof Settings, value: number) => {
    if (!state.draft) return;
    const next = { ...state.draft, [key]: value };
    state.update(() => next); preview(next);
  };
  const reset = () => { const settings = defaultAnimationSettings(); state.commit(() => settings); preview(settings); };
  return <div className={settingsGroupStackClass}>
    <host.ui.SettingsSavedStatus phase={state.savePhase} />
    {state.loadError ? <host.ui.InlineError message={state.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.reload}>重新加载</button>} /> : null}
    {state.saveError ? <host.ui.InlineError message={state.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.retry}>重试</button>} /> : null}
    {previewError ? <host.ui.InlineError message={previewError} /> : null}
    {state.draft ? <>
      {groups.map((group) => <SettingsGroup key={group.title} title={group.title}>
        {group.keys.map((key) => {
          const spec = animationControls[key], value = state.draft![key];
          return <SettingsField key={key} label={spec.label}>
            <div className="flex items-center gap-3">
              <input aria-label={spec.label} type="range" className="min-w-0 flex-1 accent-accent" min={spec.min} max={spec.max} step={spec.step} value={value} aria-valuetext={`${Number(value.toFixed(2))} ${spec.unit}`} onChange={(event) => change(key, Number(event.target.value))} />
              <output className="w-16 text-right text-body-sm text-ink-secondary tabular-nums">{Number(value.toFixed(2))} {spec.unit}</output>
            </div>
          </SettingsField>;
        })}
      </SettingsGroup>)}
      <button type="button" className={compactGhostButtonClass} onClick={reset}>恢复此形象的默认参数</button>
    </> : null}
  </div>;
}

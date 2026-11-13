import type { PluginBackgroundStore } from "@yinfengwindy/shiori-sdk";
import { isRecord } from "../shared/isRecord";
import type { CapturePreferences } from "../capture/contracts";
import { readAnimationSettings, type AnimationSettings } from "../shared/animation";

/** One serialized owner prevents camera and animation saves overwriting each other. */
export class AvatarPreferences {
  private value: Record<string, unknown>;
  private queue = Promise.resolve();
  constructor(private readonly store: PluginBackgroundStore, stored: unknown) {
    this.value = isRecord(stored) ? stored : {};
  }
  /** Last committed camera preferences, independent of any enabled session. */
  capture(): CapturePreferences {
    const value = isRecord(this.value.capture) ? this.value.capture : {};
    return { deviceId: typeof value.deviceId === "string" ? value.deviceId : "", mirror: value.mirror !== false };
  }
  /** Validates the stored controls of one package, or supplies its defaults. */
  animation(modelId: string): AnimationSettings {
    const models = isRecord(this.value.animation) ? this.value.animation : {};
    return readAnimationSettings(models[modelId] ?? {});
  }
  /** Merges only camera preferences into the latest committed document. */
  saveCapture(capture: CapturePreferences) { return this.update((current) => ({ ...current, capture })); }
  /** Merges one package without erasing another package or camera preferences. */
  saveAnimation(modelId: string, settings: AnimationSettings) {
    return this.update((current) => ({ ...current, animation: { ...(isRecord(current.animation) ? current.animation : {}), [modelId]: settings } }));
  }
  private update(change: (current: Record<string, unknown>) => Record<string, unknown>) {
    const operation = this.queue.then(async () => {
      const next = change(this.value);
      await this.store.write(next);
      this.value = next;
    });
    this.queue = operation.catch(() => {});
    return operation;
  }
}

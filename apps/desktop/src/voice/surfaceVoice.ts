import type { SurfaceVoiceGesture, VoiceStatePayload } from "@yinfengwindy/shiori-sdk/contract";
import type { DesktopSurfaceHost, SurfaceTarget } from "../surface/host.js";
import type { DesktopVoiceController } from "./controller.js";

/** Attributes voice input to a live surface and keeps that owner through awaited work. */
export class SurfaceVoiceController {
  private owner: SurfaceTarget | null = null;

  constructor(
    private readonly surfaces: Pick<DesktopSurfaceHost, "interactionTargets" | "publishVoice">,
    private readonly controller: Pick<DesktopVoiceController, "startPress" | "currentState" | "pointerMoved" | "release" | "cancel">,
  ) {}

  /** Resolve a pointer sender by window identity; no renderer-supplied role is accepted. */
  gesture(windowId: number | null, gesture: SurfaceVoiceGesture): void {
    if (windowId === null) return;
    if (gesture === "press") {
      this.startPress(windowId);
      return;
    }
    if (this.owner?.windowId !== windowId) return;
    if (gesture === "move") this.controller.pointerMoved("surface");
    if (gesture === "release") this.controller.release("surface");
    if (gesture === "cancel") this.controller.cancel("surface");
  }

  /** A hotkey uses the active owner, or the first available surface in creation order. */
  startPress(windowId: number | null = null): boolean {
    const targets = this.surfaces.interactionTargets();
    const target = windowId === null
      ? targets.find((entry) => entry.windowId === this.owner?.windowId) ?? targets[0]
      : targets.find((entry) => entry.windowId === windowId);
    if (!target) return false;
    // Another surface cannot steal a recording or an in-flight reply with a short click.
    if (this.owner && this.owner.windowId !== target.windowId
      && !["idle", "error"].includes(this.controller.currentState.kind)) return false;
    const previous = this.owner;
    this.owner = target;
    const accepted = this.controller.startPress(windowId === null ? "hotkey" : "surface", target.roleId);
    if (!accepted) this.owner = previous;
    else if (previous && previous.windowId !== target.windowId) this.surfaces.publishVoice(previous.windowId, { status: "idle" });
    return accepted;
  }

  /** Target changes and lifecycle loss cancel ASR/chat work before it can be retargeted. */
  revalidate(): void {
    const owner = this.owner;
    if (!owner) return;
    const valid = this.surfaces.interactionTargets().some((target) =>
      target.windowId === owner.windowId && target.roleId === owner.roleId);
    if (valid) return;
    this.controller.cancel();
    this.surfaces.publishVoice(owner.windowId, { status: "idle" });
    this.owner = null;
  }

  /** Deliver controller state only to the window that accepted the press. */
  publish(state: VoiceStatePayload): void {
    if (this.owner) this.surfaces.publishVoice(this.owner.windowId, state);
  }
}

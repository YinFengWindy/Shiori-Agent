import { useEffect, type RefObject } from "react";
import { isRecord } from "../shared/isRecord";
import type { SurfaceHandle } from "@yinfengwindy/shiori-sdk";
import { readAnimationSettings } from "../shared/animation";
import type { AvatarRenderer } from "./runtime/renderer";

/** Shown leases receive current package preferences without rebuilding the model. */
export function useAnimationSettings(surface: SurfaceHandle, leaseId: string, renderer: RefObject<AvatarRenderer | null>) {
  useEffect(() => surface.onMessage((value) => {
    if (!isRecord(value) || value.kind !== "animation.settings" || value.leaseId !== leaseId) return;
    renderer.current?.tune(readAnimationSettings(value.settings));
  }), [leaseId, renderer, surface]);
}

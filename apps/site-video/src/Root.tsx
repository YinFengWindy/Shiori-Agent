import type { ComponentType } from "react";
import { Composition } from "remotion";
import { CLIP_FORMAT, DEMO_CLIPS, type DemoClipId } from "./clips";
import { AffectionClip } from "./clips/AffectionClip";
import { ChannelsClip } from "./clips/ChannelsClip";
import { MemoryClip } from "./clips/MemoryClip";
import { PluginsClip } from "./clips/PluginsClip";
import { ProactiveClip } from "./clips/ProactiveClip";

const CLIP_COMPONENTS: Record<DemoClipId, ComponentType> = {
  memory: MemoryClip,
  affection: AffectionClip,
  proactive: ProactiveClip,
  channels: ChannelsClip,
  plugins: PluginsClip,
};

/** One composition per demo clip (scripts/render.ts renders each). */
export function Root() {
  return (
    <>
      {DEMO_CLIPS.map((clip) => (
        <Composition
          key={clip.id}
          id={clip.id}
          component={CLIP_COMPONENTS[clip.id]}
          durationInFrames={Math.round(clip.seconds * CLIP_FORMAT.fps)}
          {...CLIP_FORMAT}
        />
      ))}
    </>
  );
}

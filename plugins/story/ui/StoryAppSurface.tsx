import type React from "react";

type StoryAppSurfaceProps = {
  children: React.ReactNode;
};

/**
 * Top-level Story application surface, deliberately separate from the desktop
 * chat shell. `scrollbar-native` keeps the platform scrollbar here: Story sits
 * outside the host restyle, so the host's brand scrollbar stops at this root.
 */
export function StoryAppSurface({ children }: StoryAppSurfaceProps) {
  return (
    <section className="scrollbar-native h-screen min-h-0 overflow-hidden text-[#242625]" data-testid="story-app-surface">
      {children}
    </section>
  );
}

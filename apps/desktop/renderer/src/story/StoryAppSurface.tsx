import type React from "react";

type StoryAppSurfaceProps = {
  children: React.ReactNode;
};

/** Top-level Story application surface, deliberately separate from the desktop chat shell. */
export function StoryAppSurface({ children }: StoryAppSurfaceProps) {
  return (
    <section className="h-screen min-h-0 overflow-hidden text-[#242625]" data-testid="story-app-surface">
      {children}
    </section>
  );
}

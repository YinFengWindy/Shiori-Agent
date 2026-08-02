import type React from "react";

type StoryAppSurfaceProps = { children: React.ReactNode };

/** Independent full-window Story surface outside the desktop chat frame. */
export function StoryAppSurface({ children }: StoryAppSurfaceProps) {
  return <section className="h-screen min-h-0 overflow-hidden bg-[#F5F1E9]" data-testid="story-app-surface">{children}</section>;
}

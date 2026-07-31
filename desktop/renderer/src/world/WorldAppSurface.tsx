import type React from "react";

type WorldAppSurfaceProps = {
  children: React.ReactNode;
};

/** Top-level world application surface, deliberately separate from the desktop chat shell. */
export function WorldAppSurface({ children }: WorldAppSurfaceProps) {
  return (
    <section className="h-screen min-h-0 overflow-hidden text-[#242625]" data-testid="world-app-surface">
      {children}
    </section>
  );
}

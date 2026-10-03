import React from "react";
import { brandMotifPaths } from "@yinfengwindy/shiori-sdk/host-internal";
import type { IconProps } from "@yinfengwindy/shiori-sdk";

/** Little-devil wing, lifted from the app icon's hair ornament. Brand motif. */
export function WingIcon({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <path
        d={brandMotifPaths.wing}
        fill="currentColor"
        opacity={0.15}
      />
      <path
        d={brandMotifPaths.wing}
        stroke="currentColor"
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Ribbon bow, echoing the choker in the app icon. Brand motif. */
export function RibbonIcon({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <path
        d={brandMotifPaths.ribbon}
        fill="currentColor"
        opacity={0.15}
      />
      <path
        d={brandMotifPaths.ribbonLeft}
        stroke="currentColor"
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
      <path
        d={brandMotifPaths.ribbonRight}
        stroke="currentColor"
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
      <rect x="10.5" y="10.3" width="3" height="3.4" rx="1.3" stroke="currentColor" strokeWidth={1.7} />
    </svg>
  );
}

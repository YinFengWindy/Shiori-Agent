import { compactButtonSizeClass, cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "../shared/styles";

/** Primary command in a setup card's footer. */
export const onboardingActionClass = cx(primaryButtonSurfaceClass, "inline-flex min-h-10 items-center justify-center gap-2 px-5 py-2 text-body font-medium");

/** Secondary command in a setup card (retry, settings). */
export const onboardingSecondaryClass = cx(ghostButtonSurfaceClass, compactButtonSizeClass);

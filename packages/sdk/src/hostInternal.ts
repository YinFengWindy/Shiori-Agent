/**
 * `@yinfengwindy/shiori-sdk/host-internal`: host-only access to SDK internals that
 * no plugin uses, exposed only so the host and the SDK keep one
 * implementation (the host's own menus, capability badge beside a section
 * switch, mood particles and account status wording share these with the
 * SDK's components and its testing entry's stand-in host components).
 *
 * NOT part of the plugin contract: it is not in the renderer peer ABI or the
 * import map, it may change in any release, and plugin renderer code is
 * barred from importing it by the root ESLint config.
 */
export { RoleCapabilityBadge } from "./components/RoleCapabilityCard";
export { brandMotifPaths, type BrandMotif } from "./icons/brand";
export { menuItemClass, menuItemSelectedClass } from "./menuStyles";
export {
  accountCardActionLabels, accountCardView, accountStatusView,
} from "./account/account";

export { errorFeedback, errorFeedbackText, scrubErrorDetail } from "./errors";

// One serial autosave queue for the host's settings pages and `usePrivateAutosave` (#683).
export { SerialDraftQueue, autosaveDebounceMs, type SerialDraftQueueOptions } from "./serialDraftQueue";

// Host dialog chrome, shared with the SDK's capability settings dialog (#719).
export { compactIconButtonClass, dialogBackdropClass } from "./styles";
export { DialogFrame } from "./components/DialogFrame";

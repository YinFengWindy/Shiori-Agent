/**
 * `@shiori/plugin-sdk/host-internal`: host-only access to SDK internals that
 * no plugin uses, exposed only so the host and the SDK keep one
 * implementation (the host's own menus, capability badge beside a section
 * switch, and mood particles share these with the SDK's components).
 *
 * NOT part of the plugin contract: it is not in the renderer peer ABI or the
 * import map, it may change in any release, and plugin renderer code is
 * barred from importing it by the root ESLint config.
 */
export { RoleCapabilityBadge } from "./components/RoleCapabilityCard";
export { brandMotifPaths, type BrandMotif } from "./icons/brand";
export { menuItemClass, menuItemSelectedClass } from "./menuStyles";

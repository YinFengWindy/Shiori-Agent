/** Accepts function/class components and React's memo/forwardRef/lazy wrappers. */
function isValidElementType(value: unknown) {
  if (typeof value === "function") return true;
  return Boolean(value && typeof value === "object" && "$$typeof" in value &&
    [Symbol.for("react.memo"), Symbol.for("react.forward_ref"), Symbol.for("react.lazy")].includes(value.$$typeof as symbol));
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") throw new Error("Invalid plugin UI contribution");
  return Object.fromEntries(Object.entries(value));
}

function component(value: unknown, field: string) {
  if (!isValidElementType(value)) throw new Error(`Invalid ${field} component`);
}

function label(value: unknown, field: string) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`Invalid ${field} label`);
}

/** Validates the complete UI ABI before mutating any contribution registry. */
export function validateRuntimePluginUi(value: unknown, pluginId: string) {
  const module = object(value);
  if (module.pluginId !== pluginId) throw new Error("Plugin UI identity does not match its admitted package");
  if (module.navPage !== undefined) {
    const page = object(module.navPage);
    component(page.component, "navPage");
    label(page.label, "navPage");
    if (page.icon !== undefined) component(page.icon, "navPage.icon");
    if (page.sidebar !== undefined) component(page.sidebar, "navPage.sidebar");
    if (page.presentation !== undefined && page.presentation !== "workspace" && page.presentation !== "fullscreen") throw new Error("Invalid navPage presentation");
    if (page.selectBlockedReason !== undefined && typeof page.selectBlockedReason !== "function") throw new Error("Invalid navPage selection guard");
  }
  if (module.settingsSection !== undefined) {
    const section = object(module.settingsSection);
    label(section.label, "settingsSection");
    if (section.kind !== "schema" && section.kind !== "component") throw new Error("Invalid settingsSection kind");
    if (section.kind === "component") component(section.component, "settingsSection");
    if (section.subsections !== undefined) {
      if (!Array.isArray(section.subsections)) throw new Error("Invalid settingsSection subsections");
      for (const item of section.subsections) {
        const subsection = object(item);
        label(subsection.id, "subsection.id");
        label(subsection.label, "subsection");
      }
    }
  }
  if (module.roleAssets !== undefined) component(object(module.roleAssets).component, "roleAssets");
  if (module.chatImageActions !== undefined) component(module.chatImageActions, "chatImageActions");
  if (module.roleSettings !== undefined) {
    const settings = object(module.roleSettings);
    component(settings.Component, "roleSettings");
    if ("pluginId" in settings || typeof settings.read !== "function") throw new Error("Invalid roleSettings reader or identity");
    if (settings.storage !== undefined && settings.storage !== "runtime" && settings.storage !== "plugin") throw new Error("Invalid roleSettings storage");
    if (settings.storage !== "plugin" && typeof settings.write !== "function") throw new Error("Invalid roleSettings writer");
    if (settings.afterSave !== undefined && typeof settings.afterSave !== "function") throw new Error("Invalid roleSettings afterSave");
  }
}

import { createPluginSchemaSettingsSection } from "./pluginSchemaSettingsSectionFactory";
import type { PluginSummary } from "./pluginBridgeClient";
import { pluginUiRegistry } from "./pluginUiRegistry";

const PARENT_SECTION_ID = "plugins";

/**
 * Tracks the plugin ids this module itself registered a subtab for, so a
 * later roster refresh can tell "already ours, nothing to do" apart from "a
 * hand-written module claimed this id" without re-deriving that from the
 * registry (which has no origin-reading API on purpose — origin is an
 * internal bookkeeping detail).
 */
const autoRegisteredIds = new Set<string>();

/**
 * Plugin ids this module has already warned about once, for a genuine
 * conflict with a hand-written settings.section — e.g. NovelAI, which
 * legitimately ships both a hand-written `settingsSection` and a
 * `config_model`. That combination is a normal, permanent configuration,
 * not a mistake; without this, every roster refresh (every plugin toggle,
 * every settings apply — via `runtime.applied`) would re-log the same
 * warning forever, training people to ignore it. One warning per id per
 * session stays discoverable for a plugin author who is actually confused
 * about why their auto subtab did not appear, without becoming background
 * noise for the normal case (AC 6 only requires the precedence not be
 * silent, not that it be repeated).
 */
const conflictWarnedIds = new Set<string>();

/**
 * Auto-registers a settings.section subtab, under the built-in 「插件」
 * section, for every roster plugin that declares a config schema
 * (`hasConfigSchema`) but has no hand-written `ui/index.tsx` settings
 * contribution — issue #230 AC 5 (originally issue #228, folded into #230
 * when closed as not-planned; this is the first real implementation).
 *
 * Must run after both the build-time glob (`pluginUiModules.ts`, evaluated
 * at renderer bootstrap) and the runtime synchronization pass
 * (`synchronizeUi` in `pluginEnabledStateStore.ts`) have applied every
 * hand-written `PluginUiModule`, so a hand-written `settingsSection` always
 * wins (AC 6): `registerSettingsSubsection` warns and skips on a duplicate
 * `(parentId, id)` pair rather than overwriting, and this function only
 * ever attempts the id once it finds nothing already registered for it —
 * except when what's already registered is this module's own previous
 * auto-registration, in which case there is nothing to do (not a conflict).
 *
 * Also removes an auto-registered subtab once its plugin drops out of the
 * roster or stops declaring a config schema, through the same
 * `unregisterSettingsSubsection` a hand-written plugin's full unload uses
 * (via `PluginUiRegistry.unregisterPlugin`) — no parallel teardown path.
 */
export function synchronizePluginSettingsAutoRegistration(
  plugins: Array<Pick<PluginSummary, "id" | "name" | "hasConfigSchema">>,
): void {
  // A plugin's own full unload (`unregisterPlugin`) may already have
  // removed this entry from the registry; forget it here too so a later
  // re-registration for the same id is not mistaken for "already ours".
  for (const pluginId of autoRegisteredIds) {
    if (!pluginUiRegistry.getSettingsSubsection(PARENT_SECTION_ID, pluginId)) {
      autoRegisteredIds.delete(pluginId);
    }
  }

  const eligibleIds = new Set(plugins.filter((plugin) => plugin.hasConfigSchema).map((plugin) => plugin.id));
  // A plugin that drops out of the roster or loses its schema is no longer
  // a candidate for auto-registration at all, so forgetting it here means a
  // later, genuinely new conflict for the same id gets its own one-time
  // warning instead of staying silenced by an unrelated past occurrence.
  for (const pluginId of conflictWarnedIds) {
    if (!eligibleIds.has(pluginId)) conflictWarnedIds.delete(pluginId);
  }
  for (const pluginId of autoRegisteredIds) {
    if (!eligibleIds.has(pluginId)) {
      pluginUiRegistry.unregisterSettingsSubsection(PARENT_SECTION_ID, pluginId);
      autoRegisteredIds.delete(pluginId);
    }
  }

  for (const plugin of plugins) {
    if (!plugin.hasConfigSchema || autoRegisteredIds.has(plugin.id)) continue;
    if (pluginUiRegistry.getSettingsSubsection(PARENT_SECTION_ID, plugin.id)) {
      // A hand-written settings.section already claimed this id — it wins,
      // visibly (not a silent overwrite): AC 6. Warned once per id per
      // session, not on every refresh — see conflictWarnedIds above.
      if (!conflictWarnedIds.has(plugin.id)) {
        conflictWarnedIds.add(plugin.id);
        console.warn(`[pluginSettingsAutoRegistration] 插件 "${plugin.id}" 已存在手写 settings.section 子标签，跳过自动注册`);
      }
      continue;
    }
    // Label falls back through the manifest chain the backend already
    // implements (display_name, then the record name, which itself falls
    // back to the plugin id) — see PluginSummary.name / issue #230 AC 5.
    pluginUiRegistry.registerSettingsSubsection({
      slot: "settings.subsection",
      parentId: PARENT_SECTION_ID,
      id: plugin.id,
      label: plugin.name || plugin.id,
      pluginId: plugin.id,
      Component: createPluginSchemaSettingsSection(plugin.id),
    });
    autoRegisteredIds.add(plugin.id);
  }
}

/** Test-only: clears bookkeeping so each test starts from a clean slate. */
export function resetPluginSettingsAutoRegistrationForTests(): void {
  autoRegisteredIds.clear();
  conflictWarnedIds.clear();
}

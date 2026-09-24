import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { PluginManagementSection } from "../plugins/PluginManagementSection";
import { AboutSettingsPage } from "./AboutSettingsPage";
import { AdvancedSettingsSection } from "./AdvancedSettingsSection";
import { ChannelsSettingsSection } from "./ChannelsSettingsSection";
import { MemorySettingsSection } from "./MemorySettingsSection";
import { ModelsSettingsSection } from "./ModelsSettingsSection";
import { VoiceSettingsSection } from "./VoiceSettingsSection";

/** Wraps the standalone About page so it fits the registry's uniform component shape. */
function AboutSection() {
  return <AboutSettingsPage />;
}

let registered = false;

/**
 * Registers the seven built-in settings domains as ordinary registry
 * entries instead of a hand-written switch. This both dynamizes the
 * settings page (a plugin's own settings.section slots into the same list)
 * and gives the slot mechanism a real, always-present consumer. Idempotent
 * so importing it more than once (tests, hot module edge cases) is safe.
 */
export function registerBuiltinSettingsSections(): void {
  if (registered) return;
  registered = true;

  pluginUiRegistry.registerSettingsSection({
    kind: "editor", slot: "settings.section", id: "models", label: "模型",
    subsections: [{ id: "catalog", label: "模型注册" }],
    Component: ModelsSettingsSection,
  }, "builtin");

  pluginUiRegistry.registerSettingsSection({
    kind: "editor", slot: "settings.section", id: "channels", label: "频道",
    // Telegram 已迁为插件，在 设置 › 插件 中配置（#363 T4）。
    subsections: [{ id: "qq", label: "QQ" }],
    Component: ChannelsSettingsSection,
  }, "builtin");

  pluginUiRegistry.registerSettingsSection({
    kind: "editor", slot: "settings.section", id: "memory", label: "记忆",
    subsections: [
      { id: "general", label: "基础" },
      { id: "embedding", label: "Embedding" },
    ],
    Component: MemorySettingsSection,
  }, "builtin");

  pluginUiRegistry.registerSettingsSection({
    kind: "editor", slot: "settings.section", id: "voice", label: "语音",
    subsections: [
      { id: "provider", label: "供应商" },
      { id: "input", label: "输入" },
    ],
    Component: VoiceSettingsSection,
  }, "builtin");

  pluginUiRegistry.registerSettingsSection({
    kind: "editor", slot: "settings.section", id: "advanced", label: "高级",
    subsections: [{ id: "general", label: "基础" }],
    Component: AdvancedSettingsSection,
  }, "builtin");

  pluginUiRegistry.registerSettingsSection({
    kind: "standalone", slot: "settings.section", id: "plugins", label: "插件",
    subsections: [{ id: "list", label: "已安装" }],
    Component: PluginManagementSection,
  }, "builtin");

  pluginUiRegistry.registerSettingsSection({
    kind: "standalone", slot: "settings.section", id: "about", label: "关于",
    subsections: [{ id: "updates", label: "应用更新" }],
    Component: AboutSection,
  }, "builtin");
}

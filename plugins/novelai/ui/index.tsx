import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { NovelAIPage } from "./NovelAIPage";
import { NovelAIPageSidebar } from "./NovelAIPageSidebar";
import { selectBlockedReasonForNovelAiPage } from "./novelAiPageStore";

import { novelAiRoleSettings } from "./roleSettings";
import { NovelAiChatImageActions } from "./ChatImageActions";
import "./novelai.css";

const novelAiLogoDark = new URL(
  "./assets/novelai-logo-dark.svg",
  import.meta.url,
).href;

/** Nav-rail icon: NovelAI's official mark (owner decision: third-party logos stay as they are). */
function NovelAIIcon({ className }: { className?: string }) {
  return <img className={className} src={novelAiLogoDark} alt="" />;
}

/**
 * novelai's plugin UI module (issue #180): Image Studio as a `nav.page`
 * (manual generation with its history filmstrip, and the prompt-tag
 * library), and its
 * settings as an auto-generated `settings.section` form driven by the
 * plugin's own `NovelAIConfig` JSON Schema — the core settings page no
 * longer has any novelai-specific code.
 *
 * `sidebar` (issue #226 gap A) is the workspace navigation in the host's
 * resizable track; `selectBlockedReason` (gap B) refuses navigation with a
 * visible reason (owner decision: 拦住 + 给提示) while no role exists yet.
 * See `novelAiPageStore.ts` and `NovelAIPage.tsx`'s docstrings.
 */
const novelAiUiModule: PluginUiModule = {
  pluginId: "novelai",
  roleSettings: novelAiRoleSettings,
  chatImageActions: NovelAiChatImageActions,
  navPage: {
    label: "生图",
    icon: NovelAIIcon,
    component: NovelAIPage,
    sidebar: NovelAIPageSidebar,
    selectBlockedReason: selectBlockedReasonForNovelAiPage,
  },
  settingsSection: {
    kind: "schema",
    label: "NovelAI",
  },
};

export default novelAiUiModule;

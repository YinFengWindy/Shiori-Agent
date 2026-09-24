import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { ImageStudioGlyph } from "../../../apps/desktop/renderer/src/shared/ui/icons/navGlyphs";
import { NovelAIPage } from "./NovelAIPage";
import { NovelAIPageSidebar } from "./NovelAIPageSidebar";
import { selectBlockedReasonForNovelAiPage } from "./novelAiPageStore";

import { novelAiRoleSettings } from "./roleSettings";
import { NovelAiChatImageActions } from "./ChatImageActions";

/**
 * novelai's plugin UI module (issue #180): Image Studio as a `nav.page`
 * (manual generation, prompt-tag library, generation history), and its
 * settings as an auto-generated `settings.section` form driven by the
 * plugin's own `NovelAIConfig` JSON Schema — the core settings page no
 * longer has any novelai-specific code.
 *
 * `sidebar` and `selectBlockedReason` (issue #226 gaps A/B) restore two
 * behaviours the nav.page slot from #179 couldn't express when Image Studio
 * moved off the desktop shell in #180: a drag-resizable sidebar owned by
 * the host's track, and a nav-rail entry that refuses to navigate (with a
 * visible reason — owner decision: 拦住 + 给提示) while no role exists yet.
 * See `novelAiPageStore.ts` and `NovelAIPage.tsx`'s docstrings.
 */
const novelAiUiModule: PluginUiModule = {
  pluginId: "novelai",
  roleSettings: novelAiRoleSettings,
  chatImageActions: NovelAiChatImageActions,
  navPage: {
    label: "生图",
    // The host's nav glyph (brush + sparkle) so the rail reads as one icon family.
    icon: ImageStudioGlyph,
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

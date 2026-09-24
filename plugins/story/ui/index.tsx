import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { StoryGlyph } from "../../../apps/desktop/renderer/src/shared/ui/icons/navGlyphs";
import { StoryPage } from "./StoryPage";
import "./story.css";

/** Story is a full-window plugin page; backend dependency state controls its visibility. */
const storyUi: PluginUiModule = {
  pluginId: "story",
  navPage: { label: "故事", icon: StoryGlyph, component: StoryPage, presentation: "fullscreen" },
};

export default storyUi;

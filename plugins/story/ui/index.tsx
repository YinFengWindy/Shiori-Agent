import type { PluginUiModule } from "@shiori/sdk";
import { StoryGlyph } from "./StoryGlyph";
import { StoryPage } from "./StoryPage";
import "./story.css";

/** Story is a full-window plugin page; backend dependency state controls its visibility. */
const storyUi: PluginUiModule = {
  pluginId: "story",
  navPage: { label: "故事", icon: StoryGlyph, component: StoryPage, presentation: "fullscreen" },
};

export default storyUi;

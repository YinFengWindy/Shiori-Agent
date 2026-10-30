import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { ScheduleTasksBlock } from "./ScheduleTasksBlock";

/** The scheduled-task block of the chat task panel. */
const scheduleUiModule: PluginUiModule = {
  pluginId: "schedule",
  roleTasks: ScheduleTasksBlock,
};

export default scheduleUiModule;

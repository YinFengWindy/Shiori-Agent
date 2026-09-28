import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { FeishuAccountDetail } from "./FeishuAccountDetail";

/** Feishu/Lark apps are added and managed only from a role's account page. */
const feishuUiModule: PluginUiModule = {
  pluginId: "feishu",
  accountDetail: { label: "飞书 / Lark", component: FeishuAccountDetail },
};

export default feishuUiModule;

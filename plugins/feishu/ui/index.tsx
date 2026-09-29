import { BuildingsIcon } from "@phosphor-icons/react";
import type { PluginUiModule } from "@shiori/plugin-sdk";
import { FeishuAccountDetail } from "./FeishuAccountDetail";

/** Feishu/Lark apps are added and managed only from a role's account page. */
const feishuUiModule: PluginUiModule = {
  pluginId: "feishu",
  accountDetail: { label: "飞书 / Lark", icon: BuildingsIcon, component: FeishuAccountDetail },
};

export default feishuUiModule;

import { usePluginRpcClient } from "./usePluginRpcClient";
import type { ComponentType } from "react";
import { pluginChatImageActionsRegistry, type PluginChatImageActionProps } from "./pluginFeatureRegistry";
import { usePluginEnabledState } from "./usePluginEnabledState";

/** Mounts plugin-authored image actions, removing them when their plugin becomes unavailable. */
export function PluginChatImageActions(props: Omit<PluginChatImageActionProps, "client">) {
  const enabled = usePluginEnabledState();
  return pluginChatImageActionsRegistry.list().filter((entry) => enabled(entry.pluginId)).map((entry) => (
    <PluginImageAction {...props} key={entry.pluginId} pluginId={entry.pluginId} Component={entry.Component} />
  ));
}

function PluginImageAction({ pluginId, Component, ...props }: Omit<PluginChatImageActionProps, "client"> & { pluginId: string; Component: ComponentType<PluginChatImageActionProps> }) {
  const client = usePluginRpcClient(pluginId);
  return <Component {...props} client={client} />;
}

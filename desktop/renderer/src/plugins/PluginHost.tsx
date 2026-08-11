import { Fragment, type ReactNode } from "react";
import type { LoadedPluginManifest, PluginUiContribution, PluginUiSlot } from "../../../src/shared.js";
import { usePluginCatalogContext } from "./PluginCatalogContext";

type PluginHostItem = {
  plugin: LoadedPluginManifest;
  contribution: PluginUiContribution;
};

type PluginHostProps = {
  slot: PluginUiSlot;
  render: (item: PluginHostItem) => ReactNode;
};

/** Mounts loaded plugin contributions into one fixed renderer slot. */
export function PluginHost({ slot, render }: PluginHostProps) {
  const catalog = usePluginCatalogContext();
  return <>{catalog.contributions(slot).map((item) => (
    <Fragment key={`${item.plugin.plugin_id}:${item.contribution.id}`}>
      {render(item)}
    </Fragment>
  ))}</>;
}

/** Reserves a fixed slot while safely ignoring unsupported renderers. */
export function EmptyPluginHost({ slot }: { slot: PluginUiSlot }) {
  return <PluginHost slot={slot} render={() => null} />;
}

import * as React from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as ReactJsx from "react/jsx-runtime";
import * as PluginSdk from "@shiori/plugin-sdk";
import { pluginUiImportMap } from "../../../src/plugins/uiContract";

// One host instance per `pluginUiPeerExports` key; the served peer wrappers re-export these.
const peers = Object.freeze({
  react: React,
  "react/jsx-runtime": ReactJsx,
  "react-dom": ReactDOM,
  "react-dom/client": ReactDOMClient,
  "@shiori/plugin-sdk": PluginSdk,
});
const initialized = new WeakSet<Document>();

/** Install host React and plugin SDK peers once in each UI, background or surface document. */
export function initializeRuntimePluginPeers(document: Document = globalThis.document) {
  if (initialized.has(document)) return;
  const realm = document.defaultView;
  if (!realm) throw new Error("Runtime plugin peers require a window document");
  Object.defineProperty(realm, "__shioriPluginPeers", { value: peers, configurable: false, writable: false });
  const map = document.createElement("script");
  map.type = "importmap";
  map.textContent = pluginUiImportMap;
  document.head.append(map);
  initialized.add(document);
}

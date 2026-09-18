import * as React from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as ReactJsx from "react/jsx-runtime";
import { pluginUiImportMap } from "../../../src/plugins/uiContract";

const peers = Object.freeze({ react: React, "react/jsx-runtime": ReactJsx, "react-dom": ReactDOM, "react-dom/client": ReactDOMClient });
const initialized = new WeakSet<Document>();

/** Install host React peers once in each UI, background or surface document. */
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

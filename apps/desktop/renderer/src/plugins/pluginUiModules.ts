import modules from "virtual:shiori-builtin-plugins/ui";
import { applyPluginUiModules } from "./pluginUiModuleContract";

// Vite generates only built-in entries; installed external UI uses runtime admission.
applyPluginUiModules(modules);

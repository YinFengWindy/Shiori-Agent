import modules from "virtual:shiori-builtin-plugins/background";
import { applyPluginBackgroundModules } from "./pluginBackgroundContract";

// External background entries are loaded from the admitted package at runtime.
applyPluginBackgroundModules(modules);

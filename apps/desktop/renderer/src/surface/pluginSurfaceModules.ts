import modules from "virtual:shiori-builtin-plugins/surface";
import { applyPluginSurfaceModules } from "./pluginSurfaceContract";

// External surface entries are loaded from the admitted package at runtime.
applyPluginSurfaceModules(modules);

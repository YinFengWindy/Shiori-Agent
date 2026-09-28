/**
 * `--import` entry for the desktop unit test processes: registers
 * `test-unit-loader-hooks.mjs` in every `node --test` child before any test
 * file loads.
 */
import { register } from "node:module";

register("./test-unit-loader-hooks.mjs", import.meta.url);

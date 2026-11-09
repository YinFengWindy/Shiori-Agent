import type { HairPins, ImageRect, Layer, Lid } from "./model";

/** Geometry and semantic ownership needed for one draw call. */
export type Mesh = {
  layer: Layer; base: Float32Array; positions: Float32Array; uvs: Float32Array; indices: Uint16Array;
  image: string | { width: number; height: number; pixels: Uint8Array };
  pins?: HairPins; lid?: Lid; part?: "skin" | "rest" | "ink" | "line" | "mouth";
  lineColumns?: number;
};
/** Builds the exact grid shape stored by a hair bake, or a bounded regular image mesh. */
export function imageMesh(layer: Layer, pins?: HairPins): Mesh {
  const detailed = layer.fade === "eyeOpen" || layer.name.startsWith("eye_skin");
  const nx = pins?.nx ?? Math.max(1, Math.round(layer.w / (detailed ? 5 : 42)));
  const ny = pins?.ny ?? Math.max(1, Math.round(layer.h / (detailed ? 5 : 42)));
  const count = (nx + 1) * (ny + 1);
  if (count > 65_000) throw new Error("模型网格超出顶点预算");
  const base = pins ? new Float32Array(pins.rest) : new Float32Array(count * 2), uvs = new Float32Array(count * 2);
  for (let row = 0; row <= ny; row++) for (let col = 0; col <= nx; col++) {
    const index = (row * (nx + 1) + col) * 2;
    if (!pins) { base[index] = layer.x + col / nx * layer.w; base[index + 1] = layer.y + row / ny * layer.h; }
    uvs[index] = col / nx; uvs[index + 1] = row / ny;
  }
  return { layer, base, positions: new Float32Array(base), uvs, indices: gridIndices(nx + 1, ny + 1), image: layer.image, ...(pins ? { pins } : {}) };
}
/** Triangulates a grid without depending on texture coordinates or model format. */
export function gridIndices(columns: number, rows: number): Uint16Array {
  const result = new Uint16Array((columns - 1) * (rows - 1) * 6); let offset = 0;
  for (let row = 0; row < rows - 1; row++) for (let col = 0; col < columns - 1; col++) {
    const top = row * columns + col, bottom = top + columns;
    result.set([top, bottom, top + 1, top + 1, bottom, bottom + 1], offset); offset += 6;
  }
  return result;
}
/** Adds a baked sub-image without changing the owning layer's depth or head transform. */
export function componentLayer(owner: Layer, rectangle: ImageRect, name: string): Layer { return { ...owner, ...rectangle, name, phys: null, synthetic: true }; }

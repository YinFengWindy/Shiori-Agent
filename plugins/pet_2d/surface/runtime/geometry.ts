import geometryLimits from "../../geometry-limits.json";
import type { HairPins, Layer, Lid } from "./model";

/** The same numeric limits are consumed by import validation and renderer allocation. */
export { geometryLimits };

/** Verifies a pixel or grid dimension before arithmetic or typed-array allocation. */
export function geometryDimension(value: number, minimum = 1): number {
  if (!Number.isSafeInteger(value) || value < minimum) throw new Error("模型几何尺寸必须是有限的正整数");
  return value;
}

/** Enforces both the mesh budget and the actual index element width. */
export function meshVertexCount(columns: number, rows: number): number {
  geometryDimension(columns, 2); geometryDimension(rows, 2);
  const count = columns * rows;
  if (!Number.isSafeInteger(count) || count > geometryLimits.maxMeshVertices) throw new Error("模型网格超出顶点预算");
  if (count - 1 > 0xffff) throw new Error("模型网格索引超出 Uint16 范围");
  return count;
}

/** Counts the exact image grid, including baked hair grids, without allocating it. */
export function imageGrid(layer: Layer, pins?: HairPins) {
  geometryDimension(layer.w); geometryDimension(layer.h);
  const step = layer.fade === "eyeOpen" || layer.name.startsWith("eye_skin") ? 5 : 42;
  const nx = pins ? geometryDimension(pins.nx) : Math.max(1, Math.round(layer.w / step));
  const ny = pins ? geometryDimension(pins.ny) : Math.max(1, Math.round(layer.h / step));
  const count = meshVertexCount(nx + 1, ny + 1);
  if (pins && pins.rest.length !== count * 2) throw new Error("头发静止网格尺寸不一致");
  return { nx, ny, count };
}

/** Checks a generated texture before changing a canvas size or allocating pixels. */
export function generatedTextureSize(width: number, height: number) {
  geometryDimension(width); geometryDimension(height);
  const pixels = width * height;
  if (width > geometryLimits.maxGeneratedTextureSide || height > geometryLimits.maxGeneratedTextureSide || !Number.isSafeInteger(pixels) || pixels > geometryLimits.maxGeneratedTexturePixels) throw new Error("生成纹理超出纹理预算");
  return { width, height };
}

/** Derives the contour's four rows and two-row texture with both budgets checked. */
export function lidLineGrid(lid: Pick<Lid, "low" | "high">) {
  if (!Number.isFinite(lid.low) || !Number.isFinite(lid.high) || lid.high <= lid.low) throw new Error("眼睑几何尺寸无效");
  const columns = Math.max(2, Math.ceil(lid.high - lid.low) + 1);
  const count = meshVertexCount(columns, 4);
  generatedTextureSize(columns, 2);
  return { columns, count };
}

/** Uses the fixed supersampling scale shared with the importer. */
export function mouthTextureSize(width: number, height: number) {
  geometryDimension(width); geometryDimension(height);
  return generatedTextureSize(width * geometryLimits.mouthTextureScale, height * geometryLimits.mouthTextureScale);
}

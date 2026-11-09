import { isRecord } from "@yinfengwindy/shiori-pet";

/** An image rectangle in the prepared canvas coordinate system. */
export type ImageRect = { x: number; y: number; w: number; h: number; image: string };
/** Prepared layer data; the baked order and coordinates already contain corrections. */
export type Layer = ImageRect & { name: string; z: number; depth: number; group: "head" | "body"; phys: string | null; fade: string | null; side: "L" | "R" | null; opacity: number; visible: boolean; synthetic: boolean };
/** Fitted eye axis and closed-lid alignment, never re-inferred from pixels. */
export type EyeAnchor = { x0: number; x1: number; y0: number; y1: number; icx: number; icy: number; closeX: number; closeY: number; angle: number };
/** Anchors in corrected, prepared canvas coordinates. */
export type Anchors = { face: { cx: number; cy: number; x0: number; x1: number; y0: number; y1: number }; neck: { cx: number; cy: number }; body: { cx: number; cy: number }; faceScale: number; eyeL: EyeAnchor; eyeR: EyeAnchor; mouth: { cx: number; cy: number } };
/** Baked per-vertex hair constraints on the exact stored grid. */
export type HairPins = { layer: number; nx: number; ny: number; kind: "front" | "back" | "accessory"; strands: { x: number; rootY: number; tipY: number; attachY: number; hang: number; freedom: number; restsOn: "head" | "body" | null }[]; rest: Float32Array; weights: Float32Array; freedom: Float32Array; hang: Float32Array; cap: Float32Array; lo: Float32Array; hi: Float32Array };
/** Fitted lid geometry plus baked skin and lash components. */
export type Lid = { side: "L" | "R"; scale: number; low: number; high: number; lower: number[]; edge: number[]; smile: number[]; rise: number; opening: number; band: number[]; weight: number; colour: number[]; lashes: { layer: number; rest: ImageRect; ink: ImageRect | null }[]; skin: ImageRect | null };
/** Measured parameterized mouth and its articulation bounds. */
export type Mouth = { closed: number; x: number; y: number; w: number; h: number; origin: { x: number; y: number }; angle: number; halfWidth: number; lineWidth: number; restCurve: number; openHeight: number; ink: number[]; cavity: number[]; tongue: number[]; teeth: number[]; openPx: number; reach: { widenPx: number; liftPx: number } | null };
/** Data consumed by the renderer; all model images use host-authorized URLs. */
export type AvatarModel = { width: number; height: number; layers: Layer[]; anchors: Anchors; hair: HairPins[]; lids: Lid[]; mouth: Mouth; images: Map<string, string> };

const versions = { prepared: "prepared-v1-78b039a0f17fac16", mouth: "mouth-v1-49795064767624ca", hair: "hair-v1-2de9459fc64e7fc1", lids: "lids-v1-5f0c2e9a71d4b836" };
/** Rejects unsupported bake semantics instead of silently falling back to uncorrected rig layers. */
export function parseAvatarModel(value: unknown): AvatarModel {
  const source = record(value), manifest = record(source.manifest), binding = record(source.binding), rig = record(source.rig), baked = record(source.baked);
  requireValue(manifest.schema === "prelulu-avatar-package/v1" && binding.schema === "prelulu-avatar-binding/v1" && rig.schema === "prelulu-rig-bundle/v1" && baked.schema === "prelulu-rig-bake/v1", "模型版本不受支持");
  const prepared = record(baked.prepared), mouth = record(baked.mouth), hair = record(baked.hair), lids = record(baked.lids);
  for (const [name, version] of Object.entries(versions)) requireValue(record(baked[name]).version === version, `不支持的 ${name} 预计算版本`);
  const canvas = record(binding.canvas), rigCanvas = record(record(rig.rig).canvas);
  const width = positive(canvas.width), height = positive(canvas.height);
  requireValue(width === rigCanvas.w && height === rigCanvas.h, "画布尺寸不一致");
  const images = new Map<string, string>();
  for (const item of array(source.images)) { const image = record(item); images.set(text(image.file), text(image.url)); }
  const imageRect = (value: unknown): ImageRect => {
    const r = record(value), file = `rig/${text(record(r.image).file)}`;
    requireValue(images.has(file), `缺少模型图片 ${file}`);
    return { x: finite(r.x), y: finite(r.y), w: positive(r.w), h: positive(r.h), image: file };
  };
  const layers = array(prepared.layers).map((value): Layer => {
    const r = record(value);
    requireValue(r.group === "head" || r.group === "body", "图层分组无效");
    const group = r.group;
    const side = r.side === "L" || r.side === "R" ? r.side : null;
    return { ...imageRect(r), name: text(r.name), z: finite(r.z), depth: finite(r.depth), group, phys: nullableText(r.phys), fade: nullableText(r.fade), side, opacity: r.opacity === undefined ? 1 : unit(r.opacity), visible: r.visible !== false, synthetic: r.synthetic === true };
  });
  requireValue(layers.length > 0 && layers.length <= 1000, "图层数量无效");
  const a = record(prepared.anchors), face = record(a.face);
  const point = (value: unknown) => { const p = record(value); return { cx: finite(p.cx), cy: finite(p.cy) }; };
  const eye = (value: unknown): EyeAnchor => { const e = record(value); return { x0: finite(e.x0), x1: finite(e.x1), y0: finite(e.y0), y1: finite(e.y1), icx: finite(e.icx), icy: finite(e.icy), closeX: e.closeX === undefined ? (finite(e.x0) + finite(e.x1)) / 2 : finite(e.closeX), closeY: finite(e.closeY), angle: e.angleRadians === undefined ? 0 : finite(e.angleRadians) }; };
  const anchors: Anchors = { face: { ...point(face), x0: finite(face.x0), x1: finite(face.x1), y0: finite(face.y0), y1: finite(face.y1) }, neck: point(a.neckPivot), body: point(a.bodyPivot), mouth: point(a.mouth), faceScale: positive(a.faceScale), eyeL: eye(a.eyeL), eyeR: eye(a.eyeR) };
  const pins = array(hair.layers).map((value): HairPins => {
    const p = record(value), nx = integer(p.nx), ny = integer(p.ny), layer = integer(p.layer);
    requireValue(p.version === "hair-pins/v3" && nx > 0 && ny > 0 && (nx + 1) * (ny + 1) <= 65_000 && layer < layers.length, "头发网格版本或大小无效");
    requireValue(p.kind === "front" || p.kind === "back" || p.kind === "accessory", "头发绑定类型无效");
    const kind = p.kind;
    const strands = array(p.strands).map((value): HairPins["strands"][number] => { const s = record(value); return { x: finite(s.x), rootY: finite(s.rootY), tipY: finite(s.tipY), attachY: finite(s.attachY), hang: finite(s.hang), freedom: unit(s.freedom), restsOn: s.restsOn === "head" || s.restsOn === "body" ? s.restsOn : null }; });
    requireValue(strands.length > 0, "头发绑定缺少发束");
    const count = (nx + 1) * (ny + 1);
    return { layer, nx, ny, kind, strands, rest: decodeFloat32(p.rest, count * 2), weights: decodeFloat32(p.weights, count * strands.length), freedom: decodeFloat32(p.freedom, count), hang: decodeFloat32(p.hang, count), cap: decodeFloat32(p.cap, count), lo: decodeFloat32(p.lo, count), hi: decodeFloat32(p.hi, count) };
  });
  const eyes = array(lids.eyes).map((value): Lid => {
    const e = record(value), s = record(e.shape); requireValue(e.side === "L" || e.side === "R", "眼睑侧别无效");
    return { side: e.side, scale: positive(s.scale), low: finite(s.low), high: finite(s.high), lower: numbers(s.lower, 3), edge: numbers(s.edge, 3), smile: numbers(s.smile, 3), rise: finite(s.rise), opening: positive(s.opening), band: numbers(s.band, 65), weight: positive(s.weight), colour: numbers(s.colour, 3),
      lashes: array(e.lashes).map((value) => { const lash = record(value), layer = integer(lash.layer); requireValue(layer < layers.length, "眼睑图层不存在"); return { layer, rest: imageRect(lash.rest), ink: lash.ink == null ? null : imageRect(lash.ink) }; }), skin: e.skin == null ? null : imageRect(e.skin) };
  });
  requireValue(record(mouth.choice).renderer === "parametric" && mouth.parametric != null, "不支持该嘴部预计算类型");
  const m = record(mouth.parametric), fit = record(m.fit), style = record(fit.style), origin = record(fit.origin), articulation = record(mouth.articulation), reach = articulation.reach == null ? null : record(articulation.reach);
  const closed = integer(mouth.closed); requireValue(closed < layers.length, "嘴部图层不存在");
  return { width, height, layers, anchors, hair: pins, lids: eyes, images, mouth: { closed, x: finite(m.x), y: finite(m.y), w: positive(m.w), h: positive(m.h), origin: { x: finite(origin.x), y: finite(origin.y) }, angle: finite(fit.angle), halfWidth: positive(style.halfWidth), lineWidth: positive(style.lineWidth), restCurve: finite(style.restCurve), openHeight: positive(style.openHeight), ink: numbers(style.ink, 3), cavity: numbers(style.cavity, 3), tongue: numbers(style.tongue, 3), teeth: numbers(style.teeth, 3), openPx: positive(articulation.openPx), reach: reach ? { widenPx: finite(reach.widenPx), liftPx: finite(reach.liftPx) } : null } };
}

/** Decodes bounded little-endian float buffers independently of host byte order. */
export function decodeFloat32(value: unknown, count: number): Float32Array {
  const encoded = text(value); requireValue(encoded.length <= Math.ceil(count * 4 / 3) * 4 + 4, "预计算缓冲区过大");
  const decoded = atob(encoded); requireValue(decoded.length === count * 4, "预计算缓冲区长度错误");
  const bytes = Uint8Array.from(decoded, (char) => char.charCodeAt(0)); const view = new DataView(bytes.buffer), result = new Float32Array(count);
  for (let i = 0; i < count; i++) result[i] = finite(view.getFloat32(i * 4, true));
  return result;
}
/** Shared JSON boundary checks within the 2.5D provider. */
export function record(value: unknown): Record<string, unknown> { requireValue(isRecord(value), "模型数据必须为对象"); return value; }
/** Validates collection-shaped model data. */
export function array(value: unknown): unknown[] { requireValue(Array.isArray(value), "模型数据必须为数组"); return value; }
/** Validates numeric coordinates and dimensions without coercion. */
export function finite(value: unknown): number { requireValue(typeof value === "number" && Number.isFinite(value), "模型数值无效"); return value; }
/** Validates nonempty identifiers or asset paths. */
export function text(value: unknown): string { requireValue(typeof value === "string" && value.length > 0, "模型文本字段无效"); return value; }
function positive(value: unknown) { const n = finite(value); requireValue(n > 0 && n <= 16_384, "模型尺寸无效"); return n; }
function integer(value: unknown) { const n = finite(value); requireValue(Number.isInteger(n) && n >= 0, "模型索引无效"); return n; }
function unit(value: unknown) { const n = finite(value); requireValue(n >= 0 && n <= 1, "模型比例无效"); return n; }
function nullableText(value: unknown) { return value == null ? null : text(value); }
function numbers(value: unknown, count: number) { const a = array(value); requireValue(a.length === count, "模型数组长度无效"); return a.map(finite); }
function requireValue(condition: unknown, message: string): asserts condition { if (!condition) throw new Error(message); }

import type { AvatarModel, HairPins, Layer, Lid } from "./model";
import { componentLayer, imageMesh, type Mesh } from "./mesh";
import { clamp, deformLid, lidLineMesh, lidLinePoint, smooth } from "./lids";
import { createHairMotion, hairDisplacement, stepHair } from "./hair";
import { geometryLimits, imageGrid, lidLineGrid, mouthTextureSize } from "./geometry";

type ScenePart = { kind: "image"; layer: Layer; pins?: HairPins; lid?: Lid; part?: Mesh["part"] } | { kind: "line"; layer: Layer; lid: Lid };

/** Resolves each prepared correction and baked replacement into ordered render meshes. */
export function createScene(model: AvatarModel): Mesh[] {
  const hair = new Map(model.hair.map((pins) => [pins.layer, pins])), plan: ScenePart[] = [];
  for (let index = 0; index < model.layers.length; index++) {
    const layer = model.layers[index];
    const lid = model.lids.find((item) => item.side === layer.side);
    if (index !== model.mouth.closed && layer.fade !== "mouthClose" && layer.fade !== "mouthOpen") plan.push({
      kind: "image", layer, pins: hair.get(index),
      ...(lid && (layer.fade === "eyeOpen" || layer.fade === "eyeClose" || layer.fade === "eyeClose2") ? { lid } : {}),
    });
    if (layer.name === "face") for (const eye of model.lids) if (eye.skin) {
      plan.push({ kind: "image", layer: { ...componentLayer(layer, eye.skin, `eye_skin_${eye.side}`), side: eye.side }, part: "skin", lid: eye });
    }
    if (index === model.mouth.closed) {
      const mouth = model.mouth;
      plan.push({ kind: "image", layer: { ...layer, ...mouth, name: "parametric_mouth", image: "", phys: null, fade: null, side: null }, part: "mouth" });
    }
    const lash = lid?.lashes.find((item) => item.layer === index);
    if (lid && lash) {
      plan.push({ kind: "image", layer: componentLayer(layer, lash.rest, `${layer.name}:rest`), part: "rest", lid });
      plan.push({ kind: "line", layer, lid });
      if (lash.ink) plan.push({ kind: "image", layer: componentLayer(layer, lash.ink, `${layer.name}:ink`), part: "ink", lid });
    }
  }
  // Budget the final render list before allocating any derived vertex, index or
  // pixel buffer. Discarded source mouth layers never allocate temporary meshes.
  mouthTextureSize(model.mouth.w, model.mouth.h);
  let total = 0;
  for (const item of plan) {
    total += item.kind === "line" ? lidLineGrid(item.lid).count : imageGrid(item.layer, item.pins).count;
    if (total > geometryLimits.maxTotalVertices) throw new Error("模型场景超出总顶点预算");
  }
  return plan.map((item) => {
    if (item.kind === "line") return lidLineMesh(item.layer, item.lid, item.lid.side === "L" ? model.anchors.eyeL : model.anchors.eyeR);
    const mesh = imageMesh(item.layer, item.pins);
    if (item.lid) mesh.lid = item.lid;
    if (item.part) mesh.part = item.part;
    return mesh;
  });
}

/** Tracks motion separately from immutable package data. */
export function createSceneMotion(meshes: Mesh[]) { return meshes.map((mesh) => mesh.pins ? createHairMotion(mesh.pins) : null); }
/** Neutral blend opacity uses baked eyelid parts rather than generic closed-eye sprites. */
export function meshOpacity(mesh: Mesh, openness: number): number {
  if (!mesh.layer.visible) return 0;
  let alpha = 1;
  if (mesh.lid) {
    if (mesh.part === "skin") alpha = smooth((1 - openness) / 0.2);
    else if (mesh.part === "ink" || mesh.part === "line") alpha = openness < 0.999 ? 1 : 0;
    else if (mesh.part === "rest") alpha = openness < 0.999 ? smooth((openness - 0.35) / 0.5) : 0;
    else if (baseName(mesh.layer.name) === "eyelash") alpha = openness < 0.999 ? 0 : 1;
    else if (mesh.layer.fade === "eyeClose" || mesh.layer.fade === "eyeClose2") alpha = 0;
    else if (mesh.layer.fade === "eyeOpen") alpha = smooth((openness - 0.02) / 0.18);
  }
  return alpha * mesh.layer.opacity;
}
/** Deterministic blink with a short closed interval and slower reopening. */
export function eyeOpenness(seconds: number): number {
  const phase = seconds % 4.1; if (phase < 3.65) return 1;
  if (phase < 3.76) return 1 - smooth((phase - 3.65) / 0.11);
  if (phase < 3.81) return 0;
  return smooth((phase - 3.81) / 0.24);
}
/** Applies local eyelids, constrained hair and coherent breathing/head motion to the meshes. */
export function animateScene(model: AvatarModel, meshes: Mesh[], motion: ReturnType<typeof createSceneMotion>, seconds: number, elapsed: number, reduced: boolean, mouthOpen: number): number {
  const openness = reduced ? 1 : eyeOpenness(seconds), anchors = model.anchors;
  const breath = reduced ? 0 : 0.5 + 0.5 * Math.sin(seconds * Math.PI * 2 / 3.4), headBreath = reduced ? 0 : 0.5 + 0.5 * Math.sin(seconds * Math.PI * 2 / 3.4 - 0.6);
  const roll = reduced ? 0 : 0.012 * Math.sin(seconds * 0.71), yaw = reduced ? 0 : 2.5 * Math.sin(seconds * 0.47);
  for (let index = 0; index < meshes.length; index++) {
    const mesh = meshes[index], name = baseName(mesh.layer.name), springs = motion[index];
    if (springs) stepHair(springs, seconds, elapsed, anchors.faceScale, !reduced);
    const eye = mesh.lid?.side === "L" ? anchors.eyeL : anchors.eyeR;
    for (let at = 0; at < mesh.base.length; at += 2) {
      let x = mesh.base[at], y = mesh.base[at + 1]; const vertex = at / 2;
      if (mesh.part === "line" && mesh.lid && mesh.lineColumns) {
        const column = vertex % mesh.lineColumns, row = Math.floor(vertex / mesh.lineColumns), u = mesh.lid.low + (mesh.lid.high - mesh.lid.low) * column / (mesh.lineColumns - 1);
        [x, y] = lidLinePoint(mesh.lid, eye, u, row, openness);
      } else if (mesh.lid && mesh.layer.fade === "eyeOpen" && mesh.part !== "rest" && name !== "irides") [x, y] = deformLid(mesh.lid, eye, x, y, openness, mesh.part === "ink");
      if (mesh.pins && springs) { const delta = hairDisplacement(mesh.pins, springs, vertex); x += delta[0]; y += delta[1]; }
      if (name === "face" && y > anchors.mouth.cy) y += mouthOpen * 3.3 * anchors.faceScale * smooth((y - anchors.mouth.cy) / Math.max(1, anchors.face.y1 - anchors.mouth.cy));
      if (mesh.layer.group === "head") {
        const dx = x - anchors.neck.cx, dy = y - anchors.neck.cy;
        x = anchors.neck.cx + dx * Math.cos(roll) - dy * Math.sin(roll) + yaw * mesh.layer.depth;
        y = anchors.neck.cy + dx * Math.sin(roll) + dy * Math.cos(roll) - headBreath * 1.6 * anchors.faceScale;
      } else {
        const influence = clamp((anchors.body.cy - y) / Math.max(1, anchors.body.cy - anchors.neck.cy));
        x += yaw * 0.16 * influence; y -= breath * 2 * anchors.faceScale * influence;
        if (name === "neck") { const weight = smooth((anchors.neck.cy - y) / Math.max(1, anchors.neck.cy - anchors.face.cy)); x += yaw * weight; }
        if (name === "topwear") x = anchors.neck.cx + (x - anchors.neck.cx) * (1 + breath * 0.003);
      }
      mesh.positions[at] = x; mesh.positions[at + 1] = y;
    }
  }
  return openness;
}
/** Normalizes upstream layer suffixes only for existing semantic layer classes. */
export function baseName(name: string): string { return name.replace(/_(l|r)$/, "").replace(/_\d+$/, ""); }

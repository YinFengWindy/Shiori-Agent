import type { Mesh } from "./mesh";
import { baseName, meshOpacity } from "./scene";

type GpuMesh = { vertex: WebGLBuffer; uv: WebGLBuffer; indices: WebGLBuffer; texture: WebGLTexture; count: number };
const vertexShader = `attribute vec2 position; attribute vec2 texcoord; uniform vec2 canvasSize; varying vec2 uv;
void main(){ uv=texcoord; gl_Position=vec4(position.x/canvasSize.x*2.0-1.0,1.0-position.y/canvasSize.y*2.0,0.0,1.0); }`;
const fragmentShader = `precision mediump float; uniform sampler2D image; uniform float opacity; varying vec2 uv;
void main(){ vec4 pixel=texture2D(image,uv); float alpha=pixel.a*opacity; if(alpha<0.004) discard; gl_FragColor=vec4(pixel.rgb,alpha); }`;

/** GPU resources for a single canvas; transparent compositing and eye masks stay local. */
export class AvatarWebGL {
  private readonly gl: WebGLRenderingContext;
  private readonly program: WebGLProgram;
  private readonly meshes: GpuMesh[] = [];
  private readonly position: number;
  private readonly uv: number;
  private readonly opacity: WebGLUniformLocation;
  private disposed = false;
  constructor(private readonly canvas: HTMLCanvasElement, width: number, height: number) {
    const gl = canvas.getContext("webgl", { alpha: true, antialias: true, premultipliedAlpha: true, stencil: true });
    if (!gl) throw new Error("当前设备无法创建 2.5D WebGL 画布");
    this.gl = gl;
    const program = gl.createProgram(); if (!program) throw new Error("无法创建模型绘图程序"); this.program = program;
    const shaders: WebGLShader[] = [];
    try {
      for (const [kind, source] of [[gl.VERTEX_SHADER, vertexShader], [gl.FRAGMENT_SHADER, fragmentShader]] as const) {
        const shader = gl.createShader(kind); if (!shader) throw new Error("无法创建模型着色器"); shaders.push(shader);
        gl.shaderSource(shader, source); gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || "模型着色器编译失败");
        gl.attachShader(program, shader);
      }
      gl.linkProgram(program); if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || "模型绘图程序连接失败");
      gl.useProgram(program); this.position = gl.getAttribLocation(program, "position"); this.uv = gl.getAttribLocation(program, "texcoord");
      const opacity = gl.getUniformLocation(program, "opacity"); if (!opacity) throw new Error("模型着色器参数缺失"); this.opacity = opacity;
      gl.uniform2f(gl.getUniformLocation(program, "canvasSize"), width, height); gl.uniform1i(gl.getUniformLocation(program, "image"), 0);
      gl.enable(gl.BLEND); gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    } catch (error) { gl.deleteProgram(program); throw error; }
    finally { for (const shader of shaders) gl.deleteShader(shader); }
  }
  /** Uploads a loaded image and its preallocated mesh, reclaiming partial allocations on failure. */
  add(mesh: Mesh, image: HTMLImageElement | HTMLCanvasElement | { width: number; height: number; pixels: Uint8Array }) {
    const gl = this.gl, allocated: WebGLBuffer[] = []; let texture: WebGLTexture | null = null;
    const buffer = (target: number, data: Float32Array | Uint16Array, usage: number) => { const result = gl.createBuffer(); if (!result) throw new Error("模型网格分配失败"); allocated.push(result); gl.bindBuffer(target, result); gl.bufferData(target, data, usage); return result; };
    try {
      const vertex = buffer(gl.ARRAY_BUFFER, mesh.positions, gl.DYNAMIC_DRAW), uv = buffer(gl.ARRAY_BUFFER, mesh.uvs, gl.STATIC_DRAW), indices = buffer(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, gl.STATIC_DRAW);
      texture = gl.createTexture(); if (!texture) throw new Error("模型纹理分配失败"); gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      if ("pixels" in image) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, image.width, image.height, 0, gl.RGBA, gl.UNSIGNED_BYTE, image.pixels);
      else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      if (gl.getError() !== gl.NO_ERROR) throw new Error("模型纹理或网格上传失败");
      this.meshes.push({ vertex, uv, indices, texture, count: mesh.indices.length });
    } catch (error) { for (const buffer of allocated) gl.deleteBuffer(buffer); if (texture) gl.deleteTexture(texture); throw error; }
  }
  /** Replaces only the small mouth texture when its measured amplitude changes. */
  mouth(index: number, canvas: HTMLCanvasElement) { const gl = this.gl; gl.bindTexture(gl.TEXTURE_2D, this.meshes[index].texture); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvas); }
  /** Renders corrected layers in their prepared order and clips each iris to its eye white. */
  draw(meshes: Mesh[], openness: number) {
    if (this.disposed) return;
    const gl = this.gl; gl.viewport(0, 0, this.canvas.width, this.canvas.height); gl.clearColor(0, 0, 0, 0); gl.stencilMask(0xff); gl.clear(gl.COLOR_BUFFER_BIT | gl.STENCIL_BUFFER_BIT);
    for (let index = 0; index < meshes.length; index++) { gl.bindBuffer(gl.ARRAY_BUFFER, this.meshes[index].vertex); gl.bufferSubData(gl.ARRAY_BUFFER, 0, meshes[index].positions); }
    gl.enable(gl.STENCIL_TEST); gl.colorMask(false, false, false, false);
    for (let index = 0; index < meshes.length; index++) {
      const mesh = meshes[index]; if (baseName(mesh.layer.name) !== "eyewhite" || !mesh.layer.side) continue;
      gl.stencilFunc(gl.ALWAYS, mesh.layer.side === "L" ? 1 : 2, 0xff); gl.stencilOp(gl.KEEP, gl.KEEP, gl.REPLACE); this.drawMesh(index, meshOpacity(mesh, openness));
    }
    gl.colorMask(true, true, true, true); gl.stencilMask(0); gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
    for (let index = 0; index < meshes.length; index++) {
      const mesh = meshes[index], alpha = meshOpacity(mesh, openness); if (alpha < 0.004) continue;
      if (baseName(mesh.layer.name) === "irides") { gl.enable(gl.STENCIL_TEST); gl.stencilFunc(gl.EQUAL, mesh.layer.side === "L" ? 1 : 2, 0xff); }
      else gl.disable(gl.STENCIL_TEST);
      this.drawMesh(index, alpha);
    }
    gl.disable(gl.STENCIL_TEST); gl.flush();
  }
  /** Deletes every GPU allocation on failure, switch, hide or plugin unload. */
  dispose() { if (this.disposed) return; this.disposed = true; const gl = this.gl; for (const mesh of this.meshes) { gl.deleteBuffer(mesh.vertex); gl.deleteBuffer(mesh.uv); gl.deleteBuffer(mesh.indices); gl.deleteTexture(mesh.texture); } this.meshes.length = 0; gl.deleteProgram(this.program); }
  private drawMesh(index: number, alpha: number) {
    const gl = this.gl, mesh = this.meshes[index]; gl.uniform1f(this.opacity, alpha);
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.vertex); gl.enableVertexAttribArray(this.position); gl.vertexAttribPointer(this.position, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.uv); gl.enableVertexAttribArray(this.uv); gl.vertexAttribPointer(this.uv, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.indices); gl.bindTexture(gl.TEXTURE_2D, mesh.texture); gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_SHORT, 0);
  }
}

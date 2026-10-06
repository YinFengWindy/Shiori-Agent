import assert from "node:assert/strict";
import { access } from "node:fs/promises";
import { createServer, type ServerResponse } from "node:http";
import { record } from "./packagedEvidence";
import { speechWav } from "./distributionSpeechFixtures";

/** Observable external protocol requests; no plugin or chat implementation is replaced. */
export type SpeechRequest = { path: string; body: Record<string, unknown>; at: number };

/** Loopback protocol doubles for ASR, GPT-SoVITS and OpenAI-compatible chat. */
export class SpeechServer {
  readonly requests: SpeechRequest[] = [];
  readonly audioResponses: Array<{ index: number; audioBase64: string; at: number }> = [];
  readonly failures: string[] = [];
  private releases: Array<() => void> = [];
  private readonly server = createServer((request, response) => {
    void (async () => {
      const chunks: Buffer[] = [];
      for await (const chunk of request) chunks.push(Buffer.from(chunk));
      const bytes = Buffer.concat(chunks), url = new URL(request.url!, "http://127.0.0.1");
      if (url.pathname === "/health") return this.json(response, { status: "ok", device: "cpu", models_loaded: ["sensevoice"] });
      if (url.pathname === "/openapi.json") return this.json(response, { paths: { "/tts": {}, "/set_gpt_weights": {}, "/set_sovits_weights": {} } });
      if (url.pathname === "/v1/audio/transcriptions") {
        assert.match(request.headers["content-type"] ?? "", /multipart/);
        const wavOffset = bytes.indexOf(Buffer.from("RIFF")); assert.ok(wavOffset >= 0 && bytes.includes(Buffer.from("sensevoice")));
        assert.equal(bytes.readUInt32LE(wavOffset + 24), 16_000);
        assert.equal(bytes.readUInt16LE(wavOffset + 22), 1);
        const pcmBytes = bytes.readUInt32LE(wavOffset + 40); assert.ok(pcmBytes > 4_000);
        assert.ok(bytes.subarray(wavOffset + 44, wavOffset + 44 + pcmBytes).some((byte) => byte !== 0), "Capture returned silence");
        const text = `语音组合测试第${this.count(url.pathname) + 1}轮`;
        this.requests.push({ path: url.pathname, body: { text, pcmBytes, sampleRate: 16_000 }, at: Date.now() });
        return this.json(response, { text });
      }
      if (url.pathname.startsWith("/set_")) return this.json(response, { message: "success" });
      const body = record(JSON.parse(bytes.toString("utf8")));
      this.requests.push({ path: url.pathname, body, at: Date.now() });
      if (url.pathname === "/v1/chat/completions") return this.chat(response, body);
      assert.equal(url.pathname, "/tts");
      await access(String(body.ref_audio_path));
      assert.equal(body.streaming_mode, false); assert.equal(body.media_type, "wav");
      // The second real synthesis holds its HTTP response until the test releases it.
      const index = this.count("/tts");
      if (index === 2) await new Promise<void>((done) => this.releases.push(done));
      const audio = speechWav(8, 330 + index * 55);
      this.audioResponses.push({ index, audioBase64: audio.toString("base64"), at: Date.now() });
      response.writeHead(200, { "Content-Type": "audio/wav", "Content-Length": audio.length }); response.end(audio);
    })().catch((error: unknown) => {
      this.failures.push(String(error)); response.writeHead(500); response.end(String(error));
    });
  });

  async start() {
    await new Promise<void>((done) => this.server.listen(0, "127.0.0.1", done));
    const address = this.server.address(); assert.ok(address && typeof address === "object");
    return `http://127.0.0.1:${address.port}`;
  }
  count(path: string) { return this.requests.filter((request) => request.path === path).length; }
  release() { for (const done of this.releases.splice(0)) done(); }
  async close() { this.release(); this.server.closeAllConnections(); await new Promise<void>((done) => this.server.close(() => done())); }
  private json(response: ServerResponse, value: unknown) { response.writeHead(200, { "Content-Type": "application/json" }); response.end(JSON.stringify(value)); }
  private chat(response: ServerResponse, body: Record<string, unknown>) {
    const messages = body.messages; assert.ok(Array.isArray(messages));
    const texts = messages.map((message) => String(record(message).content ?? ""));
    let content: string;
    if (texts[0].includes("首版 SELF.md")) content = "# 我是谁\n\n## 我的性格与形象\n我愿意认真倾听。\n\n## 我对你的理解\n我正在认识你。\n\n## 我们的关系\n我们刚刚相识。";
    else if (record(body.response_format ?? {}).type === "json_object") content = JSON.stringify({ mood: "happy", thought: "我听到了你的问候，想认真回应。" });
    else {
      assert.ok(texts.some((text) => text.includes("语音组合测试第")), "Unexpected model request");
      const turn = this.count("/v1/audio/transcriptions");
      content = `这是第${turn}轮回复。` + (turn === 1 ? "这句话应该在手动停止后从队列丢弃。" : "");
    }
    const common = { id: `fixture-${this.count("/v1/chat/completions")}`, created: 1, model: "speech-fixture" };
    const usage = { prompt_tokens: 100, completion_tokens: 30, total_tokens: 130 };
    if (!body.stream) return this.json(response, { ...common, object: "chat.completion", choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }], usage });
    response.writeHead(200, { "Content-Type": "text/event-stream" });
    for (const delta of [{ role: "assistant" }, { content }]) response.write(`data: ${JSON.stringify({ ...common, object: "chat.completion.chunk", choices: [{ index: 0, delta, finish_reason: null }] })}\n\n`);
    response.write(`data: ${JSON.stringify({ ...common, object: "chat.completion.chunk", choices: [{ index: 0, delta: {}, finish_reason: "stop" }], usage })}\n\n`);
    response.end("data: [DONE]\n\n");
  }
}

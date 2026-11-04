import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { Buffer } from "node:buffer";
import console from "node:console";
import process from "node:process";
import { cp, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve, relative, sep } from "node:path";
import { fileURLToPath, URL } from "node:url";
import { parseArgs } from "node:util";
import { collectPluginBackendModules } from "./runtime-plugin-modules.mjs";
import { createRuntimePyinstallerArgs } from "./runtime-pyinstaller.mjs";
import { preparePyinstallerInvocation } from "./pyinstaller-invocation.mjs";

const repository = fileURLToPath(new URL("../../../", import.meta.url));
const { values } = parseArgs({ options: { output: { type: "string" }, python: { type: "string" } } });
const output = values.output ? resolve(values.output) : await mkdtemp(join(tmpdir(), "shiori-mcp-runtime-"));
await mkdir(output, { recursive: true });
const python = values.python ? resolve(values.python) : join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const stagingRoot = join(output, "staging");
const stagedPluginsDir = join(stagingRoot, "plugins");
const source = join(repository, "plugins/mcp");
await cp(source, join(stagedPluginsDir, "mcp"), {
  recursive: true,
  filter: (path) => !["tests", "build"].includes(relative(source, path).split(sep)[0]) && basename(path) !== "__pycache__",
});
const native = join(output, "native");
await mkdir(native, { recursive: true });
const entry = join(output, "mcp_runtime_probe.py");
await writeFile(entry, `import asyncio
import importlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from threading import Thread

assert getattr(sys, "frozen", False)
root = Path(sys._MEIPASS).resolve()
for name in ("plugins.mcp.backend.plugin", "plugins.mcp.backend.http_session", "mcp.client.streamable_http", "mcp_types"):
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(root), name
versions = {name: version(name) for name in ("shiori-plugin-mcp", "mcp", "mcp-types", "httpx2", "httpcore2")}
assert versions["mcp"] == "2.3.0", versions

class Peer(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "id" not in request:
            self.send_response(202); self.end_headers(); return
        method = request["method"]
        if method == "server/discover":
            result = {"error": {"code": -32601, "message": "Legacy fixture"}}
        elif method == "initialize":
            result = {"result": {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "frozen-probe", "version": "1"}}}
        elif method == "tools/list":
            result = {"result": {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}}
        else:
            result = {"result": {"content": [{"type": "text", "text": "frozen-http-ok"}]}}
        body = json.dumps({"jsonrpc": "2.0", "id": request["id"], **result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

async def probe():
    from plugins.mcp.backend.http_session import HttpMcpSession
    from plugins.mcp.backend.models import HttpTransport, LaunchCredentials
    server = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    session = HttpMcpSession("frozen", HttpTransport(), LaunchCredentials(url=f"http://127.0.0.1:{server.server_port}/mcp"))
    try:
        assert [tool.name for tool in await session.connect()] == ["echo"]
        assert await session.call("echo", {}) == "frozen-http-ok"
    finally:
        await session.disconnect()
        server.shutdown(); server.server_close(); thread.join()

asyncio.run(probe())
print(json.dumps({"frozen": True, "http_call": "passed", "versions": versions}))
`, "utf8");
const pluginModules = await collectPluginBackendModules(stagedPluginsDir);
const args = createRuntimePyinstallerArgs({
  runtimeRoot: join(output, "dist"), workRoot: join(output, "build"), backendRoot: join(repository, "apps/backend"),
  stagingRoot, stagedPluginsDir, browserRuntime: native, computerRuntime: native,
  repositoryRoot: repository, pluginModules, hostModules: [], sdkModules: [],
});
// Keep the production collection/metadata flags; replace only the executable entry
// so this focused probe needs no roles, model credentials or native UI runtimes.
args[args.length - 1] = entry;
await writeFile(join(output, "collection.json"), JSON.stringify({ pluginModules, args }, null, 2), "utf8");

async function run(executable, argv, log, env = process.env) {
  const child = spawn(executable, argv, { cwd: output, env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  const chunks = [];
  child.stdout.on("data", (chunk) => chunks.push(chunk));
  child.stderr.on("data", (chunk) => chunks.push(chunk));
  const code = await new Promise((done, reject) => { child.once("error", reject); child.once("exit", done); });
  await writeFile(join(output, log), Buffer.concat(chunks));
  assert.equal(code, 0, `MCP runtime probe failed: ${join(output, log)}`);
}

console.log(`Freezing builtin MCP through production collection. Evidence: ${output}`);
const invocation = await preparePyinstallerInvocation(args, join(output, "invocation"));
await run(python, invocation.pythonArgs, "freeze.log");
const env = { ...process.env };
delete env.PYTHONPATH;
delete env.PYTHONHOME;
await run(join(output, "dist/shiori-runtime", process.platform === "win32" ? "shiori-runtime.exe" : "shiori-runtime"), [], "probe.json", env);
console.log(await readFile(join(output, "probe.json"), "utf8"));

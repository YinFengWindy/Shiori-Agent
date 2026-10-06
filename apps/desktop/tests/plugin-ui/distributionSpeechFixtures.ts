import { execFileSync } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";

/** Generate audible PCM fixtures without a microphone, model, or downloaded asset. */
export function speechWav(seconds: number, frequency = 440) {
  const count = Math.floor(16_000 * seconds), data = Buffer.alloc(44 + count * 2);
  data.write("RIFF"); data.writeUInt32LE(data.length - 8, 4); data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(16_000, 24); data.writeUInt32LE(32_000, 28); data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34);
  data.write("data", 36); data.writeUInt32LE(count * 2, 40);
  for (let index = 0; index < count; index++) data.writeInt16LE(Math.round(1200 * Math.sin(index * 2 * Math.PI * frequency / 16_000)), 44 + index * 2);
  return data;
}

/** Build a valid pet package with every required frame, using only the repository Python environment. */
export async function speechAssets(repository: string, output: string) {
  const reference = resolve(output, "reference.wav"), pet = resolve(output, "pet.zip");
  await writeFile(reference, speechWav(3.2));
  const python = resolve(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  execFileSync(python, ["-c", `
import io, json, sys, zipfile
from PIL import Image, ImageDraw
image = Image.new("RGBA", (1536, 1872))
draw = ImageDraw.Draw(image)
for row, count in enumerate((6, 8, 8, 4, 5, 8, 6, 6, 6)):
    for column in range(count):
        x, y = column * 192, row * 208
        draw.ellipse((x + 24, y + 32, x + 168, y + 192), fill=(128, 96, 192, 255))
data = io.BytesIO()
image.save(data, format="WEBP", lossless=True)
with zipfile.ZipFile(sys.argv[1], "w") as archive:
    archive.writestr("pet.json", json.dumps({"id": "speech-fixture", "displayName": "Speech fixture", "description": "Generated integration fixture", "spritesheetPath": "spritesheet.webp"}))
    archive.writestr("spritesheet.webp", data.getvalue())
`, pet], { cwd: repository, encoding: "utf8" });
  return { reference, pet };
}

/** Use a loopback-only model registration so real chat dispatch cannot contact a cloud model. */
export function speechConfiguration(url: string) {
  return `[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
base_url = "${url}/v1"
api_key = "fixture"
model = "speech-fixture"
effort = "none"
model_context_window = 128000
[desktop.chat]
streaming_enabled = true
[agent.maintenance]
memory_optimizer_enabled = false
[plugins.desktop_pet]
enabled = true
`;
}

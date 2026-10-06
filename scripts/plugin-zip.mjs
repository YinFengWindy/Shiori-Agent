import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { crc32, deflateRawSync } from "node:zlib";

/** Write a deterministic ZIP within the host admission limits, without environment tooling. */
export async function zipPluginDirectory(directory, destination) {
  const files = [];
  let total = 0;
  async function collect(prefix = "") {
    for (const entry of (await readdir(join(directory, prefix), { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name, "en"))) {
      const path = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) await collect(path);
      else if (entry.isFile()) {
        const bytes = await readFile(join(directory, path));
        total += bytes.length;
        if (files.length >= 4096 || total > 64 * 1024 * 1024) throw new Error("Plugin exceeds 4096 files or 64 MiB");
        files.push({ name: Buffer.from(path, "utf8"), bytes });
      } else throw new Error(`Not a regular package file: ${path}`);
    }
  }
  await collect();
  const local = [], central = [];
  let offset = 0;
  for (const { name, bytes } of files) {
    const compressed = deflateRawSync(bytes);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(0x0800, 6);
    header.writeUInt16LE(8, 8);
    header.writeUInt16LE(33, 12);
    header.writeUInt32LE(crc32(bytes), 14);
    header.writeUInt32LE(compressed.length, 18);
    header.writeUInt32LE(bytes.length, 22);
    header.writeUInt16LE(name.length, 26);
    local.push(header, name, compressed);
    const record = Buffer.alloc(46);
    record.writeUInt32LE(0x02014b50);
    record.writeUInt16LE(20, 4);
    header.copy(record, 6, 4, 28);
    record.writeUInt32LE(offset, 42);
    central.push(record, name);
    offset += header.length + name.length + compressed.length;
  }
  const footer = Buffer.alloc(22);
  footer.writeUInt32LE(0x06054b50);
  footer.writeUInt16LE(files.length, 8);
  footer.writeUInt16LE(files.length, 10);
  footer.writeUInt32LE(central.reduce((size, part) => size + part.length, 0), 12);
  footer.writeUInt32LE(offset, 16);
  await writeFile(destination, Buffer.concat([...local, ...central, footer]));
}

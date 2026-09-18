import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { crc32 } from "node:zlib";

/** Write a deterministic, uncompressed ZIP without host tooling or runtime deps. */
export async function zipDirectory(directory, destination) {
  const entries = [];
  async function collect(relative = "") {
    for (const entry of (await readdir(join(directory, relative), { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name, "en"))) {
      const name = relative ? `${relative}/${entry.name}` : entry.name;
      if (entry.isDirectory()) await collect(name);
      else if (entry.isFile()) entries.push({ name: Buffer.from(name), bytes: await readFile(join(directory, name)) });
      else throw new Error(`Not a regular package file: ${name}`);
    }
  }
  await collect();
  const local = [];
  const central = [];
  let offset = 0;
  for (const { name, bytes } of entries) {
    const checksum = crc32(bytes);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(0x0800, 6);
    header.writeUInt16LE(33, 12); // Stable DOS date: 1980-01-01.
    header.writeUInt32LE(checksum, 14);
    header.writeUInt32LE(bytes.length, 18);
    header.writeUInt32LE(bytes.length, 22);
    header.writeUInt16LE(name.length, 26);
    local.push(header, name, bytes);
    const record = Buffer.alloc(46);
    record.writeUInt32LE(0x02014b50);
    record.writeUInt16LE(20, 4);
    header.copy(record, 6, 4, 28);
    record.writeUInt32LE(offset, 42);
    central.push(record, name);
    offset += header.length + name.length + bytes.length;
  }
  const footer = Buffer.alloc(22);
  footer.writeUInt32LE(0x06054b50);
  footer.writeUInt16LE(entries.length, 8);
  footer.writeUInt16LE(entries.length, 10);
  footer.writeUInt32LE(central.reduce((size, bytes) => size + bytes.length, 0), 12);
  footer.writeUInt32LE(offset, 16);
  await writeFile(destination, Buffer.concat([...local, ...central, footer]));
}

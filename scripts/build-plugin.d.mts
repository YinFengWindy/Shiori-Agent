/** Build an independent external plugin archive and return its distributable identity. */
export function buildPlugin(options: { plugin: string; output: string }): Promise<{
  id: string;
  version: string;
  archive: string;
  sha256: string;
}>;

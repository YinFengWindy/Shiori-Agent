"""Run every manifest through production setup, reload and disposal contracts."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from agent.plugin_host.manifest import load_manifest
from tests.support.plugin_contracts import (
    ROOT,
    manifest_ids,
    profile_for,
    verify_contract,
)


async def run_contracts(
    directories: list[Path],
    *,
    output: Path,
    rpc_root: Path | None = None,
    profile: str | None = None,
) -> list[dict[str, object]]:
    """Write one auditable result per requested plugin; a failure never disappears."""
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="shiori-manifest-contracts-") as temporary:
        for directory in directories:
            plugin_id = directory.name
            try:
                manifest = load_manifest(directory)
                assert manifest is not None
                plugin_id = manifest.id
                contract_path = (
                    (rpc_root / plugin_id) if rpc_root else directory
                ) / "rpc-contract.generated.json"
                assert (
                    contract_path.is_file()
                ), f"Missing generated RPC contract: {contract_path}"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                result = await verify_contract(
                    plugin_id,
                    Path(temporary) / plugin_id,
                    directory=directory,
                    profile=profile or profile_for(directory),
                    rpc_contract=contract,
                )
                results.append({**result, "status": "passed"})
                print(f"passed {plugin_id}")
            except Exception as error:
                results.append(
                    {"plugin_id": plugin_id, "status": "failed", "error": str(error)}
                )
                print(f"FAILED {plugin_id}: {error}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return results


def main() -> int:
    """Default inventory is exhaustive; explicit plugin paths support scaffolds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-dir", type=Path, action="append")
    parser.add_argument("--profile", choices=("rpc",))
    parser.add_argument("--rpc-root", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/plugin-contracts.json"
    )
    args = parser.parse_args()
    directories = args.plugin_dir or [
        ROOT / "plugins" / name for name in manifest_ids()
    ]
    results = asyncio.run(
        run_contracts(
            directories,
            output=args.output,
            rpc_root=args.rpc_root,
            profile=args.profile,
        )
    )
    return int(
        len(results) != len(directories)
        or any(r["status"] != "passed" for r in results)
    )


if __name__ == "__main__":
    raise SystemExit(main())

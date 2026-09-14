# Independent external package fixture

Copy this entire folder outside Shiori before building. It only requires Node
and pnpm 10.33.0; esbuild 0.25.12 is its own build dependency.

```powershell
pnpm install
pnpm build
```

`package/` is the complete distribution root, including all three renderer
contributions, backend, CSS and a static asset. React and React DOM remain external
peers; the build does not resolve or import Shiori source files. Zip the **contents**
of `package/`, without a wrapping directory.

From a Shiori environment containing the contract validator (use its `.venv`
interpreter or `uv run`), pass the outside path to the owning API:

```python
from pathlib import Path
from agent.plugin_host.package_contract import validate_package
from agent.plugin_host.package_archive import validate_package_zip

validated = validate_package(Path("D:/independent-example/package"))
validated_zip = validate_package_zip(Path("D:/independent-example/release.zip"))
assert validated.manifest.id == validated_zip.manifest.id == "external_demo"
```

The validation environment is the host under test, not a build dependency of the
fixture. Validation executes no plugin backend or JS. It establishes the package
contract; installation/trust, external renderer loading and transactional
activation are subsequent #210 tickets.

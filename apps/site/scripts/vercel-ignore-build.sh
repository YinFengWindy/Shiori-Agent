#!/bin/sh
# Vercel "Ignored Build Step" (vercel.json `ignoreCommand`, capped at 256
# characters, hence this script): exit 0 skips the deploy, exit 1 builds.
# Lists every input of `pnpm run build:site`: the site package; the desktop
# files it imports (styles, shared class names, scene assets + timeOfDay,
# title logo, Tailwind theme) and the tsconfigs Vite reads to transpile them;
# the SDK sources and the package.json whose exports resolve them; and the
# dependency graph.
exec git diff HEAD^ HEAD --quiet -- \
  apps/site \
  apps/desktop/renderer/src/styles.css \
  apps/desktop/renderer/src/shared/adv/adv.css \
  apps/desktop/renderer/src/shared/styles.ts \
  apps/desktop/renderer/src/shared/scene \
  apps/desktop/renderer/src/shared/assets/scene \
  apps/desktop/renderer/public/assets/branding \
  apps/desktop/renderer/tailwind.config.ts \
  apps/desktop/renderer/tsconfig.json \
  apps/desktop/tsconfig.base.json \
  packages/sdk/src \
  packages/sdk/package.json \
  package.json \
  pnpm-lock.yaml \
  pnpm-workspace.yaml \
  vercel.json

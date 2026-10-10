#!/bin/sh
# Vercel "Ignored Build Step" (vercel.json `ignoreCommand`, capped at 256
# characters, hence this script): exit 0 skips the deploy, exit 1 builds.
# Lists every input of `pnpm run build:site`: the site package plus the
# desktop styles, scene assets and Tailwind theme it imports directly.
exec git diff HEAD^ HEAD --quiet -- \
  apps/site \
  apps/desktop/renderer/src/styles.css \
  apps/desktop/renderer/src/shared/adv/adv.css \
  apps/desktop/renderer/src/shared/styles.ts \
  apps/desktop/renderer/src/shared/scene \
  apps/desktop/renderer/src/shared/assets/scene \
  apps/desktop/renderer/public/assets/branding \
  apps/desktop/renderer/tailwind.config.ts \
  packages/sdk/src \
  package.json \
  pnpm-lock.yaml \
  pnpm-workspace.yaml \
  vercel.json

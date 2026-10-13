#!/bin/sh
# Vercel "Ignored Build Step" (vercel.json `ignoreCommand`, capped at 256
# characters, hence this script): exit 0 skips the deploy, exit 1 builds.
#
# 1. Build when the last commit changed an input of `pnpm run build:site`:
#    the site package; the desktop files it imports (styles + design tokens,
#    shared class names, scene assets + timeOfDay, mascot expression sprites +
#    expression list + mascot.css, Tailwind theme) and the tsconfigs Vite
#    reads to transpile them; the SDK sources and the package.json whose
#    exports resolve them; and the dependency graph. A failing diff (no
#    parent commit in the clone) exits above 1, which builds too.
git diff HEAD^ HEAD --quiet -- \
  apps/site \
  apps/desktop/renderer/src/styles.css \
  apps/desktop/renderer/src/tokens.css \
  apps/desktop/renderer/src/shared/adv/adv.css \
  apps/desktop/renderer/src/shared/styles.ts \
  apps/desktop/renderer/src/shared/scene \
  apps/desktop/renderer/src/shared/assets/scene \
  apps/desktop/renderer/src/shared/mascot/mascotExpressions.ts \
  apps/desktop/renderer/src/shared/mascot/mascot.css \
  apps/desktop/renderer/src/shared/assets/mascot \
  apps/desktop/renderer/tailwind.config.ts \
  apps/desktop/renderer/tsconfig.json \
  apps/desktop/tsconfig.base.json \
  packages/sdk/src \
  packages/sdk/package.json \
  package.json \
  pnpm-lock.yaml \
  pnpm-workspace.yaml \
  vercel.json
status=$?
[ "$status" -eq 0 ] || exit 1

# 2. The GitHub releases are an input too (the changelog, #792), outside
#    git: a release published after the last commit makes the site stale.
#    This is what lets the Deploy Hook's build through
#    (.github/workflows/site-redeploy-on-release.yml): Vercel marks no
#    deployment as hook-made, and the hook builds the branch's last commit,
#    which often touched nothing of the site.
exec node apps/site/scripts/vercel-release-since-head.mjs

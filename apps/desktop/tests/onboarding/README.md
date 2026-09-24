# Onboarding QA

Run from the repository root after `pnpm build`. Start the renderer separately:

```powershell
pnpm --filter shiori-desktop exec vite --config renderer/vite.config.ts --host 127.0.0.1 --port 5187 --strictPort
```

Then run the relevant checks:

```powershell
pnpm desktop:test:onboarding
pnpm desktop:test:onboarding:electron
```

The browser test uses a persistent fake bridge and Edge on Windows. Set
`SHIORI_QA_BROWSER` to another Chromium executable or `SHIORI_QA_URL` to another
renderer URL when needed. The guide is 吟风's ADV: the tests click through her
lines (the transparent 「继续对话」 surface) until each step's card appears. It
checks the greeting, the step indicator, 「跳过」 and her answer, failed
reads/writes, connection test results and her reactions, retry behavior,
temporary dismissal, restart recovery, avatar selection/removal, completion,
existing-user exemption, and that every step's primary action and the dialogue
box fit at 1280x800, 960x640, 1920x1080 and the 520x680 minimum window. The fake
bridge answers only the methods it implements with real payload shapes; any
other method is recorded and fails the run.

The Electron test uses the real preload, IPC, project `.venv` Python bridge,
settings transactions, role storage, and local asset transport. Only the native
file dialog result is substituted. It uses an isolated home and user-data directory
under `.test-tmp-root/onboarding-qa`; existing user configuration is untouched.
The test model points to a closed loopback port and never sends a chat request.

Screenshots and isolated runtime data remain under `.test-tmp-root/onboarding-qa`
for inspection. Both tests close the browser/application processes they launch.

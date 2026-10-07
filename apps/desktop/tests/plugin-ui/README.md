# Production plugin integration checks

Run from the repository root with its `.venv` and frozen pnpm dependencies installed:

```powershell
pnpm build:desktop
pnpm desktop:test:speech-integration
```

The speech check verifies that the built-in SenseVoiceSmall and GPT-SoVITS plugins start disabled in a fresh temporary workspace, enables them through the plugins page, selects their services in the actual desktop-pet settings, and drives the pet surface's public press/release and stop messages. The production native recorder, provider implementations, chat dispatcher, SSE events, session persistence, and native audio player execute.

Physical microphone input is replaced with a generated WebAudio `MediaStream`. The ASR, TTS and LLM servers are loopback HTTP protocol doubles. No models are downloaded, no physical microphone is opened, and no cloud model is contacted. This proves application integration and cancellation, not real-model recognition, voice quality, latency or frozen-installer behavior. OS global-key delivery is covered separately; this test uses the pet surface's public gesture channel.

`SHIORI_E2E_ELECTRON_PATH` optionally identifies an already installed Electron executable. The application entry always comes from the current checkout. All configuration, generated pet/reference assets, profile and evidence live under a fresh `.test-tmp-root/distribution-speech-*` directory. `results.json`, HTTP request logs, process errors and a screenshot remain available after the run.

Checks cover normal ASR → chat → TTS playback, manual stop clearing the remaining sentence queue, stopping while synthesis is pending, and a new turn waiting for the actual prior HTTP response before starting synthesis. The stopped turn's late audio must never play.

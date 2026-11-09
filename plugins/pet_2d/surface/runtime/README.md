# Prelulu package renderer

This is a local implementation of the prepared data in `prelulu-avatar-package/v1`.
It loads image data only; it does not execute package code or load a remote player.

The supported bake fingerprints are checked in `model.ts`. The renderer consumes
prepared layer order and coordinates, corrected eye axes, the parameterized mouth
fit and articulation bound, `hair-pins/v3` buffers, and baked eyelid skin/rest/ink
components. It never substitutes the uncorrected rig layers for a missing bake.

The data semantics were checked against the player supplied through
[the author's preview](https://paper-avatar-preview.zjudn2013.workers.dev/c/job_188e29e4691e94dcf75a7937).
Its four bake fingerprints match the supplied ZIP. The preview character and the
ZIP character are different; visual acceptance uses the ZIP itself. No website
bundle or user character assets are distributed here.

During implementation, an external local reference oracle compared 1,630 scalar
results for amplitude-only mouth contours, constrained hair displacement, eye
deformation, lash ink and lid lines. Maximum difference was below `3e-10`.
That oracle is an investigation artifact, not a production dependency or a test
fixture. Repository tests use synthetic data.

`renderer.ts` owns asynchronous image loading and the frame loop. `webgl.ts` owns
the program, buffers, textures and iris stencil masks. `scene.ts` assembles the
prepared layers and applies idle motion. `mouth.ts`, `lids.ts` and `hair.ts` operate
in the stored canvas coordinates before the common head/body transform.

Speech input is the desktop's currently playing RMS stream. The renderer applies
gain and attack/release smoothing, then the baked mouth-opening limit. No audio
is played here. A terminal sample closes the mouth; a changed playback identity
starts a fresh envelope. Reduced-motion mode suppresses idle motion and blinking
while retaining speech articulation. Website drama, expression-generation and
viseme features are outside this provider's scope.

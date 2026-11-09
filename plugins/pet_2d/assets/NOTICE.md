# MediaPipe runtime and model

The local face tracker uses `@mediapipe/tasks-vision` **1.2.2**, published by the
MediaPipe authors under Apache-2.0. Its JavaScript and WebAssembly assets are
bundled from the pinned npm dependency; the license is retained alongside this
notice. No runtime CDN request is required.

The unchanged Face Landmarker model bundle is obtained from Google's official
versioned model endpoint:

- Source: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
- Size: 3,758,596 bytes
- SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`
- Model documentation and model cards: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker#models

The model estimates face motion and expressions locally. Camera frames are not
stored, uploaded, or used to identify people.

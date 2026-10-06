import { VoiceCaptureRenderer } from "./captureController";
import { VoicePlaybackRenderer } from "./playbackController";

const capture = new VoiceCaptureRenderer();
const playback = new VoicePlaybackRenderer();

window.miraDesktop.onVoiceCaptureCommand((command) => capture.handleCommand(command));
window.miraDesktop.onVoicePlaybackCommand((command) => playback.handleCommand(command));

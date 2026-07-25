import { VoiceCaptureRenderer } from "./captureController";
import { VoicePlaybackRenderer } from "./playbackController";

const capture = new VoiceCaptureRenderer();
const playback = new VoicePlaybackRenderer();

window.miraDesktop.onVoiceCaptureCommand((command) => {
  if (!capture.handleCommand(command) && typeof command === "object" && command.command === "play-test") {
    playback.playTestAudio(command.audioBase64);
  }
});
window.miraDesktop.onVoicePlaybackCommand((command) => playback.handleCommand(command));

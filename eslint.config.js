// Repository-root ESLint configuration.
//
// It exists because ESLint resolves what is lintable from the working
// directory: an ESLint run rooted at `apps/desktop/` refuses to lint anything
// above it, including the colocated plugin UI under the top-level `plugins/`
// tree that is compiled straight into the renderer bundle (#174, #181). Moving
// plugin-owned renderer code out of `apps/desktop/renderer/src/` without this
// would silently drop it from lint.
//
// The rules themselves stay next to the toolchain that provides them —
// `typescript-eslint` and the React plugins live in `apps/desktop/node_modules`,
// and are resolved from that file rather than from here.
import { desktopEslintConfig } from "./apps/desktop/eslint.config.js";

/**
 * Plugin renderer code and the plugin SDK. Plugins reach the host only
 * through `@shiori/plugin-sdk` and their injected `client`/`host` (#440), and
 * the SDK itself must never depend on host source.
 */
const pluginRendererFiles = [
  "plugins/*/ui/**/*.ts",
  "plugins/*/ui/**/*.tsx",
  "plugins/*/surface/**/*.ts",
  "plugins/*/surface/**/*.tsx",
  "plugins/*/background/**/*.ts",
  "plugins/*/background/**/*.tsx",
  "packages/plugin-sdk/src/**/*.ts",
  "packages/plugin-sdk/src/**/*.tsx",
];

/**
 * Plugin renderer files that still import host source while their plugin
 * awaits migration to the SDK (#440). One entry per file that really has such
 * an import — never a directory — so a new file is always checked. Delete an
 * entry as soon as its file is migrated; the last migration ticket removes
 * this list and the `ignores` below. `pluginHostImportBoundary.test.ts`
 * fails on an entry whose file no longer imports host source.
 */
export const pluginHostImportExemptions = [
  "plugins/desktop_pet/background/controller.test.ts",
  "plugins/desktop_pet/background/controller.ts",
  "plugins/desktop_pet/background/hostContract.test.ts",
  "plugins/desktop_pet/background/index.test.ts",
  "plugins/desktop_pet/background/index.ts",
  "plugins/desktop_pet/background/replyBubble.test.ts",
  "plugins/desktop_pet/background/replyBubble.ts",
  "plugins/desktop_pet/background/roleReply.test.ts",
  "plugins/desktop_pet/background/roleReply.ts",
  "plugins/desktop_pet/surface/CodexSpritePetRenderer.tsx",
  "plugins/desktop_pet/surface/DesktopPetSurface.test.tsx",
  "plugins/desktop_pet/surface/DesktopPetSurface.tsx",
  "plugins/desktop_pet/surface/activity.ts",
  "plugins/desktop_pet/surface/petMenu.test.ts",
  "plugins/desktop_pet/surface/petMenu.ts",
  "plugins/desktop_pet/surface/useCodexPetInteraction.test.tsx",
  "plugins/desktop_pet/surface/useCodexPetInteraction.ts",
  "plugins/desktop_pet/ui/RolePetPackagesPanel.test.tsx",
  "plugins/desktop_pet/ui/RolePetPackagesPanel.tsx",
  "plugins/desktop_pet/ui/index.tsx",
  "plugins/desktop_pet/ui/petPackagePicker.ts",
  "plugins/desktop_pet/ui/roleSettings.test.tsx",
  "plugins/desktop_pet/ui/roleSettings.tsx",
  "plugins/desktop_pet/ui/usePetPackages.ts",
  "plugins/feishu/ui/FeishuAccountDetail.test.tsx",
  "plugins/feishu/ui/FeishuAccountDetail.tsx",
  "plugins/feishu/ui/index.tsx",
  "plugins/novelai/ui/BaseImageField.tsx",
  "plugins/novelai/ui/ChatImageActions.test.tsx",
  "plugins/novelai/ui/ChatImageActions.tsx",
  "plugins/novelai/ui/ImageFilmstrip.tsx",
  "plugins/novelai/ui/ImageStage.test.tsx",
  "plugins/novelai/ui/ImageStage.tsx",
  "plugins/novelai/ui/ImageStudioPage.tsx",
  "plugins/novelai/ui/NovelAIPage.tsx",
  "plugins/novelai/ui/NovelAIPageSidebar.tsx",
  "plugins/novelai/ui/PromptPanel.test.tsx",
  "plugins/novelai/ui/PromptPanel.tsx",
  "plugins/novelai/ui/PromptSettingsPopover.tsx",
  "plugins/novelai/ui/PromptTagEntryEditor.tsx",
  "plugins/novelai/ui/PromptTagGrid.test.tsx",
  "plugins/novelai/ui/PromptTagGrid.tsx",
  "plugins/novelai/ui/PromptTagLibraryPage.test.tsx",
  "plugins/novelai/ui/PromptTagLibraryPage.tsx",
  "plugins/novelai/ui/PromptTagLibraryPanel.tsx",
  "plugins/novelai/ui/SegmentedControl.tsx",
  "plugins/novelai/ui/SizeField.tsx",
  "plugins/novelai/ui/StageStates.tsx",
  "plugins/novelai/ui/generationFailure.test.ts",
  "plugins/novelai/ui/generationFailure.ts",
  "plugins/novelai/ui/index.tsx",
  "plugins/novelai/ui/novelAiGeneration.test.ts",
  "plugins/novelai/ui/novelAiGeneration.ts",
  "plugins/novelai/ui/novelAiPageStore.test.tsx",
  "plugins/novelai/ui/novelAiPageStore.ts",
  "plugins/novelai/ui/roleSettings.test.tsx",
  "plugins/novelai/ui/roleSettings.tsx",
  "plugins/novelai/ui/studioForm.ts",
  "plugins/novelai/ui/useImageStudio.test.tsx",
  "plugins/novelai/ui/useImageStudio.ts",
  "plugins/novelai/ui/useNovelAiPromptSettings.ts",
  "plugins/novelai/ui/usePromptTagLibrary.ts",
  "plugins/qq/ui/QQAccountForm.tsx",
  "plugins/qq/ui/index.test.tsx",
  "plugins/qq/ui/index.tsx",
  "plugins/qq/ui/qqStatusPresentation.ts",
  "plugins/qq/ui/useManagedNapCat.ts",
  "plugins/qq/ui/useQQAccountForm.test.tsx",
  "plugins/qq/ui/useQQAccountForm.ts",
  "plugins/qqbot/ui/QQBotAccountDetail.test.tsx",
  "plugins/qqbot/ui/QQBotAccountDetail.tsx",
  "plugins/qqbot/ui/index.tsx",
  "plugins/story/ui/StoryCgGallerySurface.tsx",
  "plugins/story/ui/StoryCreateFlow.tsx",
  "plugins/story/ui/StoryCreateStep.tsx",
  "plugins/story/ui/StoryGameSurface.tsx",
  "plugins/story/ui/StoryPage.tsx",
  "plugins/story/ui/StorySurface.tsx",
  "plugins/story/ui/StoryWorkspacePresentationView.tsx",
  "plugins/story/ui/index.tsx",
  "plugins/story/ui/storyBridgeClient.test.ts",
  "plugins/story/ui/storyCharacterPresentation.test.ts",
  "plugins/story/ui/storyCharacterPresentation.ts",
  "plugins/story/ui/storyMenuBackground.ts",
  "plugins/story/ui/types.ts",
  "plugins/story/ui/useStoryController.ts",
  "plugins/story/ui/useStoryGalleryRefresh.test.tsx",
  "plugins/story/ui/useStoryGalleryRefresh.ts",
  "plugins/story/ui/useStoryMenuBackground.ts",
  "plugins/story/ui/useStoryWorkspacePresentation.tsx",
  "plugins/telegram/ui/TelegramAccountDetail.test.tsx",
  "plugins/telegram/ui/TelegramAccountDetail.tsx",
  "plugins/telegram/ui/index.tsx",
];

const hostImportMessage = "Plugins must not import host source (apps/desktop); use @shiori/plugin-sdk or the injected client/host.";

export default [
  ...desktopEslintConfig([
    "apps/desktop/tests/plugin-ui/packaged*.ts",
    "tests/fixtures/external-plugin/src/**/*.ts",
    "tests/fixtures/external-plugin/src/**/*.tsx",
    "apps/desktop/src/**/*.ts",
    "apps/desktop/src/**/*.tsx",
    "apps/desktop/renderer/src/**/*.ts",
    "apps/desktop/renderer/src/**/*.tsx",
    "apps/desktop/site/**/*.ts",
    ...pluginRendererFiles,
  ]),
  {
    files: pluginRendererFiles,
    ignores: pluginHostImportExemptions,
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [
          // Any relative (`../../../apps/desktop/...`) or aliased spelling that names the host tree.
          { regex: "(^|/)apps/desktop(/|$)", message: hostImportMessage },
          // The host's workspace package name, should it ever become resolvable.
          { group: ["shiori-desktop", "shiori-desktop/**"], message: hostImportMessage },
        ],
      }],
    },
  },
];

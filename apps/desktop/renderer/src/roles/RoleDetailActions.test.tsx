import assert from "node:assert/strict";
import { it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { RoleDetailActions } from "./RoleDetailActions";

it("keeps chat available but hides editor actions on the memory tab", () => {
  const props = {
    canGoToChat: true,
    saveState: { canSave: true, canReset: true, saveLabel: "保存", saving: false },
    onGoToChat: () => undefined,
    onReset: () => undefined,
    onSave: () => undefined,
  };
  const readOnly = renderToStaticMarkup(<RoleDetailActions {...props} showEditorActions={false} />);
  const editable = renderToStaticMarkup(<RoleDetailActions {...props} showEditorActions />);

  assert.match(readOnly, /去聊天/);
  assert.doesNotMatch(readOnly, /reset-role-button|save-role-button/);
  assert.match(editable, /reset-role-button/);
  assert.match(editable, /save-role-button/);
});

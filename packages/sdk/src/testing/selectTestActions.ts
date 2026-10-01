import assert from "node:assert/strict";
import { act } from "react";

/**
 * Chooses an option through the visible picker, including a real bubbling
 * pointer event. `index` picks among several pickers sharing one label.
 */
export async function chooseSelectOption(label: string, optionLabel: string, index = 0) {
  const trigger = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="combobox"]'))
    .filter((element) => element.getAttribute("aria-label") === label)[index];
  assert.ok(trigger, `Missing select: ${label}`);
  await act(async () => trigger.click());
  const option = Array.from(document.querySelectorAll<HTMLElement>('[role="option"]'))
    .find((element) => element.textContent === optionLabel);
  assert.ok(option, `Missing option: ${optionLabel}`);
  await act(async () => {
    option.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, pointerType: "mouse" }));
    option.click();
  });
}

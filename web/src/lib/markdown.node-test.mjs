import assert from "node:assert/strict";
import test from "node:test";

function splitOpenFence(text) {
  const ticks = text.split("```").length - 1;
  if (ticks % 2 === 0) return { complete: text, openFence: "" };
  const idx = text.lastIndexOf("```");
  return { complete: text.slice(0, idx), openFence: text.slice(idx) };
}

test("closed fence stays complete", () => {
  const src = "hi\n```js\nconst x = 1\n```\n";
  const out = splitOpenFence(src);
  assert.equal(out.openFence, "");
  assert.equal(out.complete, src);
});

test("open fence is split off", () => {
  const src = "hi\n```js\nconst x = 1\n";
  const out = splitOpenFence(src);
  assert.equal(out.openFence.startsWith("```"), true);
  assert.equal(out.complete.includes("```"), false);
});

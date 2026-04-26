import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

test("index page includes local console workflow copy", () => {
  const page = readFileSync(new URL("./index.tsx", import.meta.url), "utf8");

  assert.match(page, /Syncore Local Prototype Console/);
  assert.match(page, /Task Explorer/);
  assert.match(page, /Analyst Digest/);
  assert.match(page, /make demo-local/);
});

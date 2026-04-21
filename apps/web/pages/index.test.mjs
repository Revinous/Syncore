import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

test("index page includes expected shell copy", () => {
  const page = readFileSync(new URL("./index.tsx", import.meta.url), "utf8");

  assert.match(page, /Agent Workforce OS/);
  assert.match(page, /Local shell is running\./);
  assert.match(page, /apiBaseUrl/);
});

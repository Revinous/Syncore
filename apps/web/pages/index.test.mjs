import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

test("index page includes dashboard control panel copy", () => {
  const page = readFileSync(new URL("./index.tsx", import.meta.url), "utf8");

  assert.match(page, /Dashboard/);
  assert.match(page, /Loading dashboard summary/);
  assert.match(page, /Recent Events/);
  assert.match(page, /Recent Batons/);
});

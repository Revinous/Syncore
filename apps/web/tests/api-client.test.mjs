import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

test("api client uses NEXT_PUBLIC_API_BASE_URL and handles non-200", () => {
  const apiFile = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");

  assert.match(apiFile, /NEXT_PUBLIC_API_BASE_URL/);
  assert.match(apiFile, /if \(!response\.ok\)/);
  assert.match(apiFile, /API request failed/);
});

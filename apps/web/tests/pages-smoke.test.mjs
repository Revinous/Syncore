import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

function read(rel) {
  return readFileSync(new URL(rel, import.meta.url), "utf8");
}

test("dashboard page has loading/empty/error states", () => {
  const page = read("../pages/index.tsx");
  assert.match(page, /Loading dashboard summary/);
  assert.match(page, /No recent events/);
  assert.match(page, /ErrorState/);
});

test("workspaces page has empty state", () => {
  const page = read("../pages/workspaces.tsx");
  assert.match(page, /No workspaces registered yet/);
});

test("tasks page has empty state", () => {
  const page = read("../pages/tasks\/index.tsx");
  assert.match(page, /No tasks found/);
});

test("diagnostics page renders service health", () => {
  const page = read("../pages/diagnostics.tsx");
  assert.match(page, /Service Health/);
  assert.match(page, /getServicesHealth/);
});

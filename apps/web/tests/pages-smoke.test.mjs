import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

function read(rel) {
  return readFileSync(new URL(rel, import.meta.url), "utf8");
}

test("dashboard page has loading/empty/error states", () => {
  const page = read("../pages/index.tsx");
  const panels = read("../src/components/DashboardPanels.tsx");
  assert.match(page, /Loading dashboard summary/);
  assert.match(panels, /No recent events/);
  assert.match(page, /ErrorState/);
});

test("workspaces page has empty state", () => {
  const page = read("../pages/workspaces.tsx");
  const body = read("../src/components/WorkspaceRegistryBody.tsx");
  assert.match(page, /WorkspaceRegistryBody/);
  assert.match(body, /No workspaces registered yet/);
});

test("tasks page has empty state", () => {
  const page = read("../pages/tasks\/index.tsx");
  assert.match(page, /No tasks found/);
});

test("diagnostics page renders service health", () => {
  const page = read("../pages/diagnostics.tsx");
  const providerPanel = read("../src/components/ExperimentalProviderPanel.tsx");
  assert.match(page, /Service Health/);
  assert.match(page, /getServicesHealth/);
  assert.match(providerPanel, /Recommended Action/);
  assert.match(page, /Native Experimental Codex OAuth/);
});

test("auth page renders provider setup controls", () => {
  const page = read("../pages/auth.tsx");
  const panels = read("../src/components/AuthPanels.tsx");
  assert.match(page, /OpenAIAuthPanel/);
  assert.match(page, /CodexAuthPanel/);
  assert.match(panels, /Official OpenAI API Key/);
  assert.match(panels, /Native Experimental Codex OAuth/);
  assert.match(panels, /Start Browser OAuth/);
});

test("settings page renders runtime default controls", () => {
  const page = read("../pages/settings.tsx");
  assert.match(page, /Runtime Settings/);
  assert.match(page, /Default provider path/);
  assert.match(page, /Resolved Provider/);
});

test("notifications page has empty state", () => {
  const page = read("../pages/notifications.tsx");
  assert.match(page, /No unread notifications/);
});

test("analyst page renders digest controls", () => {
  const page = read("../pages/analyst.tsx");
  assert.match(page, /Analyst Digest/);
  assert.match(page, /Generate Digest/);
});

test("task detail page renders model strategy controls", () => {
  const page = read("../pages/tasks/[taskId].tsx");
  const detailBody = read("../src/components/TaskDetailBody.tsx");
  const executionPanel = read("../src/components/ExecutionOutcomePanel.tsx");
  const modelStrategyPanel = read("../src/components/ModelStrategyPanel.tsx");
  assert.match(page, /TaskDetailBody/);
  assert.match(detailBody, /Model Strategy/);
  assert.match(detailBody, /Execution Outcome/);
  assert.match(executionPanel, /Verification Commands/);
  assert.match(modelStrategyPanel, /optimization_goal/);
  assert.match(modelStrategyPanel, /Save strategy/);
});

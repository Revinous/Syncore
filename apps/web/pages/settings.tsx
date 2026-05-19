import { FormEvent, useEffect, useState } from "react";

import { getRuntimeSettings, updateRuntimeSettings } from "../src/lib/api";
import { readApiError } from "../src/lib/api_error";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { PageHeader } from "../src/components/PageHeader";
import { StatusBadge } from "../src/components/StatusBadge";
import { Surface } from "../src/components/Surface";
import { RuntimeSettings } from "../src/lib/types";

const OPTION_LABELS: Record<string, string> = {
  openai: "Official OpenAI API",
  codex_oauth_experimental: "Native Codex OAuth",
  codex_sidecar: "Codex Sidecar Bridge",
  anthropic: "Anthropic API",
  gemini: "Gemini API",
  local_echo: "Local Echo",
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [selection, setSelection] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const next = await getRuntimeSettings();
      setSettings(next);
      setSelection(next.default_provider_preference ?? next.resolved_default_provider);
    } catch (err) {
      setError(readApiError(err, "Failed to load runtime settings"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const next = await updateRuntimeSettings({
        default_provider_preference: selection || null,
      });
      setSettings(next);
      setSelection(next.default_provider_preference ?? next.resolved_default_provider);
    } catch (err) {
      setError(readApiError(err, "Failed to save runtime settings"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Layout title="Settings">
      <div className="page-shell">
        <PageHeader
          title="Runtime Settings"
          subtitle="Choose the overall default provider path Syncore should use when a task does not explicitly override its model strategy."
          kicker="Global Defaults"
          actions={
            <button className="button" onClick={() => void load()}>
              Refresh Settings
            </button>
          }
          metrics={[
            {
              label: "Resolved Provider",
              value: settings?.resolved_default_provider ?? "loading",
            },
            {
              label: "Resolved Model",
              value: settings?.resolved_default_model ?? "loading",
            },
          ]}
        />

        {loading ? <LoadingState message="Loading runtime settings..." /> : null}
        {error ? (
          <ErrorState
            title="Settings unavailable"
            message={error}
            hint="Refresh after confirming the local orchestrator is running."
          />
        ) : null}

        {!loading && settings ? (
          <div className="content-grid two-column">
            <Surface
              title="Execution Default"
              description="This choice becomes the baseline for new runs and tasks unless a task-level Model Strategy overrides it."
            >
              <form onSubmit={handleSave} className="stack">
                <div className="helper-text">
                  This is the overall API vs OAuth choice you asked for. Select the provider path Syncore should treat as the default operating mode.
                </div>
                <label className="field-label">
                  Default provider path
                  <select
                    className="field"
                    value={selection}
                    onChange={(event) => setSelection(event.target.value)}
                  >
                    {settings.available_provider_preferences.map((provider) => (
                      <option key={provider} value={provider}>
                        {OPTION_LABELS[provider] ?? provider}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="control-row">
                  <button className="button" type="submit" disabled={saving || !selection}>
                    {saving ? "Saving..." : "Save Default"}
                  </button>
                </div>
                <div className="helper-text">{settings.detail}</div>
              </form>
            </Surface>

            <Surface
              title="Resolution"
              description="How Syncore is currently interpreting the global default provider setting."
              tone="inset"
            >
              <div className="meta-grid">
                <div className="meta-card">
                  <span className="meta-label">Configured</span>
                  <div className="meta-value">
                    <StatusBadge status={settings.configured ? "completed" : "pending"} />
                  </div>
                </div>
                <div className="meta-card">
                  <span className="meta-label">Storage</span>
                  <div className="meta-value">
                    <StatusBadge status={settings.storage_secure ? "healthy" : "warning"} />
                  </div>
                </div>
                <div className="meta-card">
                  <span className="meta-label">Resolved Provider</span>
                  <div className="meta-value">{settings.resolved_default_provider}</div>
                </div>
                <div className="meta-card">
                  <span className="meta-label">Resolved Model</span>
                  <div className="meta-value">{settings.resolved_default_model}</div>
                </div>
              </div>
              <div className="helper-text" style={{ marginTop: 12 }}>
                Stored at: <code>{settings.settings_path}</code>
              </div>
              <div className="helper-text">
                Updated: {settings.updated_at ?? "never"}
              </div>
            </Surface>
          </div>
        ) : null}

        {!loading && settings && settings.available_provider_preferences.length === 0 ? (
          <EmptyState
            message="No configurable providers are currently available."
            hint="Configure API keys or OAuth on the Auth page first."
          />
        ) : null}
      </div>
    </Layout>
  );
}

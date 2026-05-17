import { FormEvent, useEffect, useState } from "react";

import {
  clearCodexAuth,
  clearOpenAIAuth,
  getCodexAuthStatus,
  getOpenAIAuthStatus,
  refreshCodexAuth,
  saveOpenAIAuth,
  startCodexBrowserLogin,
} from "../src/lib/api";
import { readApiError } from "../src/lib/api_error";
import { CodexAuthStatus, OpenAIAuthStatus } from "../src/lib/types";
import { CodexAuthPanel, OpenAIAuthPanel } from "../src/components/AuthPanels";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { PageHeader } from "../src/components/PageHeader";

export default function AuthPage() {
  const [openaiStatus, setOpenaiStatus] = useState<OpenAIAuthStatus | null>(null);
  const [codexStatus, setCodexStatus] = useState<CodexAuthStatus | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [openaiBusy, setOpenaiBusy] = useState(false);
  const [codexBusy, setCodexBusy] = useState<"login" | "refresh" | "logout" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [openai, codex] = await Promise.all([getOpenAIAuthStatus(), getCodexAuthStatus()]);
      setOpenaiStatus(openai);
      setCodexStatus(codex);
    } catch (err) {
      setError(readApiError(err, "Failed to load auth status"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleOpenAISave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOpenaiBusy(true);
    setError(null);
    try {
      setOpenaiStatus(await saveOpenAIAuth(apiKeyInput));
      setApiKeyInput("");
    } catch (err) {
      setError(readApiError(err, "Failed to save OpenAI API key"));
    } finally {
      setOpenaiBusy(false);
    }
  }

  async function handleOpenAIClear() {
    setOpenaiBusy(true);
    setError(null);
    try {
      setOpenaiStatus(await clearOpenAIAuth());
    } catch (err) {
      setError(readApiError(err, "Failed to clear OpenAI API key"));
    } finally {
      setOpenaiBusy(false);
    }
  }

  async function handleCodexAction(action: "login" | "refresh" | "logout") {
    setCodexBusy(action);
    setError(null);
    try {
      if (action === "login") {
        const popup = typeof window !== "undefined" ? window.open("about:blank", "_blank") : null;
        const login = await startCodexBrowserLogin();
        if (popup) {
          popup.location.href = login.auth_url;
        } else if (typeof window !== "undefined") {
          window.open(login.auth_url, "_blank");
        }
        setTimeout(() => {
          void pollCodexStatus();
        }, 1000);
      } else if (action === "refresh") {
        setCodexStatus(await refreshCodexAuth());
      } else {
        setCodexStatus(await clearCodexAuth());
      }
    } catch (err) {
      setError(readApiError(err, `Failed to ${action} native Codex OAuth`));
    } finally {
      setCodexBusy(null);
    }
  }

  async function pollCodexStatus(attempt = 0) {
    try {
      const next = await getCodexAuthStatus();
      setCodexStatus(next);
      const pending = next.metadata["browser_login_pending"] === true;
      if (pending && attempt < 150) {
        window.setTimeout(() => {
          void pollCodexStatus(attempt + 1);
        }, 2000);
        return;
      }
    } catch {
      // Keep the last visible state; the operator can refresh manually if needed.
    } finally {
      setCodexBusy(null);
    }
  }

  return (
    <Layout title="Auth">
      <div className="page-shell">
        <PageHeader
          title="Provider Access"
          subtitle="Manage the local credentials Syncore uses from this machine. Official OpenAI API keys and experimental native Codex OAuth stay separate on purpose."
          kicker="Local Auth"
          actions={
            <button className="button" onClick={() => void load()}>
              Refresh Auth
            </button>
          }
          metrics={[
            { label: "OpenAI API", value: openaiStatus?.configured ? "configured" : "not configured" },
            {
              label: "Codex OAuth",
              value: codexStatus?.authenticated ? "authenticated" : "not authenticated",
            },
          ]}
        />
        {loading ? <LoadingState message="Loading provider auth status..." /> : null}
        {error ? (
          <ErrorState
            title="Auth action failed"
            message={error}
            hint="Retry the exact provider action after checking whether the local credential store or browser flow is available."
          />
        ) : null}
        {!loading && openaiStatus && codexStatus ? (
          <div className="content-grid two-column">
            <OpenAIAuthPanel
              openaiStatus={openaiStatus}
              apiKeyInput={apiKeyInput}
              openaiBusy={openaiBusy}
              onApiKeyInputChange={setApiKeyInput}
              onSave={handleOpenAISave}
              onClear={() => void handleOpenAIClear()}
            />
            <CodexAuthPanel
              codexStatus={codexStatus}
              codexBusy={codexBusy}
              onAction={(action) => void handleCodexAction(action)}
            />
          </div>
        ) : null}
      </div>
    </Layout>
  );
}

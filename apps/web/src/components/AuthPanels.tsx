import { FormEvent } from "react";

import { CodexAuthStatus, OpenAIAuthStatus } from "../lib/types";
import { StatusBadge } from "./StatusBadge";
import { Surface } from "./Surface";

type CodexBusyState = "login" | "refresh" | "logout" | null;

export function OpenAIAuthPanel(props: {
  openaiStatus: OpenAIAuthStatus;
  apiKeyInput: string;
  openaiBusy: boolean;
  onApiKeyInputChange: (value: string) => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onClear: () => void;
}) {
  const { openaiStatus, apiKeyInput, openaiBusy, onApiKeyInputChange, onSave, onClear } = props;
  return (
    <Surface
      title="Official OpenAI API Key"
      description="Supported OpenAI Platform path. Syncore validates the key before storing it locally."
    >
      <div className="stack">
        <div className="operator-strip compact">
          <div className="operator-strip-block">
            <span className="operator-strip-label">Configured</span>
            <div className="operator-strip-value">
              <StatusBadge status={openaiStatus.configured ? "ready" : "pending"} />
            </div>
          </div>
          <div className="operator-strip-block">
            <span className="operator-strip-label">Storage</span>
            <div className="operator-strip-value">
              <StatusBadge status={openaiStatus.storage_secure ? "healthy" : "warning"} />
            </div>
          </div>
        </div>
        <div className="helper-text">{openaiStatus.detail}</div>
        <div className="helper-text">
          Stored at: <code>{openaiStatus.token_path}</code>
        </div>
        <form className="stack" onSubmit={onSave}>
          <label className="field-label" htmlFor="openai-api-key">
            API key
          </label>
          <input
            id="openai-api-key"
            className="field"
            type="password"
            autoComplete="off"
            placeholder="sk-..."
            value={apiKeyInput}
            onChange={(event) => onApiKeyInputChange(event.target.value)}
          />
          <div className="control-row">
            <button className="button" type="submit" disabled={openaiBusy || !apiKeyInput.trim()}>
              {openaiBusy ? "Saving..." : "Save API Key"}
            </button>
            <button
              className="ghost-button"
              type="button"
              disabled={openaiBusy || !openaiStatus.configured}
              onClick={onClear}
            >
              Remove API Key
            </button>
          </div>
        </form>
        <div className="helper-text">
          Visible text models:{" "}
          {openaiStatus.models.length ? openaiStatus.models.slice(0, 8).join(", ") : "none loaded"}
        </div>
      </div>
    </Surface>
  );
}

export function CodexAuthPanel(props: {
  codexStatus: CodexAuthStatus;
  codexBusy: CodexBusyState;
  onAction: (action: Exclude<CodexBusyState, null>) => void;
}) {
  const { codexStatus, codexBusy, onAction } = props;
  return (
    <Surface
      title="Native Experimental Codex OAuth"
      description="Local browser OAuth for the experimental Codex auth prototype. These credentials can now power direct `codex_oauth_experimental` execution."
    >
      <div className="stack">
        <div className="operator-strip compact">
          <div className="operator-strip-block">
            <span className="operator-strip-label">Authenticated</span>
            <div className="operator-strip-value">
              <StatusBadge status={codexStatus.authenticated ? "ready" : "pending"} />
            </div>
          </div>
          <div className="operator-strip-block">
            <span className="operator-strip-label">Refreshable</span>
            <div className="operator-strip-value">
              <StatusBadge status={codexStatus.can_refresh ? "ready" : "blocked"} />
            </div>
          </div>
          <div className="operator-strip-block">
            <span className="operator-strip-label">Storage</span>
            <div className="operator-strip-value">
              <StatusBadge status={codexStatus.storage_secure ? "healthy" : "warning"} />
            </div>
          </div>
        </div>
        <div className="helper-text">{codexStatus.detail}</div>
        <div className="helper-text">
          Stored at: <code>{codexStatus.token_path}</code>
        </div>
        <div className="helper-text">
          Expires: {codexStatus.expires_at ?? "unknown"} · state {codexStatus.implementation_state}
        </div>
        <div className="control-row">
          <button
            className="button"
            type="button"
            disabled={codexBusy !== null}
            onClick={() => onAction("login")}
          >
            {codexBusy === "login" ? "Waiting for OAuth..." : "Start Browser OAuth"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={codexBusy !== null || !codexStatus.authenticated || !codexStatus.can_refresh}
            onClick={() => onAction("refresh")}
          >
            {codexBusy === "refresh" ? "Refreshing..." : "Refresh Token"}
          </button>
          <button
            className="ghost-button"
            type="button"
            disabled={codexBusy !== null || !codexStatus.authenticated}
            onClick={() => onAction("logout")}
          >
            {codexBusy === "logout" ? "Clearing..." : "Clear OAuth"}
          </button>
        </div>
        <div className="helper-text">
          If you want the local bridge path instead, configure <code>codex_sidecar</code> on the
          Diagnostics page.
        </div>
      </div>
    </Surface>
  );
}

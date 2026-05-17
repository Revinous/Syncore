import { Surface } from "./Surface";
import { StatusBadge } from "./StatusBadge";
import type { DiagnosticsProviderStatus } from "../lib/types";

type Props = {
  title: string;
  description: string;
  provider: DiagnosticsProviderStatus;
  footerNote?: string;
};

function providerStatus(provider: DiagnosticsProviderStatus): "completed" | "blocked" | "pending" {
  if (provider.executable) return "completed";
  if (provider.provider_registered || provider.authenticated) return "blocked";
  return "pending";
}

export default function ExperimentalProviderPanel({
  title,
  description,
  provider,
  footerNote,
}: Props) {
  return (
    <Surface title={title} description={description}>
      <div className="meta-grid">
        <div className="meta-card"><span className="meta-label">Provider</span><div className="meta-value">{provider.provider ?? "unknown"}</div></div>
        <div className="meta-card"><span className="meta-label">Mode</span><div className="meta-value">{provider.mode ?? "none"}</div></div>
        <div className="meta-card"><span className="meta-label">Registered</span><div className="meta-value">{String(provider.provider_registered)}</div></div>
        <div className="meta-card"><span className="meta-label">Executable</span><div className="meta-value"><StatusBadge status={providerStatus(provider)} /></div></div>
        {provider.reachable !== null ? (
          <div className="meta-card"><span className="meta-label">Reachable</span><div className="meta-value"><StatusBadge status={provider.reachable ? "completed" : provider.enabled ? "blocked" : "pending"} /></div></div>
        ) : null}
        {provider.authenticated !== null ? (
          <div className="meta-card"><span className="meta-label">Authenticated</span><div className="meta-value">{String(provider.authenticated)}</div></div>
        ) : null}
        {provider.storage_secure !== null ? (
          <div className="meta-card"><span className="meta-label">Storage Secure</span><div className="meta-value">{String(provider.storage_secure)}</div></div>
        ) : null}
      </div>
      <div className="meta-card" style={{ marginTop: 16 }}>
        <span className="meta-label">Warning</span>
        <div className="meta-value">{provider.warning ?? "none"}</div>
      </div>
      <div className="meta-card" style={{ marginTop: 16 }}>
        <span className="meta-label">Detail</span>
        <div className="meta-value">{provider.detail ?? "none"}</div>
        {provider.base_url ? <div className="helper-text" style={{ marginTop: 8 }}>Base URL: {provider.base_url}</div> : null}
        {provider.token_path ? <div className="helper-text" style={{ marginTop: 8 }}>Token path: {provider.token_path}</div> : null}
        {provider.expires_at ? <div className="helper-text" style={{ marginTop: 8 }}>Expires: {provider.expires_at}</div> : null}
      </div>
      <div className="meta-card" style={{ marginTop: 16 }}>
        <span className="meta-label">Recommended Action</span>
        <div className="meta-value">{provider.recommended_action ?? "none"}</div>
        {provider.required_settings.length ? (
          <div className="helper-text" style={{ marginTop: 8 }}>
            Required settings: {provider.required_settings.join(", ")}
          </div>
        ) : null}
        {footerNote ? <div className="helper-text" style={{ marginTop: 8 }}>{footerNote}</div> : null}
      </div>
    </Surface>
  );
}

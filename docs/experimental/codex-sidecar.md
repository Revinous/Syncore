# Experimental Codex Sidecar

`codex_sidecar` is Syncore's experimental bridge mode for ChatGPT/Codex-backed execution through a local sidecar.

This is **not** official OpenAI Platform API authentication.

## What It Is

- A local OpenAI-compatible upstream that Syncore can call as a run provider
- Intended for technical users running a local sidecar such as `CLIProxyAPI`
- Explicitly separate from the supported `OPENAI_API_KEY` path

## What It Is Not

- A replacement for `OPENAI_API_KEY`
- An enterprise-supported provider mode
- A guarantee of upstream stability

## Required Settings

Set these in your local `.env`:

```bash
CODEX_SIDECAR_ENABLED=true
CODEX_SIDECAR_BASE_URL=http://127.0.0.1:4010
CODEX_SIDECAR_API_KEY=...
```

## Verify It

Use:

```bash
syncore diagnostics
syncore providers
```

You should see:

- provider `codex_sidecar`
- explicit `experimental` mode
- executable only when the sidecar is reachable

## Use It

Select it explicitly when creating or switching provider strategy for a task or run.

Do not treat it as the default OpenAI mode.

## Operator Guidance

- If diagnostics says the sidecar is not reachable, fix the sidecar first
- If diagnostics says API key or base URL is missing, fix configuration first
- If you want official OpenAI Platform access, use `OPENAI_API_KEY` instead

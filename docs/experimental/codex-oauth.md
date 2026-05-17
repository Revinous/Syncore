# Experimental Native Codex OAuth

`codex_oauth_experimental` is Syncore's local native OAuth prototype for ChatGPT/Codex-style credentials.

This is **not** official OpenAI Platform API authentication.

## Current State

Today this mode is:

- local-only
- experimental
- directly executable through `codex_oauth_experimental`

That means:

- you can create and inspect local credentials
- you can refresh them when a refresh token exists
- Syncore does **not** use this provider for native execution yet

For actual experimental execution today, use `codex_sidecar`.

## Commands

Inspect current state:

```bash
syncore auth codex status
```

Start browser login:

```bash
syncore auth codex login
```

Use device fallback:

```bash
syncore auth codex login --device
```

Refresh stored credentials:

```bash
syncore auth codex refresh
```

Delete stored credentials:

```bash
syncore auth codex logout
```

## Storage

Credentials are stored locally under:

```text
~/.syncore/auth/codex/token.json
```

Syncore hardens this storage by:

- writing credentials atomically
- using restrictive directory permissions
- using restrictive file permissions
- reporting storage security state in diagnostics

## Verify It

Use:

```bash
syncore auth codex status
syncore diagnostics
```

Diagnostics will show:

- `codex_oauth_experimental`
- whether credentials are present
- whether storage is secure
- that the provider is authenticated and executable

## Boundary

Do not present this mode as:

- OpenAI OAuth support
- a supported enterprise auth path
- a replacement for API keys

The supported official OpenAI path remains `OPENAI_API_KEY`.

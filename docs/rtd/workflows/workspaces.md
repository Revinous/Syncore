# Workspace Lifecycle

1. Register workspace: `syncore workspace add ./repo --name repo`
2. Scan workspace: `syncore workspace scan repo`
3. Inspect safe file listing: `syncore workspace files repo`
4. Create task scoped to workspace

Safety rules enforce root boundaries and block secret-like files by default.

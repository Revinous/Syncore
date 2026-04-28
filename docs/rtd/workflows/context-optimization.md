# Context Optimization

Syncore uses an internal context optimization layer (not a proxy).

Pipeline:
1. Assemble raw context
2. Preserve critical constraints verbatim
3. Compress/summarize low-value context
4. Replace heavy content with references
5. Persist full originals for retrieval
6. Return optimized bundle

Core endpoints:
- `POST /context/assemble`
- `GET /context/references/{ref_id}`

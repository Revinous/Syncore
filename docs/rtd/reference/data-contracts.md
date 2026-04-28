# Data Contracts

This section describes the most important entities consumed by API clients.

## Workspace

- identifier and metadata for bounded repository access
- includes scan-derived metadata

## Task

- unit of work lifecycle state
- may contain preferred provider/model

## AgentRun

- execution unit tied to task and role

## ProjectEvent

- timestamped timeline entry

## BatonPacket

- handoff payload across phases/roles

## RoutingDecision

- next-action recommendation

## ContextBundle / OptimizedContextBundle

- assembled and optimized model input data

## ContextReference

- pointer to stored heavy content with retrieval hint

## ExecutiveDigest

- analyst summary for task/project status

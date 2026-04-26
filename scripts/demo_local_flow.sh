#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${ORCHESTRATOR_BASE_URL:-http://localhost:8000}"
PAYLOAD_DIR="scripts/payloads"

post_json() {
  local path="$1"
  local payload="$2"
  curl -fsS -X POST "${BASE_URL}${path}" \
    -H "Content-Type: application/json" \
    -d "${payload}"
}

patch_json() {
  local path="$1"
  local payload="$2"
  curl -fsS -X PATCH "${BASE_URL}${path}" \
    -H "Content-Type: application/json" \
    -d "${payload}"
}

inject_task_id() {
  local file="$1"
  local task_id="$2"
  python3 - "$file" "$task_id" <<'PY'
import json,sys
payload_file,task_id=sys.argv[1],sys.argv[2]
with open(payload_file,'r',encoding='utf-8') as f:
    payload=json.load(f)
payload['task_id']=task_id
print(json.dumps(payload))
PY
}

extract_id() {
  python3 -c "import json,sys; print(json.loads(sys.stdin.read())['id'])"
}

printf "[demo-local] verifying orchestrator health...\n"
curl -fsS "${BASE_URL}/health" >/dev/null

printf "[demo-local] creating task...\n"
task_payload="$(cat "${PAYLOAD_DIR}/task_create.json")"
task_response="$(post_json "/tasks" "${task_payload}")"
task_id="$(printf '%s' "$task_response" | extract_id)"
printf "[demo-local] task_id=%s\n" "$task_id"

printf "[demo-local] creating planner run...\n"
planner_payload="$(inject_task_id "${PAYLOAD_DIR}/agent_run_planner.json" "$task_id")"
planner_response="$(post_json "/agent-runs" "$planner_payload")"
planner_run_id="$(printf '%s' "$planner_response" | extract_id)"
printf "[demo-local] planner_run_id=%s\n" "$planner_run_id"

printf "[demo-local] writing planner events...\n"
event_started_payload="$(inject_task_id "${PAYLOAD_DIR}/project_event_started.json" "$task_id")"
post_json "/project-events" "$event_started_payload" >/dev/null

event_plan_payload="$(inject_task_id "${PAYLOAD_DIR}/project_event_plan_drafted.json" "$task_id")"
post_json "/project-events" "$event_plan_payload" >/dev/null

printf "[demo-local] creating baton packet...\n"
baton_payload="$(inject_task_id "${PAYLOAD_DIR}/baton_packet.json" "$task_id")"
baton_response="$(post_json "/baton-packets" "$baton_payload")"
packet_id="$(printf '%s' "$baton_response" | extract_id)"
printf "[demo-local] packet_id=%s\n" "$packet_id"

printf "[demo-local] creating coder run...\n"
coder_payload="$(inject_task_id "${PAYLOAD_DIR}/agent_run_coder.json" "$task_id")"
coder_response="$(post_json "/agent-runs" "$coder_payload")"
coder_run_id="$(printf '%s' "$coder_response" | extract_id)"
printf "[demo-local] coder_run_id=%s\n" "$coder_run_id"

printf "[demo-local] updating coder run status...\n"
patch_json "/agent-runs/${coder_run_id}" '{"status":"completed","output_summary":"Implemented routes and local demo tooling"}' >/dev/null

printf "[demo-local] writing completion event...\n"
event_completed_payload="$(inject_task_id "${PAYLOAD_DIR}/project_event_implementation_completed.json" "$task_id")"
post_json "/project-events" "$event_completed_payload" >/dev/null

printf "[demo-local] requesting routing decision...\n"
routing_payload="$(cat "${PAYLOAD_DIR}/routing_decide.json")"
routing_response="$(post_json "/routing/decide" "$routing_payload")"

printf "[demo-local] checking memory lookup...\n"
memory_payload="$(inject_task_id "${PAYLOAD_DIR}/memory_lookup.json" "$task_id")"
memory_response="$(post_json "/memory/lookup" "$memory_payload")"

printf "[demo-local] checking context bundle...\n"
context_response="$(curl -fsS "${BASE_URL}/context/${task_id}")"

printf "[demo-local] loading task detail and digest...\n"
task_detail="$(curl -fsS "${BASE_URL}/tasks/${task_id}")"
digest="$(curl -fsS "${BASE_URL}/analyst/digest/${task_id}")"

printf "\n[demo-local] ✅ demo completed successfully\n"
printf "Task URL: %s/tasks/%s\n" "$BASE_URL" "$task_id"
printf "Digest URL: %s/analyst/digest/%s\n" "$BASE_URL" "$task_id"
printf "Baton list URL: %s/baton-packets/%s\n" "$BASE_URL" "$task_id"
printf "Context URL: %s/context/%s\n" "$BASE_URL" "$task_id"
printf "UI URL: http://localhost:3000/?taskId=%s\n" "$task_id"

printf "\nRouting decision:\n%s\n" "$routing_response"
printf "\nMemory lookup:\n%s\n" "$memory_response"
printf "\nContext bundle:\n%s\n" "$context_response"
printf "\nTask detail:\n%s\n" "$task_detail"
printf "\nDigest:\n%s\n" "$digest"

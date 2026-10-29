#!/usr/bin/env bash
# End-to-end check against a running docker compose stack.
# Usage: ./scripts/e2e.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-http://127.0.0.1:8000}"
API_KEY="${API_KEY:-dev-api-key}"
WEBHOOK_PORT="${WEBHOOK_PORT:-9000}"
EVENTS="$ROOT/webhook-events.jsonl"
RECEIVER_PID=""

cleanup() {
  if [[ -n "$RECEIVER_PID" ]]; then
    kill "$RECEIVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "waiting for API"
for _ in $(seq 1 60); do
  if curl -fsS "$API_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "$API_URL/health" >/dev/null

rm -f "$EVENTS"
python3 "$ROOT/scripts/webhook_receiver.py" "$EVENTS" "$WEBHOOK_PORT" &
RECEIVER_PID=$!
sleep 0.5

KEY="e2e-$(date +%s)"
BODY=$(cat <<EOF
{"amount":"1500.50","currency":"RUB","description":"Order 1001","metadata":{"order_id":"1001"},"webhook_url":"http://host.docker.internal:${WEBHOOK_PORT}/webhook"}
EOF
)

echo "creating payment"
CREATED=$(curl -fsS -X POST "$API_URL/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $KEY" \
  -d "$BODY")
echo "$CREATED"
PAYMENT_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["payment_id"])' <<<"$CREATED")

echo "replaying the same request"
REPLAY=$(curl -fsS -X POST "$API_URL/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $KEY" \
  -d "$BODY")
REPLAY_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["payment_id"])' <<<"$REPLAY")
if [[ "$REPLAY_ID" != "$PAYMENT_ID" ]]; then
  echo "idempotent replay returned a different payment" >&2
  exit 1
fi

echo "sending a conflicting body"
CONFLICT=$(curl -sS -o /tmp/payment-conflict.json -w "%{http_code}" -X POST "$API_URL/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $KEY" \
  -d '{"amount":"1.00","currency":"USD","description":"other","webhook_url":"https://merchant.example/other"}')
if [[ "$CONFLICT" != "409" ]]; then
  echo "expected 409, got $CONFLICT" >&2
  cat /tmp/payment-conflict.json >&2
  exit 1
fi

echo "waiting until payment $PAYMENT_ID is settled"
STATUS=""
for _ in $(seq 1 40); do
  DETAIL=$(curl -fsS "$API_URL/api/v1/payments/$PAYMENT_ID" -H "X-API-Key: $API_KEY")
  STATUS=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$DETAIL")
  if [[ "$STATUS" != "pending" ]]; then
    break
  fi
  sleep 1
done

if [[ "$STATUS" == "pending" ]]; then
  echo "payment stayed pending" >&2
  exit 1
fi
echo "payment status=$STATUS"

echo "waiting for webhook"
FOUND=0
for _ in $(seq 1 20); do
  if [[ -f "$EVENTS" ]] && grep -q "$PAYMENT_ID" "$EVENTS"; then
    FOUND=1
    break
  fi
  sleep 1
done
if [[ "$FOUND" != "1" ]]; then
  echo "webhook was not received" >&2
  exit 1
fi

echo "ok payment_id=$PAYMENT_ID status=$STATUS"

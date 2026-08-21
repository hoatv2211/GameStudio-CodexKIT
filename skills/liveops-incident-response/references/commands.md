# Liveops Incident Command Reference

Every command below is read-only observation. Service control, traffic shifts, rollback, database writes, bans, credential rotation, and public communication are **not** covered here; they require explicit authority for the exact action and otherwise remain `BLOCKED`.

## Establish identity before diagnosis

An incident report without build and configuration identity cannot be correlated with a deploy.

```bash
kubectl -n prod get deploy -o wide
kubectl -n prod get pods -l app=game-server -o wide
kubectl -n prod rollout history deployment/game-server
```

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.RunningFor}}'
systemctl status game-server --no-pager
```

```bash
curl -fsS http://127.0.0.1:8080/version
curl -fsS -o /dev/null -w 'health=%{http_code} time=%{time_total}s\n' http://127.0.0.1:8080/healthz
```

Record the image tag or commit actually running, not the one that was supposed to ship. The two differing is itself a finding.

## Build the timeline

Timestamps must be absolute and timezone-qualified. Relative phrasing like "20 minutes ago" is unusable in a post-incident review.

```bash
date -u +'%Y-%m-%dT%H:%M:%SZ'
kubectl -n prod logs deployment/game-server --since=30m --timestamps | tail -400
kubectl -n prod logs deployment/game-server --previous --timestamps | tail -200
journalctl -u game-server --since '30 min ago' --no-pager -o short-iso | tail -400
```

`--previous` retrieves the crashed container's log and is usually where the real cause is. Missing it and reading only the restarted container is a routine investigative error.

```bash
kubectl -n prod get events --sort-by=.lastTimestamp | tail -40
kubectl -n prod describe pod <pod> | rg -n 'Last State|Reason|Exit Code|OOMKilled|Restart Count'
```

`OOMKilled` and a non-zero exit code are hard facts; treat any narrative that contradicts them as `Unverified`.

## Correlate with deploys and configuration

```bash
git log --since='6 hours ago' --date=iso-strict --pretty='%h %ad %an %s' | cat
git diff --stat <last-known-good>..<current> | tail -30
```

```bash
kubectl -n prod get configmap game-config -o json | jq '{metadata: {name: .metadata.name, namespace: .metadata.namespace, resourceVersion: .metadata.resourceVersion}, data_keys: ((.data // {}) | keys)}'
kubectl -n prod rollout status deployment/game-server --timeout=10s
```

This intentionally emits metadata and data-key names only; it never emits ConfigMap values. If `jq` is unavailable, mark this observation `BLOCKED` rather than dumping the manifest. Project-specific allowlisted value inspection belongs in an approved runbook.

## Measure impact with more than one indicator

```bash
curl -fsSG --data-urlencode 'query=sum(rate(http_requests_total{status=~"5.."}[5m]))' http://prometheus:9090/api/v1/query
curl -fsSG --data-urlencode 'query=histogram_quantile(0.99,sum(rate(request_duration_seconds_bucket[5m]))by(le))' http://prometheus:9090/api/v1/query
curl -fsSG --data-urlencode 'query=sum(game_sessions_active)' http://prometheus:9090/api/v1/query
```

`--data-urlencode` keeps PromQL braces and range selectors out of curl's URL-globbing parser while preserving the query sent to Prometheus.

```sql
-- Read-only. Bound the range; never run an unbounded scan during an incident.
SELECT COUNT(*) AS failed_logins
FROM auth_log
WHERE created_at >= NOW() - INTERVAL 30 MINUTE AND result <> 'ok';
```

```bash
mysql --defaults-file=/etc/mysql/readonly.cnf -e "SHOW PROCESSLIST;" | head -40
mysql --defaults-file=/etc/mysql/readonly.cnf -e "SHOW ENGINE INNODB STATUS\G" | rg -n 'DEADLOCK|LATEST DETECTED'
```

Pass credentials through a defaults file or environment, never inline on the command line where they land in shell history and in the incident record.

Recovery requires a player-facing indicator (active sessions, successful logins, completed transactions) **and** a system indicator (error rate, latency, saturation). Alert silence alone is not recovery; an alerting pipeline that is itself down is silent too.

## Exploit and abuse indicators

```bash
kubectl -n prod logs deployment/game-server --since=1h | rg -n 'anti_cheat|invalid_packet|rate_limit|replay_detected' | head -60
rg -c 'opcode=0x[0-9a-f]+ rejected' /var/log/game/gateway.log
```

Suspected exploitation escalates to `network-authority-and-exploit-review` and to the security owner. Do not ban accounts or rotate credentials from this workflow.

## Actions that stay BLOCKED without explicit authority

| Action | Required before proceeding |
|---|---|
| `kubectl rollout undo` / restart / scale | Named approver, exact deployment, rollback target, dry run |
| Traffic shift, feature flag, maintenance mode | Named approver plus stated player impact |
| Any DB write, schema change, or data repair | Approval plus `game-database-migration-safety` |
| Account bans, item rollbacks, compensation | Approval plus abuse evidence and audit trail |
| Credential or token rotation | Security owner approval |
| Public status post or player communication | Communication owner approval |

Record each as a proposed action with its risk, its blast radius, its reversal path, and its blocking approver. Urgency never expands authority.

## Evidence

Record UTC start time, severity, affected services and regions, running image or commit, the timeline with absolute timestamps and named actors, the exact read-only commands and their outputs, the impact indicators from both player-facing and system sources, hypotheses kept separate from facts, every proposed action with its approver, blocked actions with reasons, the recovery validation across multiple indicators, the monitoring window, and residual risks.

Never paste secrets, tokens, or player personal data into the incident record. When observability, log retention, or database access is unavailable, that portion of the analysis is `BLOCKED` and cannot be inferred from the remaining signals.

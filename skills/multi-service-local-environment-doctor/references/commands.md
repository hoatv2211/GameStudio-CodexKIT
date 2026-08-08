# Local Environment Command Reference

These commands collect read-only snapshots. They do not authorize stopping processes, restarting services, editing configs, or changing firewall rules.

## Windows ports and processes

```powershell
Get-NetTCPConnection -State Listen |
  Sort-Object LocalPort |
  Select-Object LocalAddress,LocalPort,OwningProcess

Get-NetTCPConnection -LocalPort 3306,3307 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess

Get-Process -Id 1234 | Select-Object Id,ProcessName,Path,StartTime
Get-CimInstance Win32_Service | Select-Object Name,State,StartMode,PathName
```

## Linux ports and processes

```bash
ss -lntp
ss -lntp '( sport = :3306 or sport = :3307 )'
lsof -nP -iTCP:3306 -sTCP:LISTEN
lsof -nP -iTCP:3307 -sTCP:LISTEN
ps -fp PID
systemctl status SERVICE_NAME --no-pager
```

## Configuration snapshot

Search only the named project and exclude secrets or generated output.

```powershell
rg -n --glob '!**/logs/**' --glob '!**/secrets/**' '3306|3307|27000|redis|mysql' D:\Projects\MyGame
```

```bash
rg -n --glob '!**/logs/**' --glob '!**/secrets/**' '3306|3307|27000|redis|mysql' /srv/my-game
```

## Evidence

Record expected port, configured port, observed listener, owning process path, service name, project ownership, command, timestamp, and limitations.

Do not kill an unknown process to free a port. Do not treat a listener as proof that the correct executable or database owns it. Service-control actions require explicit approval.

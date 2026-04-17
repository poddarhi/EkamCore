# Hub Unreachable

This page helps you diagnose and fix problems where the EkamCore web
interface or mobile app cannot connect to the hub.

## Symptoms

- The mobile app shows **DISCONNECTED_EMPTY** or **DISCONNECTED_CACHED**.
- The web browser shows "Unable to connect" or a timeout error.
- The mobile app's **Test Connection** button fails.

## Step-by-step diagnosis

Work through each check in order. Stop when you find the problem.

### 1. Is Docker running?

The most common cause is Docker not being active.

- Open **Docker Desktop** or **OrbStack** and verify it shows a running state.
- Or run in a terminal:
  ```
  docker info
  ```
  If this returns an error, Docker is not running. Start it and wait for it
  to finish initializing. See
  [Docker Not Running](docker-not-running.md) for detailed steps.

### 2. Are EkamCore services healthy?

- Open the **Manager** app and check the dashboard.
- All ten service tiles should be green. If any are red, click the tile to
  view logs.
- Try clicking **Stop All**, wait five seconds, then **Start All** to
  restart everything.
- If a specific service stays red, check
  [Disk Full](disk-full.md) (PostgreSQL often fails when disk is low).

### 3. Is Tailscale connected? (mobile only)

- On your phone, open the **Tailscale** app and confirm it shows
  **Connected**.
- On your Mac, click the Tailscale menu-bar icon and verify it is
  connected to the same tailnet.
- If either device is disconnected, toggle Tailscale off and on.
- See [Tailscale Setup](../mobile/tailscale-setup.md) for initial
  configuration.

### 4. Is the Mac awake?

If your Mac is asleep or the lid is closed, EkamCore services are paused.

- Wake the Mac by pressing a key or opening the lid.
- To prevent sleep during active use, go to **System Settings > Energy**
  and enable "Prevent automatic sleeping when the display is off".

### 5. Is a firewall blocking the port?

EkamCore uses port 443 by default.

- Open **System Settings > Network > Firewall**.
- If the firewall is on, make sure incoming connections for Docker (or
  OrbStack) are allowed.
- Temporarily disable the firewall to test. If that fixes it, add a rule
  to allow port 443.

### 6. Try a direct connection

From the device that cannot connect, try reaching the hub directly:

```
curl -k https://<tailscale-ip>:443/api/health
```

A healthy hub responds with `{"status":"ok"}`. If you get no response, the
issue is network-level. If you get an error JSON, the issue is with a
specific service.

## If nothing works

1. Open the Manager and go to **Diagnostics > Export Support Bundle**.
2. The bundle contains logs from all services and the watchdog.
3. File an issue on the EkamCore GitHub repository and attach the bundle.

# Docker Not Running

EkamCore uses Docker containers for all its services. If Docker is not
running, nothing works.

## Symptoms

- The Manager dashboard shows all service tiles as gray (Stopped).
- The Manager shows an error banner: "Docker engine not available".
- Running `docker info` in a terminal returns a connection error.
- The web interface and mobile app cannot reach the hub.

## Which Docker runtime?

EkamCore works with either **Docker Desktop** or **OrbStack**. Check which
one you have installed:

- Look for **Docker Desktop** in your Applications folder or Dock.
- Look for **OrbStack** in your Applications folder or menu bar.

If neither is installed, follow the
[Installation guide](../getting-started/installation.md) to set up your
environment.

## Start Docker

### Docker Desktop

1. Open **Docker Desktop** from your Applications folder.
2. Wait for the whale icon in the menu bar to stop animating. This means
   the engine is ready.
3. If Docker Desktop asks you to complete setup or accept terms, do so.

### OrbStack

1. Open **OrbStack** from your Applications folder.
2. The menu-bar icon appears almost immediately. OrbStack starts faster
   than Docker Desktop.

## Verify Docker is running

Open a terminal and run:

```
docker info
```

You should see output including `Server Version` and `Operating System`.
If you see an error like "Cannot connect to the Docker daemon", the engine
is still starting -- wait a few seconds and try again.

## Start EkamCore services

Once Docker is confirmed running:

1. Open the **Manager** app.
2. Click **Start All** on the dashboard.
3. Wait for all ten service tiles to turn green.

If the Manager was already open when Docker started, it detects the engine
automatically and enables the **Start All** button within a few seconds.

## Auto-start Docker on login

To avoid this problem in the future, configure your Docker runtime to
launch at login:

- **Docker Desktop**: Open Docker Desktop > Settings > General > check
  "Start Docker Desktop when you sign in to your computer".
- **OrbStack**: OrbStack starts at login by default. Verify in OrbStack >
  Settings > General > "Start at login".

Also ensure the Manager itself is set to auto-start (see
[Settings Reference](../settings/settings-reference.md)).

## Still not working?

If Docker starts but EkamCore services fail to come up, check
[Hub Unreachable](hub-unreachable.md) for further diagnosis. If Docker
itself will not start, consult the
[Docker Desktop docs](https://docs.docker.com/desktop/troubleshoot/overview/)
or [OrbStack docs](https://docs.orbstack.dev/).

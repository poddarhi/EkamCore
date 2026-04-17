# Mobile Connection Issues

If the EkamCore mobile app cannot connect to your hub, work through these
checks in order.

## Symptoms

- The app shows **DISCONNECTED_EMPTY** or a full-screen error.
- Tapping **Test Connection** in Settings fails.
- Data is stale and never refreshes.
- The app shows the **HUB_SLEEPING** banner.

## Step 1 -- Verify Tailscale on both devices

Tailscale must be connected on both your phone and your Mac.

1. On your **phone**, open the Tailscale app. Confirm it shows
   **Connected** and your Mac appears in the device list.
2. On your **Mac**, click the Tailscale menu-bar icon. Confirm it shows
   **Connected** and your phone appears in the device list.
3. If either device is disconnected, toggle Tailscale off and back on.
4. If your Tailscale account session has expired, sign in again on both
   devices.

See [Tailscale Setup](../mobile/tailscale-setup.md) if you have not
configured Tailscale yet.

## Step 2 -- Verify the hub URL

1. Open the EkamCore mobile app and go to the **Settings** tab.
2. Check the **Hub URL** field. It should look like
   `https://100.64.1.10:443` or `https://your-mac.tail1234.ts.net:443`.
3. Make sure:
   - The URL starts with `https://`.
   - The port number is correct (default is `443`).
   - There are no trailing spaces or extra characters.
4. If you changed your Mac's Tailscale IP (rare), update the URL here.

## Step 3 -- Use the Test Connection button

1. After confirming the URL, tap **Test Connection**.
2. Possible results:
   - **Green checkmark**: The hub is reachable. If you still see stale
     data, pull to refresh on the affected tab.
   - **Red X with "Connection refused"**: EkamCore services are not
     running. Open the Manager on your Mac and click **Start All**.
   - **Red X with "Timed out"**: The network path is blocked. Continue
     to step 4.
   - **Red X with "Certificate error"**: The hub's TLS certificate is
     not trusted. This can happen after a reinstall. Go to Settings >
     Hub URL and re-enter the URL to refresh the certificate trust.

## Step 4 -- Check if your Mac is awake

When your Mac sleeps, Docker containers are paused and the hub becomes
unreachable.

- Wake your Mac by pressing a key or opening the lid.
- If you frequently access EkamCore remotely, prevent sleep by going to
  **System Settings > Energy** and enabling "Prevent automatic sleeping
  when the display is off".
- If the app shows the **HUB_SLEEPING** banner, this confirms the Mac is
  asleep.

## Step 5 -- Test from the Mac itself

To confirm the issue is network-related and not a service problem:

1. On your Mac, open a browser and go to `https://localhost:443`.
2. If the EkamCore web interface loads, the services are fine and the
   problem is between your phone and Mac.
3. If the web interface does not load, see
   [Hub Unreachable](hub-unreachable.md) for service-level diagnosis.

## Step 6 -- Restart the network stack

If all the above checks pass but the app still cannot connect:

1. On your phone: toggle Airplane Mode on, wait five seconds, toggle it
   off.
2. On your Mac: run `sudo killall -HUP mDNSResponder` in a terminal to
   flush DNS.
3. Restart Tailscale on both devices.
4. Try **Test Connection** again.

## Still stuck?

Export a support bundle from the Manager (**Diagnostics > Export Support
Bundle**) and file an issue on the EkamCore GitHub repository.

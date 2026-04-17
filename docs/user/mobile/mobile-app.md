# Mobile App

The EkamCore mobile app gives you access to your Today briefing, Recap,
search, and People graph from your iPhone or iPad.

## Install

1. Download **EkamCore** from the iOS App Store.
2. Open the app. You will see the **Connect to Hub** screen.

## Connect to your hub

1. Tap **Enter Hub URL**.
2. Type your Mac's Tailscale IP followed by the port, for example
   `https://100.64.1.10:443`. If you enabled MagicDNS you can use the
   friendly name instead, such as `https://your-mac.tail1234.ts.net:443`.
3. Tap **Test Connection**. A green checkmark confirms the app can reach
   your hub.
4. Tap **Continue**.

If the test fails, see [Tailscale Setup](tailscale-setup.md) to verify your
network connection.

## Log in

1. Enter the same username and password you use on the EkamCore web
   interface.
2. Tap **Sign In**.
3. On success you land on the **Today** tab.

Your session token is stored in the iOS keychain and refreshes
automatically. You should not need to log in again unless you explicitly
log out.

## Set up biometric unlock

Biometric unlock lets you open the app with Face ID or Touch ID instead of
entering your password each time.

1. Go to the **Settings** tab.
2. Toggle **Biometric Unlock** on.
3. Authenticate with Face ID or Touch ID when prompted.
4. From now on the app presents a biometric prompt on launch instead of the
   password screen.

You can disable biometric unlock at any time from the same toggle.

## The five tabs

| Tab | What it shows |
|-----|---------------|
| **Today** | Your daily briefing cards -- calendar events, tasks, weather, suggested actions. |
| **Recap** | A summary of yesterday's activity, completed tasks, and highlights. |
| **Search** | Natural-language search across all your indexed documents, photos, and notes. |
| **People** | Your People graph with person profiles, recent interactions, and face clusters. |
| **Settings** | Hub URL, cache size, biometric toggle, appearance, and logout. |

## Tips

- **Pull to refresh** on Today and Recap to fetch the latest data from your
  hub.
- **Search** supports the same natural-language queries as the web
  interface, for example "photos from last weekend" or "emails about the
  project deadline".
- **People** shows the same profiles and face clusters configured on the web.
  Edits sync back to the hub automatically.

## Logging out

Go to **Settings > Log Out**. This clears your session token, cached data,
and any biometric credentials from the device. See
[Offline Behavior](offline-behavior.md) for details on what is cached and
how it is wiped.

## Next step

Read [Offline Behavior](offline-behavior.md) to understand what happens
when your phone cannot reach the hub.

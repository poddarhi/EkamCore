# Tailscale Setup

Tailscale creates a private network between your Mac and your phone so you
can reach EkamCore from anywhere without exposing it to the public internet.

## What you need

- Your Mac running EkamCore.
- An iPhone (iOS 15 or later) or iPad.
- A free Tailscale account.

## Step 1 -- Install Tailscale on your Mac

1. Download **Tailscale** from the Mac App Store.
2. Open Tailscale. It appears as a small icon in the menu bar.
3. Click the icon and choose **Log in**. Sign in with Google, Microsoft,
   GitHub, or Apple. This creates your tailnet (your private network).
4. After login the menu bar icon turns to a connected state. Note the IP
   address shown under your Mac's name (for example `100.64.1.10`). You will
   need this later.

## Step 2 -- Install Tailscale on your phone

1. Download **Tailscale** from the iOS App Store.
2. Open the app and sign in with the **same account** you used on your Mac.
3. Allow Tailscale to add a VPN configuration when prompted.
4. Once connected your phone appears in the same tailnet as your Mac.

## Step 3 -- Enable MagicDNS

MagicDNS lets you use friendly names instead of IP addresses.

1. Open [https://login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns)
   in a browser.
2. Under **MagicDNS**, click **Enable** if it is not already on.
3. Your Mac will be reachable at a name like `your-mac.tail1234.ts.net`.

## Step 4 -- Verify the connection

On your phone, open the Tailscale app and check that both your Mac and phone
show a green **Connected** status.

Test the link from your phone's terminal or browser:

```
ping 100.64.1.10
```

Replace `100.64.1.10` with your Mac's Tailscale IP. You should see replies
with low latency.

## Step 5 -- Access EkamCore

EkamCore listens on port 443 by default. Open Safari on your phone and go to:

```
https://100.64.1.10:443
```

Or, if MagicDNS is enabled:

```
https://your-mac.tail1234.ts.net:443
```

You should see the EkamCore login page.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Cannot see the Mac in Tailscale | Make sure both devices are logged in to the same account. |
| Ping works but browser fails | Confirm EkamCore services are running in the Manager. |
| Connection drops on mobile data | Tailscale works on cellular. Toggle airplane mode off and on. |
| MagicDNS name does not resolve | Wait a minute after enabling. Restart Tailscale on both devices. |

## Next step

Once you can reach EkamCore from your phone, continue to
[Mobile App Setup](mobile-app.md) to install and configure the EkamCore
mobile app.

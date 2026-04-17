╔══════════════════════════════════════════════════════════╗
║              EkamCore Manager — First Launch             ║
╚══════════════════════════════════════════════════════════╝

If macOS says the app "is damaged and can't be opened":

1. Open Terminal (search "Terminal" in Spotlight)
2. Copy and paste this command:

   xattr -cr "/Applications/EkamCore Manager.app"

3. Press Enter
4. Open EkamCore Manager from Applications

This is required because the app is not yet signed with an
Apple Developer certificate. This is safe — the app is
open-source at github.com/poddarhi/EkamCore


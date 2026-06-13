# EkamCore — Privacy Policy

**Effective date:** 2026-06-13
**App:** EkamCore (on-device AI chat)

> ⚙️ **Before publishing, confirm the 3 fields marked `‹…›` below** (developer/contact name,
> contact email, and the public URL you host this at). Everything else is accurate to the
> current app and ready to go. Host this page at a public URL and use that URL in both
> App Store Connect and Google Play Console.

EkamCore ("**the app**", "**we**", "**us**") is built and published by ‹DEVELOPER NAME / ENTITY›.
We designed EkamCore to be **private by default**: your conversations and the content you give it
stay on your device. This policy explains exactly what does and does not leave your device.

---

## The short version

- **Your chats, conversations, and attached images stay on your device.** We do not run servers
  that receive, store, or process them. We cannot read them.
- **We do not collect personal information, run analytics, track you, or show ads.**
- **There is no account and no login.**
- The app **does connect to the internet** for two limited, non-personal purposes: (1) downloading
  AI model files and browsing the model catalog, and (2) — only if **you** turn it on — sending your
  messages to a custom AI endpoint **you** configure. Details below.

---

## What stays on your device (always)

- **Conversations and messages** — stored locally in the app's on-device storage.
- **Attached images / photos** — stored locally in the app's file storage. Deleting a conversation
  removes its images from your device.
- **App settings and preferences.**
- **AI inference** — the AI model runs **entirely on your device**. Your prompts are processed
  locally; generating a reply does not send your chat anywhere.

We have no access to any of the above. It is not transmitted to us.

## What the app sends over the network (and to whom)

EkamCore makes network requests **only** in these cases, and **none of them include your chats**:

1. **Downloading AI models and browsing the catalog.** To get a model, the app downloads model
   files (GGUF) and reads catalog/search information from third-party sources such as **Hugging Face**
   and the app's model catalog host. These requests contain standard technical data (e.g. the file
   requested, your IP address as seen by that server, and a basic app user-agent). They do **not**
   contain your conversations or personal content. Your use of those third-party services is subject
   to **their** privacy policies (e.g. Hugging Face's).
2. **Optional custom AI endpoint (advanced, off by default).** If you choose to configure a remote
   model endpoint (for example your own server) and select it for a chat, then the messages in that
   chat are sent **to the endpoint you specified** so it can generate a reply. This happens only when
   you set it up and select it; the default on-device mode sends nothing. Data handling at that
   endpoint is governed by whoever operates it (which may be you).

We do not receive a copy of any of this.

## Permissions the app may request

- **Camera** — only when you take a photo to attach to a chat. Images stay on your device.
- **Photos / storage** — only when you attach an existing image, or to save downloaded models and
  chat images on your device.
- **Device information** — the app reads basic device capability info (such as total memory and
  device model) **on your device** to size the AI model appropriately. This is used locally and is
  not transmitted to us.

You can revoke these permissions at any time in your device settings.

## Data we collect

**None.** We do not collect, sell, share, or store your personal data. We do not use third-party
analytics, advertising, or tracking SDKs.

## Children's privacy

EkamCore is not directed to children under 13 (or the equivalent minimum age in your country) and we
do not knowingly collect personal information from children. As the app collects no personal data,
none is collected from children either.

## Data retention and deletion

Because your data lives only on your device, **you** control it. Deleting a conversation removes its
messages and attached images from your device. Uninstalling the app removes all app data, including
any downloaded models, conversations, and images.

## Security

Your content stays on your device and is protected by your device's own security (passcode,
biometrics, OS sandboxing). Network requests to download models use secure HTTPS connections.

## Changes to this policy

We may update this policy as the app evolves. We will post the updated version at the URL below and
revise the "Effective date" above. Material changes will be reflected here.

## Contact

Questions about this policy or your privacy: **ekamcore.ai@gmail.com**

_This policy is hosted at: ‹PUBLIC URL WHERE YOU HOST THIS PAGE›_

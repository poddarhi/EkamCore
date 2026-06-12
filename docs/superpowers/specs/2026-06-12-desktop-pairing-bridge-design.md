# Desktop ⇄ Phone Personal-Compute Bridge — Subsystem A (Secure Pairing) Design

_Date: 2026-06-12 · Status: design approved-in-principle, pending written-spec review_

This spec captures the full set of decisions made during brainstorming so they can be
revisited. It covers **Subsystem A (desktop agent + secure QR pairing)** plus the
**trivial Subsystem B (compute proxy)** folded into the same cycle. Subsystem C
(local resource access) is designed-for but **out of scope this cycle**.

---

## 1. Why this exists (strategic rationale)

Honest competitive read (confirmed against `docs/ROADMAP.md` and the code):

- **On-device LLM chat is table stakes, not a moat.** PocketPal, Private LLM, MLC,
  Jan, Enclave, GPT4All, OnDevice LLM all ship it. Persistent history and shallow
  fact-memory also already exist across competitors.
- **`src/services/remote.ts` as it stands is also not novel** — it is a manual
  Ollama/OpenAI HTTP client (user types a base URL + optional token). LMSA,
  Tailscale+Ollama, and similar prosumer setups already do exactly this.
- **The actual differentiation is packaging, not invention.** Nobody has assembled a
  **zero-config, phone-first, seamless, secure** bridge that lets a *non-technical*
  person use their home computer's compute (and later, its local resources) from
  their phone. Prosumer tools deliberately don't solve seamless pairing because their
  users don't need it. That gap is the wedge.

**Therefore:** the desktop app + secure QR pairing is not a feature on top of the
differentiator — for a non-technical audience it **is** the differentiator. Get the
trust + seamlessness right and we have something the crowded field lacks. Get it wrong
(clunky pairing, or "yet another remote Ollama client") and we're a worse PocketPal.

---

## 2. Scope: decomposition and what this cycle delivers

Option 2 ("compute + local resources") is the destination, but it is three stacked
subsystems with a strict dependency order. We build them in separate
brainstorm → spec → plan → implementation cycles.

| # | Subsystem | What it is | Depends on | This cycle? |
|---|-----------|-----------|------------|-------------|
| **A** | Desktop agent + secure pairing | Tray app the phone pairs with by QR over an encrypted, mutually-authenticated channel. The "no hacking" foundation. | — | **YES** |
| **B** | Compute proxy | Phone routes chat to the desktop's bundled model over that channel. | A | **YES (trivial, folded in)** |
| **C** | Local resource access | Phone asks about files/photos/notes; desktop indexes + retrieves with per-resource permission grants. | A (+B) | No — next cycle |

Everything rides on A. B is nearly free once A exists. C is the largest/richest and
gets its own future cycle.

---

## 3. Locked decisions (with rationale)

| Decision | Choice | Why |
|----------|--------|-----|
| **Scope this cycle** | A + trivial B | A is the riskiest (security) and unblocks everything; B is near-free on top. |
| **Connectivity** | **LAN now, architected for remote later** | Traffic never leaves home Wi-Fi → strongest, near-provable "no hacking" story and fastest to a shippable demo. Crypto identity layer is built remote-ready so remote is a later add-on, not a rewrite. |
| **Transport (v1)** | Noise-encrypted TCP over LAN | Simple, no servers to run, no internet-facing surface. |
| **Inference location** | **Desktop bundles its own engine** (llama.cpp baked in) | The whole point is seamlessness for non-technical users. Requiring Ollama would rebuild a prosumer tool and lose the wedge. (Auto-detect Ollama/LM Studio = later "#3 hybrid" evolution.) |
| **Desktop form factor** | **Tray / menu-bar background agent** (small window for QR + device list) | The phone is the primary UI; the desktop just shows a QR, runs the model, holds the channel, manages paired devices. |
| **Desktop stack** | **Tauri** (Rust core + system webview UI) | ~10MB binaries, low RAM, and Rust is the best fit for the crypto handshake, LAN socket, and native llama.cpp binding. Minimal UI still written in familiar web tech. Electron's ~100–150MB footprint undercuts the "quiet companion that also holds a model" feel. |

**Deferred to later cycles (designed-for, not built):**
- Remote access (out-of-home) — swap LAN TCP for WebRTC data channel + signaling/STUN/TURN.
- Hybrid inference (#3) — auto-detect and offer the user's existing Ollama/LM Studio.
- Subsystem C — local resource access (files/photos/notes) with permission grants.

### Cost note (for when remote is added later)
- **End user always pays $0.**
- **LAN v1: $0 infra** — nothing leaves the local network.
- **Future remote (WebRTC P2P + tiny signaling/TURN):** signaling is a few KB/connect
  (free/cheap hobby tier); ~80–90% of connections go **direct** (P2P, $0 bandwidth to
  us); only the ~10–20% that can't punch through NAT relay via TURN (small, usage-based,
  self-hostable via coturn). STUN (NAT discovery) is free/public; TURN (actual relay) is
  the only variable cost. This is strictly cheaper than relay-everything, which would
  pay for every user's every message.

---

## 4. Architecture & components

```
┌─────────────────────────┐         LAN (same Wi-Fi)          ┌──────────────────────────────┐
│  PHONE  (RN app, exists) │                                   │  DESKTOP AGENT (new, Tauri)  │
│                          │   1. scan QR (out-of-band trust)  │                              │
│  • QR scanner (new)      │ ───────────────────────────────▶ │  • Tray app + QR screen      │
│  • Noise client (new)    │                                   │  • Noise listener (TCP)      │
│  • paired-key store (new)│ ◀═══ 2. encrypted Noise channel ═▶│  • bundled llama.cpp engine  │
│  • chat UI (exists)      │        (mutually authenticated)   │  • paired-device store       │
│                          │   3. chat over channel ─▶ tokens  │  • mDNS advertise            │
└─────────────────────────┘                                   └──────────────────────────────┘
```

Four new building blocks, each independently testable:

1. **Identity layer (shared concept).** Each device has a long-term keypair. The
   desktop's public key travels out-of-band inside the QR, so the phone pins the
   desktop's real identity → LAN MITM/impersonation fails. After pairing, each side
   stores the other's public key; future connects need no QR.

2. **Desktop agent (Tauri, Rust core).** Modules: `pairing` (QR + handshake),
   `channel` (Noise-encrypted TCP transport), `inference` (bundled llama.cpp),
   `devices` (paired-key store + revoke), `discovery` (mDNS so the phone re-finds it
   after a DHCP IP change).

3. **Phone additions (RN).** QR scanner, Noise client, **secure** key store
   (Keychain/Keystore — *not* plain AsyncStorage), and a new chat **source = "My
   Computer"** alongside on-device `llama.rn`. Existing chat UI + model picker gain
   this backend option.

4. **Transport seam (remote-ready).** Noise is transport-agnostic; identity is
   key-based, not IP-based. v1 = Noise over LAN TCP. Remote later = swap *only* the
   transport (TCP → WebRTC data channel); pairing, keys, and channel encryption are
   untouched.

**Reuse note:** existing `src/services/remote.ts` (manual Ollama/OpenAI HTTP client)
stays as a separate "advanced/remote endpoint" feature. The new "My Computer" paired
path coexists with it.

---

## 5. Pairing & security model (the "no hacking" core)

Like pairing AirPods, but stronger:

1. **Computer shows a QR** containing: its identity public key + LAN address (IP:port)
   + a **one-time pairing code that expires in ~60 seconds** (single use).
2. **Phone scans it.** Having learned the computer's key by physically seeing the
   screen, the phone pins that identity — no one on the network can impersonate the
   computer.
3. **Computer asks to confirm:** prompt *"Allow 'Arpan's iPhone' to connect?"* → user
   clicks Allow. Defends against someone photographing the QR from a distance.
4. **Paired.** The two remember each other; reopening reconnects automatically with no
   re-scan. All traffic is **end-to-end encrypted** via the **Noise Protocol Framework**
   (standard, audited; same crypto family as WireGuard/Signal — no home-rolled crypto).
   Exact Noise pattern (a mutually-authenticated handshake seeded by the QR's one-time
   secret, with static-key pinning) finalized in the implementation plan.
5. **User stays in control.** Desktop "Paired devices" list → revoke instantly cuts a
   phone off. Phone stores its private key + paired desktop keys in device secure
   hardware (iOS Keychain / Android Keystore).

**Security summary (v1):** traffic never leaves home Wi-Fi; encryption is standard and
end-to-end; identities verified by the physical scan; pairing requires a physical
confirmation; one-time, short-TTL pairing code prevents stale-QR reuse.

---

## 6. UX flow

- Install **EkamCore desktop app** → it sits in the menu bar/tray and shows a QR.
- On phone: tap **"Connect my computer"** → scan → confirm on desktop → paired.
- In chat, a new **"My Computer"** source appears alongside on-device. Selecting it
  routes chat through the computer's bigger bundled model; answers **stream** back live.
- Out of Wi-Fi range → graceful fallback to on-device. (Remote access = future cycle.)

---

## 7. Build milestones (each independently shippable)

1. **Desktop skeleton** — Tauri tray app; shows pairing QR; listens for connections.
2. **Pairing** — phone scans; Noise handshake; both persist each other's keys; desktop
   confirmation prompt; "Paired devices" list + revoke.
3. **Chat through it (B)** — desktop bundles a default model; phone "My Computer" source
   streams answers over the encrypted channel.
4. **Polish** — auto-reconnect after DHCP IP change (mDNS); graceful on-device fallback;
   hardening.

---

## 8. Dependencies & risks to resolve in the plan

- **Phone:** a QR scanner (e.g. react-native-vision-camera), a Noise/crypto
  implementation usable from RN/JS, and secure key storage (e.g. react-native-keychain).
  **Riskiest item:** a solid, maintained Noise/crypto library on React Native — validate
  early.
- **Desktop:** Tauri; a Rust Noise lib (e.g. `snow`); mDNS (e.g. `mdns-sd`); a llama.cpp
  binding or bundled llama.cpp server binary; per-OS packaging/signing of the bundled
  runtime + (downloaded-on-first-run) default model.
- **New language surface:** Rust for the desktop core (new ground for the founder).
- **Bundled model size:** keep installer small — download a sensible default GGUF on
  first run rather than baking a large model into the installer.

---

## 9. Testing

- **Desktop (Rust):** unit tests for the Noise handshake + message framing; negative
  tests — wrong key rejected, expired/used pairing code rejected, unpaired phone rejected.
- **Phone:** pure-function tests for protocol message parse/encode (matches the existing
  `remote.ts` test style).
- **End-to-end:** manual pairing walk on real devices; revoke-then-reconnect; DHCP IP
  change reconnect; out-of-range fallback.

---

## 10. Open items for the implementation plan

- Exact Noise handshake pattern + key formats.
- Wire protocol/framing for chat requests + token streaming over the channel.
- mDNS service naming + how the phone relocates the desktop by stable device ID.
- Default bundled model choice + first-run download UX.
- Per-OS Tauri packaging/code-signing approach.

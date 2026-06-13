# EkamCore — "Own Your Intelligence": Vision, the Three Ideas & the Launch Roadmap

_Date: 2026-06-13 · Status: vision + roadmap (founding document) · Supersedes the framing of the
2026-06-12 bridge spec by **re-sequencing** it (see §7), not replacing it._

> **Read this first if you are new to the project.** This is the master document. It defines
> *what EkamCore is becoming*, *why it can win where the crowded field can't*, and — most
> importantly — *the exact order we ship it in so we actually launch instead of building forever.*
> Each phase below gets its own detailed spec + implementation plan when we reach it. This
> document is the map, not the turn-by-turn directions.

---

## 0. The one sentence

> **Own your intelligence.** A private brain that lives in your home and your pocket, remembers
> your whole life with zero effort, can never leak (and *proves* it), pools compute with the
> people you love, and one day becomes a model of *you* that you own forever — built on an
> **open standard** anyone can implement and nobody can take away.

On-device chat is the seed. The movement is the product.

---

## 1. The honest competitive read (why we need more than "another local LLM app")

We do not get to skip this. EkamCore today is a bare React Native app that downloads a GGUF and
chats offline (with a vision catalog + Hugging Face browse). That is **table stakes**, not a moat:

- **On-device chat is commodity.** PocketPal, Private LLM, Jan, Enclave, MLC, GPT4All, OnDevice
  LLM all ship it. A nicer one of these earns a polite Show HN and ~2k stars. It does not break
  records.
- **The desktop⇄phone bridge alone is also not novel.** **LM Studio "LM Link"** already keeps
  chat on the phone while heavy compute runs on a remote machine. Tailscale+Ollama, LMSA, and
  prosumer setups do the same. If our headline is *"my phone runs a 70B on my laptop,"* we are a
  prettier LM Link and we lose — they have years of head start and a desktop user base. Our own
  `src/services/remote.ts` is, today, just a manual Ollama/OpenAI HTTP client — the same prosumer
  pattern.
- **Obsidian** is the closest thing in spirit — local-first, you-own-the-files, "second brain,"
  great plugin ecosystem. But it is **effort-gated**: you only get value if you are the rare
  person who manually writes notes in markdown. That ceiling is ~1% of humanity. It is a power
  tool for PKM enthusiasts.
- **Rewind / Personal.ai** chase "a memory of you," but they are **closed, creepy** (screen
  recording), often Mac-only, and cloud-adjacent. Nobody can audit the privacy claim.
- **The cloud giants (OpenAI / Gemini)** have the biggest models — and **structurally cannot**
  hold your whole private life. People will never upload medical cards, passports, and family
  texts to a cloud, and even if a few would, trust caps it forever.

**The gap nobody is filling:** a *phone-first, zero-effort, provably-private* brain for **normal
people** — not model hobbyists, not note-takers — where **the more it knows about you, the safer
it is**, because it physically cannot leave your control. That gap is the wedge. Everything below
is how we drive into it.

### What "viral like OpenClaw" actually requires
OpenClaw did not win on code quality. It won on two things, and our roadmap is engineered to
manufacture both:
1. **One sub-15-second "holy shit" moment** that survives compression into a tweet/TikTok.
2. **A movement to belong to** — ownership against rent-seeking incumbents.

---

## 2. The Three Ideas (in full)

The three ideas are not three products. They are **three faces of one brain**: how it *thinks*
(compute), what it *knows about you* (memory), and how it is *shared and owned* (the movement).

### Idea A — "Own Your Intelligence" (the movement + the open standard + the heirloom)

**The thesis.** Right now you *rent* intelligence from ~5 trillion-dollar companies, forever, and
they see everything you ask. EkamCore's reason to exist is to **take AI back** — to make
intelligence something you *own*, that runs on hardware you already paid for, that no corporation
can read, rent, throttle, or switch off.

Three concrete expressions, in increasing ambition:

1. **The open protocol, not just an app.** The *actual* OpenClaw-scale move is to publish an
   **open standard for personal AI** — how a phone (or any client) pairs with, talks to, and
   recalls from a personal vault/brain — and make EkamCore the polished reference implementation.
   Apps come and go; a standard with a movement behind it changes the face of the earth. This is
   how we become "the TCP/IP of owning your own AI" instead of "an app that will be cloned."
2. **You own the weights and the data, provably.** Open-source the agent so anyone can audit that
   nothing leaves your control. Open-source is not marketing decoration here — it is the
   **precondition** for everything in Idea B (see §3). "Trust me bro" cannot clear the bar of
   "give me your whole private life." *Verifiable* can.
3. **The heirloom: a model of you that you own forever.** Over years, the brain learns *you* (a
   local adapter, fine-tuned on your own life, on your own machine). It becomes a model *of you*
   that is legally and physically yours — portable, inheritable. When you are gone, your family
   can still ask it *"how did Dad make his coffee?"* Cloud AI can never give you a continuity of
   self that you own; theirs can be read, rented, and shut off. Yours cannot. **The first AI that
   is an heirloom, not a subscription.** (Far-horizon; designed-for, built last.)

**Why uncopyable:** the cloud cannot sell you something whose entire value is *that they can't see
it*. LM Studio won't build a movement around *your life* — their product is the model.

### Idea B — "The Memory That Can't Betray You" (the aha, the launch hero)

**The thesis.** The reason "second brain" never went mainstream is two unsolved problems, and
EkamCore's architecture is the only one that can solve **both at once**:

- **Capture is too much work** (Obsidian: write markdown) — *or* —
- **Capture is too creepy** (Rewind: record your screen).

EkamCore solves effort *and* trust simultaneously:

1. **Effortless capture.** "Send to my brain" from any app's share sheet. Opt-in camera-roll
   ingest. A 5-second voice memo on the drive home. A quick photo of a card/form/letter. **No
   markdown, no folders, no discipline.** The brain does the organizing.
2. **Provable privacy.** Because the vault is *your device / your house*, capture can finally be
   **total without being a liability**. The more it knows, the more it *can't* betray you —
   because it physically cannot leave.
3. **Plain-language recall — the aha-in-life.** The moment a stranger records and posts:

   > You are standing at a pharmacy counter. You ask your phone: *"What's my dad's insurance
   > member ID?"* — and it answers instantly, from a photo of his card you snapped a year ago and
   > forgot. That photo lives only on your device / the computer at home. No cloud ever saw it.
   > You never organized a thing. **It just knew.**

   That clip pattern-breaks three "known truths" at once: *good AI needs the cloud* (✅ broken),
   *private = weak* (✅ broken), *it can't really know my life* (✅ broken). And it is emotionally
   nuclear because it is *your life, perfectly recalled, perfectly private.*

4. **The Glass House — security as spectacle.** Since open-source means people *will* attack it,
   don't hide the security — **weaponize it.** A live, in-app **privacy meter** showing
   bytes-to-cloud pinned at a flat, hard **zero**. Public bug bounty. Public audits. *"Watch the
   network monitor. Flat line. That's the whole product."* We turn the thing competitors hide
   into the thing people screenshot.

**Why uncopyable:** OpenAI/Gemini *can't* (they'd have to see your life); LM Studio/Obsidian
*won't* (wrong product, wrong user); Rewind/Personal.ai *can't be trusted* (closed, cloud-ish).

### Idea C — "The People's Cloud" (intelligence as a gift economy)

**The thesis.** Invert the cloud at the *social* layer. Every EkamCore home node, when idle, can
lend compute to **people you trust** — not strangers, not a marketplace — so a circle of family
and friends pools the GPUs they already own instead of renting from Amazon.

The non-obvious mechanics that make this earth-changing rather than "distributed Ollama":

- **The trust circle = reused pairing crypto.** You only lend to people you have physically paired
  with (the same identity/QR/Noise spine as the bridge). This sidesteps ~90% of the abuse and
  safety problems that kill public compute networks.
- **Blind compute (the killer property).** When Grandma's phone runs on *your* GPU, **you cannot
  read what she asked.** Her context and memory stay hers; your machine is a blindfolded engine
  that only emits tokens. This is what makes a *compute* commons acceptable where every prior one
  failed — and it is only possible on the same E2E-crypto spine.
- **Owner always wins.** Lending is idle-only and policy-controlled (who, when, how much). Your
  game launches → it instantly yields.
- **Reciprocity, not money.** A simple karma ledger ("you lent 10h, you can borrow 10h") keeps it
  a **gift economy among people who love each other** — the soul of Idea A expressed as
  infrastructure, not a market.
- **Built-in virality.** Every circle invite recruits a user. The viral coefficient is the highest
  of the three ideas.

**The hard wall (why it comes last):** it requires remote / NAT-traversal (WebRTC + STUN/TURN) —
exactly what the bridge spec deferred — plus careful sandboxing to *guarantee* blind compute. So
it structurally follows the bridge. That is fine: it is worth waiting for, and waiting makes it
safe.

**One line:** *intelligence as a gift economy among people who trust each other.*

### How the three unify
| Face | Idea | What it is |
|------|------|-----------|
| **What it knows** | B — Memory | Your life, captured effortlessly, recalled instantly, provably private. **The aha.** |
| **How it thinks** | A (compute) + bridge | Your home computer as the bigger brain; you own the weights. |
| **How it's shared & owned** | A (movement/standard) + C (mesh) | Open standard, gift-economy compute, an AI you own forever. |

---

## 3. Why open-source and the aha are the *same* strategy (the lock)

This is the load-bearing insight of the whole product:

- The aha (Idea B) requires people to feed the brain their **entire private life**.
- "Trust me bro" (LM Studio, Rewind) **cannot** clear that bar.
- *"The agent is open-source — audit it, watch the network, nothing leaves your control"* **can.**
- Therefore open-source is the **precondition** for the aha, the aha is the engine of virality,
  and virality feeds the movement (Idea A). **They are one strategy, not three.**

This is also why the **Glass House** (visible, provable "zero bytes left") is not a nice-to-have —
it is the marketing *and* the trust mechanism *and* the answer to "open-source = attack target":
we make the security legible enough that the public can verify it themselves.

---

## 4. The differentiation matrix (keep us honest)

| | Cloud (OpenAI/Gemini) | LM Studio / Ollama | Obsidian | Rewind / Personal.ai | **EkamCore** |
|---|---|---|---|---|---|
| Runs without the cloud | ✗ | ✓ | ✓ (notes) | partial | **✓** |
| Knows your *whole life* | ✗ (won't be trusted) | ✗ (not its job) | only what you type | ✓ but closed/creepy | **✓ effortless + private** |
| Effortless capture (no discipline) | n/a | ✗ | ✗ (write markdown) | ✓ (but invasive) | **✓** |
| Provable privacy (auditable) | ✗ | partial | ✓ (files) | ✗ | **✓ open + Glass House** |
| Bigger brain on your own hardware | ✗ | ✓ (hobbyist) | ✗ | ✗ | **✓ (bridge, seamless)** |
| Pool compute with people you trust | ✗ | ✗ | ✗ | ✗ | **✓ (People's Cloud)** |
| An AI you *own forever* | ✗ | ✗ | your notes only | ✗ | **✓ (heirloom)** |
| A movement / open standard | ✗ | ✗ | community | ✗ | **✓ (the wedge)** |

If a row ever stops being true, we have drifted into being "a nicer PocketPal." This table is the
guardrail.

---

## 5. Security model (because open-source = a target — and that's the point)

The user is correct: open-sourcing invites attack. Our posture turns that into strength.

- **Reuse audited crypto, never home-roll.** Noise Protocol Framework (WireGuard/Signal family)
  for the channel; OS secure hardware (iOS Keychain / Android Keystore) for keys — *not* plain
  AsyncStorage.
- **Out-of-band trust.** Pairing identity travels inside a physically-scanned QR (one-time,
  short-TTL code), so LAN/MITM impersonation fails. Physical confirmation on the desktop defends
  against remote photographs of the QR.
- **Blind compute guarantee (Idea C).** A lender's machine must be provably unable to read a
  borrower's prompts/context — sandboxed inference, no prompt logging, E2E-encrypted payloads.
- **The Glass House.** Make "nothing left your control" *visible and testable* in the app. Publish
  a threat model. Run a public bug bounty. Invite third-party audits. Let the security be a thing
  people *verify*, not a thing they're asked to believe.
- **Default-deny capture.** Every capture source (camera roll, share sheet, voice) is explicit
  opt-in, per-source, revocable. The brain never ingests what you didn't hand it.

---

## 6. The aha-moments we are manufacturing (the launch clips)

Each phase exists to produce **one** shareable moment. If a feature doesn't serve that phase's
clip, it waits.

- **Phase 1 clip:** the pharmacy moment. *"I never organized anything. It just knew. And nothing
  ever left my phone — watch the meter."*
- **Phase 2 clip:** *"I plugged in my old laptop and my phone's brain got 19× smarter — still $0,
  still private. Setup was one QR scan."*
- **Phase 3 clip:** *"Grandma's iPhone is running on my gaming PC across town — and I can't even
  see what she asked. We don't pay anyone."*

---

## 7. The Launch Roadmap (the part that makes us actually ship)

**Principle:** *a movement with no launch milestones builds forever and ships nothing.* Every
release below has a hard **Definition of Done** and an explicit **NOT in this release**. We do not
start the next phase until the current one's DoD is met and it is *in users' hands*. Scope creep
dies at these boundaries.

**The key re-sequencing decision:** the existing bridge spec builds the desktop *first*. We
**reverse that.** The pharmacy aha works **entirely on the phone** — the phone took the photo, the
phone can index it (embeddings + vector search are cheap and excellent on-device), the phone can
recall it. You only need the home brain for *deeper reasoning*, not for the recall miracle. So we
ship the viral moment on the phone alone — **no Rust, no Tauri, no pairing, no NAT** — get the clip
spreading in weeks, and *then* the bridge becomes the irresistible Pro upgrade. We go viral before
we ever have to learn Rust.

### Phase 0 — Foundation _(shipping today)_
On-device LLM chat, vision model catalog, Hugging Face browse, segmented Text/Image models.
**DoD:** already met. **Role:** the seed the memory grows on.

### Phase 1 — **"The Memory"** _(THE LAUNCH — phone-only)_
The viral hero. Everything runs on a single phone.
- **Capture:** share-sheet "Send to my brain," opt-in camera-roll ingest, voice memo, manual
  quick-add. Per-source, revocable consent.
- **Ingest:** on-device OCR / vision-extraction (reuse the existing vision models) + text
  extraction → embeddings → a **local vector store**. Fix the known storage debts en route
  (turn-level history window, image cleanup on delete, move off the O(n) AsyncStorage index).
- **Recall:** plain-language Q&A over your captured life; the answer **plus the source artifact**
  (the photo it read it from) is shown — trust through provenance.
- **Glass House:** a visible "0 bytes left this device" privacy indicator; published threat model.
- **DoD:** the pharmacy demo works reliably end-to-end on a real phone; privacy is demonstrably
  zero-egress; the recall clip is recordable; app is shippable (and the repo open-sourced).
- **NOT in this release:** ❌ desktop app ❌ pairing/QR ❌ any networking ❌ accounts ❌ the bridge
  ❌ multi-device ❌ the People's Cloud ❌ the heirloom model. *If it needs a second device, it's
  not Phase 1.*

### Phase 1.x — **Spread & harden** _(no new surface area)_
Reliability, recall-ranking quality, more capture sources, Android parity, **publish the open
protocol v0 spec** (plant the movement flag), launch the bug bounty, lean into the clip and the
"Own your intelligence" narrative.
- **DoD:** crash-free recall at scale; protocol spec public; the clip is actually circulating.
- **NOT in this release:** ❌ anything requiring the desktop.

### Phase 2 — **"The Home Brain"** _(the bridge — the existing A+B spec, now Phase 2)_
Pair the home computer; the brain gets bigger and smarter.
- Tauri tray agent, Noise-encrypted LAN pairing (QR), bundled llama.cpp, "My Computer" source in
  chat; the memory vault can live on / sync to the home machine (bigger storage), reasoning jumps
  to a far larger model (~19× throughput, 8k–128k context).
- Reuses the full 2026-06-12 bridge spec — **unchanged in design, only re-sequenced to here.**
- **DoD:** one-QR-scan pairing on real devices; "My Computer" streams answers; graceful on-device
  fallback out of range; revoke works.
- **NOT in this release:** ❌ remote/out-of-home access ❌ the mesh ❌ the heirloom ❌ lending to
  others. LAN-only, single user.

### Phase 2.x — **Remote-ready & the self that learns you**
Swap LAN TCP for WebRTC data channel (remote access groundwork — STUN/TURN); begin the **local
adapter that learns you** (heirloom v0, on-device/home-only).
- **DoD:** secure out-of-home connect to your *own* home brain; an opt-in personalization adapter
  that measurably improves recall/answers.

### Phase 3 — **"The People's Cloud"** _(the movement, fully expressed)_
Trust-circle compute mesh with **blind compute**, the reciprocity ledger, and the inheritable
heirloom model.
- **DoD:** a paired friend/family device runs inference on your idle machine; you provably cannot
  read their prompts; idle-only lending with owner preemption; karma ledger balances.
- **NOT in this release:** ❌ public/stranger compute markets ❌ money. Trust circles only.

### Roadmap at a glance
| Phase | Name | Needs new high-risk tech? | The clip | Status |
|---|---|---|---|---|
| 0 | Foundation | — | — | shipping |
| **1** | **The Memory** | **No** (phone-only) | pharmacy aha | **next — the launch** |
| 1.x | Spread & harden | No | clip circulating | after 1 |
| 2 | The Home Brain | Yes (Rust/Tauri/Noise) | "19× smarter, one scan" | bridge spec, re-sequenced |
| 2.x | Remote + self-model | Yes (WebRTC) | — | after 2 |
| 3 | The People's Cloud | Yes (mesh/blind compute) | "Grandma on my GPU" | the destination |

---

## 8. What we are explicitly NOT doing (YAGNI guardrails)

- **No cloud accounts, ever**, for the core experience. (A movement about owning your intelligence
  cannot have a login wall to a server we run.)
- **No stranger/public compute marketplace.** Trust circles only — that's what keeps it safe and
  on-message.
- **No money in the loop** for compute. Reciprocity (karma), not payments.
- **No screen recording / ambient surveillance.** Capture is always an explicit, per-source,
  user-initiated act. We are the *anti*-Rewind.
- **No home-rolled crypto.** Audited libraries only.
- **No bridge work before Phase 1 ships.** The single most important guardrail against
  never-launching.

---

## 9. Open questions to resolve in each phase's own spec

- **Phase 1:** which on-device embedding model; vector-store choice (e.g. SQLite + vector ext vs.
  a small RN-friendly ANN store); recall-ranking approach; OCR quality bar on the existing vision
  models; the exact Glass House measurement (how we *prove* zero egress in-app).
- **Phase 2:** all open items already in the 2026-06-12 bridge spec (Noise pattern, wire protocol,
  mDNS naming, bundled-model first-run, per-OS Tauri signing).
- **Phase 3:** the blind-compute sandbox guarantee; reciprocity-ledger design; mesh discovery;
  heirloom adapter training pipeline on-device/home.
- **Cross-cutting:** the open-protocol v0 surface; naming/positioning of the public movement;
  governance of an open standard.

---

## 10. Immediate next step

Brainstorm **Phase 1 ("The Memory")** to its own detailed design spec, then an implementation
plan. Phase 1 is the launch; nothing else starts until it is in users' hands. The bridge spec
already exists and waits, intact, as Phase 2.

# EkamCore — Product Roadmap & Vision

_Last updated: 2026-06-11_

EkamCore is a bare React Native app that runs LLMs **fully on-device** via `llama.rn`.
This document records the multi-phase product vision. **Only Phase 1 is being built now**;
Phases 2 and 3 are captured here so the foundation is built with them in mind, but are
**not yet started** and each will get its own spec → plan → implementation cycle.

---

## Competitive landscape (scan: 2026-06-11)

**Fully offline on-device LLM chat is a mature, crowded category** — it is table stakes, not
a differentiator:

- **PocketPal AI** (llama.cpp, iOS+Android, 500K+ downloads) — closest architectural peer.
- **Private LLM, MLC Chat, Ollama iOS, LLM Hub, Enclave AI, Jan, onLM, GPT4All, OnDevice LLM.**

Persistent chat history (our Phase 1) already ships in every serious app (Enclave, Jan, onLM).
On-device "memory"/personalization (our Phase 2) partly exists (OnDevice LLM "learns facts about
you"; Jan remembers preferences; Enclave custom personalities) — but only as **shallow fact memory**.

The phone → personal-compute bridge (our Phase 3) exists today only as **prosumer/technical** tools
(LM Studio **LM Link**, **Tailscale + Ollama**, **LMSA**, **Exo** clustering, **AnythingLLM/Open WebUI**
RAG) — **never assembled into one zero-config, phone-first consumer product that can reach any local
resource the user grants access to**.

**Strategic read:** the underlying tech for all three phases is proven and open. EkamCore's moat is
**packaging and execution** — behavioral (not just factual) memory that is transparent and editable,
and a personal-compute bridge that is invisible to non-technical users, can query **any local resource
the user explicitly grants access to** (files, photos, notes, mail, calendars, code, databases, and
more), and **switches models seamlessly inside one chat window**.

Sources: [PocketPal AI](https://github.com/a-ghorbani/pocketpal-ai) ·
[OnDevice LLM](https://apps.apple.com/us/app/ondevice-llm-offline-ai-chat/id6761696880) ·
[Enclave AI](https://enclaveai.app/) ·
[Mem0](https://github.com/mem0ai/mem0) ·
[LM Link](https://lmstudio.ai/link) ·
[Tailscale + Ollama](https://www.kdnuggets.com/accessing-local-llms-remotely-using-tailscale-a-step-by-step-guide) ·
[Exo](https://github.com/exo-explore/exo) ·
[AnythingLLM / Open WebUI RAG](https://www.tooljunction.io/blog/self-hosted-ai-stack-2026)

---

## Phase 1 — Persistent chat history _(IN PROGRESS)_

**The must-have foundation.** Today `messages` lives only in React state and is wiped on model
load — history vanishes on restart. Phase 1 makes chat history persistent and browsable on both
platforms.

- Multiple conversations (thread list), not a single rolling transcript.
- Slide-in history panel from the Chat header; tap to reopen, swipe to delete, "+" for new.
- AsyncStorage: a lightweight index + per-conversation message blobs.
- Removes the model-switch wipe, setting up Phase 3's in-chat model switching.

→ Full design: `docs/superpowers/specs/2026-06-11-persistent-chat-history-design.md`

## Phase 2 — Behavioral + transparent on-device memory _(NOT STARTED)_

Differentiator vs the fact-only crowd. Built on top of Phase 1's history.

- **Two memory layers:** *facts* about you (table stakes) **and** *style/behavior* — preferred
  answer length, format (bullets vs prose), tone, recurring topics, expertise level — derived
  periodically from your own chat history.
- Profile is **injected into the system prompt / context** so the model behaves adapted to you
  (prompt-based personalization — NOT on-device weight fine-tuning, which is not feasible via
  `llama.rn`).
- **Transparent & editable:** a screen showing exactly what the model has learned about you,
  fully editable and deletable, with a **one-tap off switch**. Local-only, never leaves device.

## Phase 3 — "Your AI, your hardware" (personal-compute bridge) _(NOT STARTED)_

The biggest differentiator. Phone stays a thin, private client; heavy models run on hardware you own.

- **Zero-config, secure discovery** of your own home compute (Mac Mini / NAS / laptop), hiding the
  Tailscale-mesh / Exo-cluster plumbing entirely from non-technical users.
- **Seamless model switching inside one chat window** — choose "fast on-device" or "big at home"
  per message. This specific UX is essentially unclaimed.
- **Query any local resource the user explicitly grants access to** — not limited to a fixed set.
  Files and photos are obvious first connectors, but the model is **generalized**: notes, mail,
  calendars, messages, code repos, databases, app data, or any other source the user opts in to.
  Access is **per-resource, user-granted, and revocable**; nothing is reachable unless the user
  turns it on.
- Privacy-first: data stays on devices you own; nothing goes to a third-party cloud.

---

## Build order

Phase 1 (persistent history) → Phase 2 (behavioral memory) → Phase 3 (personal-compute bridge).
Each phase is shipped and verified before the next is designed. P1 is built so its persistence
layer and model handling do not block P2/P3.

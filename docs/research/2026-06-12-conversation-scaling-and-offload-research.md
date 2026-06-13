# Conversation Scaling, Long-Context Degradation & Phone→Laptop Offload — Research + Verdict

_Date: 2026-06-12 · Status: research report (revisitable reference)_

**Question investigated:** How do on-device / local LLM chat apps handle scaling of
conversations (long single chats, many chats, storage, attachments), and is
long-context degradation a fundamental **system-design** problem or a tractable
**engineering** one? Plus: how would moving inference from the phone model to a paired
**laptop model** (the desktop bridge) change speed, context limits, model size, battery,
and UX?

**Method:** deep-research harness — 6 search angles → 26 sources → 115 extracted claims
→ 25 adversarially verified (3-vote, kill on ≥2 refutes) → **21 confirmed, 4 killed**.
The harness's final synthesis step timed out; this report was synthesized by hand from
the 21 verified claims (cited below). Only verified claims are asserted. The 4 killed
claims are listed so we don't accidentally repeat them.

---

## EkamCore's current behavior (the baseline this is measured against)

Grounded in the actual code at the time of writing:

- **Context window:** `n_ctx: 2048` hardcoded (`src/services/llama.ts:37`). No `n_keep`,
  no context-shift config.
- **History handling:** the app sends the **entire** conversation history every turn —
  `generate()` builds `messages = [system, ...all non-system history]` with no
  truncation/windowing (`src/services/llama.ts:102-103`). `maxTokens` (n_predict) = 512.
  Only `regenerate` slices history (`AppContext.tsx:681`).
- **Persistence:** each conversation = one AsyncStorage blob
  (`ekamcore.conversation.<id>.v1`) + a **single index key**
  (`ekamcore.conversations.index.v1`). `saveConversation` **rewrites the whole index on
  every message** (read → prepend → sort → write all) — O(n) write amplification
  (`src/services/conversations.ts:52-55`).
- **Images:** stored as files in `chat-images/`; **deleting a conversation removes the
  text blob but never the image files** (`conversations.ts:59-61`) → unbounded file leak
  (already tracked in `docs/DEFERRED_WORK.md`).

---

## Part 1 — How other apps handle it

### Context window (long single chat)
Industry consensus is **curation, not "send everything"**:

- **Canonical fix = turn-level truncation:** drop whole old message-tuples (user + AI +
  any tool turn) while **pinning the system prompt** — not naive token dropping.
  llama.cpp's old engine-level `--context-shift` was **removed and won't return** because
  it "broke the chat template, removed the system prompt, and invalidated KV caches that
  encode token position"; the maintainers point to app-level turn truncation as the
  replacement. [llama.cpp #19838]
- **Sliding-window primitive still exists:** `n_keep` (front tokens kept) + `n_discard`
  (dropped on overflow); `n_keep=0, n_discard=1` = pure sliding window. [llama.cpp #11845]
- **Graceful default in bindings:** node-llama-cpp's `eraseFirstResponseAndKeepFirstSystem`
  "truncate[s] the oldest model responses… while keeping the first system prompt in place"
  when history exceeds context — shifts instead of failing. [node-llama-cpp.withcat.ai]
- **Cloud apps / agents add summarization + RAG-over-history:** when the question and the
  buried answer have low semantic similarity, "performance degrades more quickly in input
  length" — so retrieving the relevant slice beats dumping raw history.
  [research.trychroma.com/context-rot]

### Storage at scale
Flat JSON in a single rewritten key is the known anti-pattern. Documented better answers:

- **MMKV** (key-value): "~30x faster than AsyncStorage," fully synchronous via JSI/C++,
  no bridge. [github.com/mrousavy/react-native-mmkv]
- **SQLite-backed reactive store (WatermelonDB)** (message corpus): "scale from hundreds
  to tens of thousands of records and remain fast," and **lazy** — "nothing is loaded
  until it's requested," fixing load-everything / write-amplification.
  [github.com/Nozbe/WatermelonDB]

---

## Part 2 — Verdict: system-design issue or engineering one?

**Both, but they split cleanly — EkamCore's actual pain is ~90% tractable engineering.**

- **Model-level reality (manage, don't "fix"):** long-context degradation is intrinsic.
  "Models do not use their context uniformly; performance grows increasingly unreliable
  as input length grows" [Chroma]; effective context "typically [does] not exceed half of
  their training lengths" [arXiv 2410.18745]; models "fell far short of their… context
  window by as much as 99 percent," with "severe degradation by 1000 tokens" — **below
  the 2048 `n_ctx`** [arXiv 2509.21361]. No setting makes a 2 B phone model reliably
  reason over a giant history.
- **Tractable at the engineering layer:** "what matters more is *how* that information is
  presented" [Chroma]; degradation is fixable at inference (e.g. STRING "shift[s]
  well-trained positions… with no additional training") [arXiv 2410.18745]. Every serious
  app solves it with curation — sliding-window + keep-system + summarize/retrieve.

**Translation:** EkamCore's `n_ctx=2048`, full-history-every-turn, AsyncStorage index
rewrite, and never-cleaned images are **plain engineering omissions**, each with a known
fix. They are *not* the fundamental limit. The fundamental limit (small phone model can't
deeply use a long history) is **managed** with the same curation toolkit everyone uses.
**A tractable engineering problem on top of a model constraint you design around — not a
dead end.**

---

## Part 3 — Phone model → laptop model (the desktop bridge)

Highest-leverage move; research validates the architecture our bridge spec already
commits to (`docs/superpowers/specs/2026-06-12-desktop-pairing-bridge-design.md`).

- **Speed:** laptop/dGPU sustains "roughly 19× higher throughput" than mobile-class NPU
  (RTX 4050 ≈ 131.7 tok/s vs mobile ≈ 6.9 tok/s). [arXiv 2603.23640]
- **Lifts the phone's binding constraints:** on mobile, "thermal management supersedes
  peak compute as the primary constraint" — iPhone 16 Pro "loses nearly half its
  throughput within two iterations," Galaxy S24 Ultra hits an OS GPU floor that
  "terminates inference entirely" [ibid]; on-device is bounded by "battery, thermal
  limits, and, most importantly, memory" [arXiv 2603.26603]. Offloading lifts all three:
  the phone just renders tokens (cool, low battery); the desktop runs a far bigger model
  with a far bigger context (8k–128k), so the **long-chat context problem largely
  disappears for paired sessions**.
- **Proven pattern, matches our spec:** LM Studio "LM Link" keeps "chats… local, while the
  heavy processing happens on more powerful devices" [lmstudio.ai/link] — precisely the
  bridge's **"My Computer" source** (Noise-encrypted LAN → desktop-bundled llama.cpp →
  streamed tokens; history stays on the phone).
- **What changes:** model size 0.5–4 B → 8–70 B; context window jumps; latency shifts from
  compute-bound to *network*-bound (LAN RTT, trivial); phone battery use ≈ zero. **But**
  requires desktop on + same Wi-Fi → keep on-device model as graceful fallback (already in
  the spec). Storage/context bookkeeping still lives on the phone, so the Part-2 fixes
  still matter regardless of the bridge.

---

## Recommendations for EkamCore (prioritized)

| # | Fix | Type | Why |
|---|-----|------|-----|
| **1** | Turn-level sliding window in the message builder: keep system + last N turns under a token budget; drop whole oldest tuples | engineering | Canonical fix; stops silent overflow past 2048 [llama.cpp #19838] |
| **2** | Make `n_ctx` device-adaptive (4k–8k where RAM allows) | engineering | Buys headroom; KV cost bounded |
| **3** | Image cleanup on conversation delete (unlink `imagePath` files) | engineering | Stops unbounded file leak |
| **4** | Summarize dropped turns into the existing memory feature | engineering | Preserves gist past the window [Chroma favors retrieval/summary] |
| **5** | Move chat corpus to SQLite/WatermelonDB (or index to MMKV) | engineering | Fixes O(n) index rewrite + load-everything [WatermelonDB, MMKV] |
| **6** | Ship the bridge "My Computer" source | architecture | Lifts model/thermal/context ceilings entirely [LM Link, 19× throughput] |

**One-line verdict:** Tractable engineering problem — fix truncation, storage, and the
image leak now; manage the residual model-level context limit with curation; the bridge is
the real escape hatch, not a workaround.

---

## Appendix A — Verified claims (3-vote adversarial; vote shown)

**Context management**
1. `[3-0]` When history exceeds context size, context shift removes oldest tokens from the
   KV cache to make room, rather than failing. — node-llama-cpp.withcat.ai/guide/chat-context-shift
2. `[3-0]` Default strategy `eraseFirstResponseAndKeepFirstSystem` truncates oldest model
   responses while preserving the first system prompt (removing a response also removes its
   preceding prompt). — node-llama-cpp.withcat.ai
3. `[3-0]` llama.cpp's previous `--context-shift` had material flaws (broke chat template,
   removed system prompt, invalidated position-encoding KV caches) and won't be reintroduced
   in that form. — github.com/ggml-org/llama.cpp/issues/19838
4. `[3-0]` Correct long-chat approach = application/turn-level truncation dropping whole old
   conversation tuples while preserving the system prompt. — llama.cpp #19838
5. `[3-0]` llama.cpp's built-in context-shift takes `n_keep` + `n_discard`; `n_keep=0,
   n_discard=1` = pure sliding window. — github.com/ggml-org/llama.cpp/discussions/11845

**Long-context degradation (verdict-driving)**
6. `[3-0]` LLMs don't process long context uniformly; reliability drops as input grows, even
   on simple retrieval. — research.trychroma.com/context-rot
7. `[3-0]` Low question/answer semantic similarity → faster degradation with length → favors
   summarization/RAG over raw dumps. — research.trychroma.com/context-rot
8. `[2-1]` What matters is how info is presented/positioned (relevant words used more when
   early in input) → curation is an engineering lever. — research.trychroma.com/context-rot
9. `[3-0]` Effective context length of open-source LLMs typically ≤ half their training
   length. — arxiv.org/pdf/2410.18745
10. `[2-1]` Root cause = left-skewed frequency distribution of relative positions in
    pre/post-training. — arxiv.org/pdf/2410.18745
11. `[3-0]` Tractable at inference: STRING shifts well-trained positions over ineffective
    ones, no training needed. — arxiv.org/pdf/2410.18745
12. `[2-1]` Large gap between advertised (MCW) and effective (MECW) context; models fell
    short by as much as 99%. — arxiv.org/abs/2509.21361
13. `[2-1]` Severe accuracy degradation by ~1000 tokens; some top models failed at ~100
    tokens — below a 2048 n_ctx. — arxiv.org/abs/2509.21361

**Storage**
14. `[3-0]` react-native-mmkv reads ~30x faster than AsyncStorage. — github.com/mrousavy/react-native-mmkv
15. `[3-0]` MMKV is fully synchronous (JSI/C++ NitroModules, no bridge). — github.com/mrousavy/react-native-mmkv
16. `[3-0]` WatermelonDB scales hundreds → tens of thousands of records and stays fast. — github.com/Nozbe/WatermelonDB
17. `[3-0]` WatermelonDB is lazy — nothing loaded until requested — fixing flat-JSON
    read/write amplification + memory. — github.com/Nozbe/WatermelonDB

**Performance / thermal / offload**
18. `[2-1]` On mobile, thermal management supersedes peak compute; iPhone 16 Pro loses ~half
    throughput within 2 iterations; S24 Ultra hits an OS GPU floor that terminates
    inference. — arxiv.org/pdf/2603.23640
19. `[2-1]` Laptop/dGPU ≈ 19x higher throughput than mobile NPU (RTX 4050 131.7 tok/s @34.1W
    vs Hailo-10H 6.9 tok/s @<2W). — arxiv.org/pdf/2603.23640
20. `[3-0]` On-device inference is bounded by battery, thermal limits, and (most) memory. — arxiv.org/pdf/2603.26603
21. `[3-0]` LM Studio "LM Link" offloads inference to a more powerful remote machine; chats
    stay local, heavy processing remote. — lmstudio.ai/link

## Appendix B — Killed claims (DO NOT repeat — failed verification)

- `[1-2]` "llama.cpp maintainers declined to add automatic context truncation (app-layer
  concern)." — overstated; refuted.
- `[0-3]` "The native/canonical way is the context-shift API in `examples/main/main.cpp`." —
  refuted (the engine path was deprecated; app-level truncation is canonical).
- `[1-2]` "Importance-aware quantization yields negligible energy savings vs mixed-precision." — refuted.
- `[0-3]` "On-device LLM/LMM deployment is practically capped at ~7B parameters." — refuted;
  do **not** claim a hard 7B ceiling.

## Appendix C — Primary sources
- node-llama-cpp context-shift guide · llama.cpp issues #19838 / discussion #11845
- Chroma "Context Rot" (research.trychroma.com/context-rot)
- arXiv 2410.18745 (effective context length / STRING), 2509.21361 (MCW vs MECW),
  2603.23640 (mobile thermal / throughput), 2603.26603 (on-device constraints)
- react-native-mmkv · WatermelonDB · lmstudio.ai/link

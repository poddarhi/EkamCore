# EkamCore — End-to-End UX Spec (for UI/UX enhancement)

> **Purpose:** A complete, accurate description of EkamCore's current screens, flows,
> design system, and UX so a design model (Fable) can propose concrete UI/UX
> improvements. Each screen lists **Current** behavior and **Opportunities**.
> The "Asks for Fable" section at the end states constraints and deliverables.

---

## 1. What EkamCore is

A **bare React Native (no Expo)** mobile app that runs LLMs **fully on-device** via
`llama.rn` (llama.cpp). You download a small GGUF model once, then chat **offline** —
no accounts, no servers, nothing leaves the phone. It also includes one-shot **AI
Tools**, an **on-device personalization** layer, and a bridge to **your own remote
compute** (Ollama / LM Studio).

**Brand feel today:** "Nebula" — a violet→indigo identity with an electric cyan accent;
geometric display type (Space Grotesk) over highly legible body type (Inter); an animated
"aurora" glow behind chat while generating. Privacy-first, calm, modern.

**Core principles to preserve:** offline-first, private, fast/light, approachable for
non-technical users (plain language, not developer jargon).

---

## 2. Platform & technical constraints (important for design)

- **React Native 0.85**, iOS (Metal GPU) + Android (CPU). UI is hand-built RN components
  (no UI kit). Icons are custom Feather-style strokes via `react-native-svg`.
- **No web stack.** Designs must be expressible with RN primitives (View/Text/Pressable/
  FlatList/Modal/Animated/Switch/TextInput) and the existing theme tokens.
- Prefer **no heavy new dependencies**. Animations use the built-in `Animated` API.
- Must keep working **offline** (catalog browsing/remote are online; chat/tools are local).
- Two themes exist (**light + dark**) and must both be honored by any new UI.
- Custom fonts are per-weight PostScript faces (see §4).

---

## 3. Information architecture & navigation

**Custom shell** (`App.tsx`) — not React Navigation. A persistent **bottom tab bar** with
an animated pill indicator and 4 tabs:

| Tab | Icon | Screen |
|-----|------|--------|
| Chat | chat bubble | ChatScreen |
| AI Tools | grid | ToolsListScreen → ToolRunnerScreen |
| Models | cube | ModelsScreen |
| Settings | sliders | SettingsScreen |

- **A top header** (title + subtitle) is rendered by the shell; the **Chat** tab adds a
  **history icon** at the top-left; the **AI Tools runner** adds a back arrow.
- **Default landing tab is `models`** (not Chat).
- **Overlays / bottom sheets** (RN `Modal`): History panel (slide-in from left), Model
  detail sheet, Hugging Face search (full-screen), "+" chat sheet, Personalization sheet,
  Connections sheet, Add-from-URL sheet, Onboarding (full-screen), Splash (full-screen).
- The keyboard hides the tab bar while open (chat/forms get full height).

**App entry sequence:** Splash → (first run) Onboarding → Shell (Models tab).

---

## 4. Design system (current tokens)

**Typography** (`typography.ts`)
- Display = **Space Grotesk** (Medium/SemiBold/Bold) — titles, greetings, brand.
- Body = **Inter** (Regular/Medium/SemiBold/Bold/ExtraBold) — everything else, incl. chat.
- Mono = Menlo (rare).

**Spacing**: xs 4 · sm 8 · md 12 · lg 16 · xl 24 · xxl 32
**Radius**: sm 8 · md 12 · lg 18 · pill 999

**Colors** (`theme.ts`) — light & dark parity:

| Token | Light | Dark |
|-------|-------|------|
| bg | #F7F5FF | #0A0713 |
| surface | #FFFFFF | #140F22 |
| surfaceAlt | #EFEAFB | #1E1733 |
| border | #E3DBF6 | #2C2444 |
| primary | #7C3AED | #8B5CF6 |
| primaryDark | #6D28D9 | #6D28D9 |
| accent | #0EA5E9 | #22D3EE |
| onPrimary | #FFFFFF | #FFFFFF |
| text | #1B1535 | #F2EEFF |
| textDim | #5E5680 | #A99FC6 |
| textFaint | #968CB4 | #6C6090 |
| success | #10B981 | #34D399 |
| warning | #D97706 | #FBBF24 |
| danger | #EF4444 | #FB7185 |
| userBubble / text | #7C3AED / #FFF | #8B5CF6 / #FFF |
| aiBubble | #FFFFFF | #181228 |
| overlay | rgba(27,21,53,.42) | rgba(7,4,16,.72) |
| gradientStart→End | #8B5CF6→#6366F1 | #A78BFA→#6366F1 |
| aurora1/2/3 | #A78BFA / #67E8F9 / #F0ABFC | #7C3AED / #22D3EE / #EC4899 |

**Motion today:** tab pill spring; landing-hero fade/rise + logo pulse; aurora backdrop
animates while generating; sheets slide; typewriter reveal of streamed text.

**System-wide opportunities:** elevation/shadow scale is ad-hoc; no documented
component states (hover/press/disabled/focus) beyond a press-scale on a few buttons; no
defined empty/skeleton/error visual language; spacing rhythm is mostly consistent but
section headers vary (some uppercase tracked, some not).

---

## 5. End-to-end user journeys

1. **First run:** Splash → Onboarding (3 slides) → Models tab. User has no model yet.
2. **Get a model:** Models → pick a fit-recommended model → Download (progress) → Load →
   (auto nothing; user navigates to Chat).
3. **Chat:** Chat tab → type → streamed reply (typewriter) → continue. New chat via "+" or
   header. Revisit past chats via the history panel.
4. **Discover more models:** Models → Browse Hugging Face → search → pick quant → added.
5. **Use a tool:** AI Tools → pick a tool → fill fields + options (or tap an example) →
   Generate → copy result.
6. **Personalize:** Settings → Adapt to me → toggle on, add facts / learn from chat.
7. **Use home compute:** Settings → Your computers → add server; in chat, "+" → pick a
   remote model → replies come from the bigger model.

---

## 6. Screen-by-screen

### 6.1 Splash
**Current:** Brief branded splash (logo) before the shell.
**Opportunities:** Ensure it doesn't double-flash with onboarding; consider a single
cohesive cold-start animation.

### 6.2 Onboarding (3 slides, full-screen)
**Current:** Slides — (1) "AI that runs offline", (2) "Download once, use anywhere", (3)
"Totally private". Skip (top-right), Next button, 3 dots. Shown once.
**Opportunities:** Slides are informational, not interactive; could end with a direct CTA
("Pick your first model") that deep-links to Models with a recommended model pre-highlighted;
illustrations are minimal (logo only); progress dots → could preview the actual value
(a tiny chat demo). Make the privacy promise more visceral (e.g. "airplane-mode works").

### 6.3 Chat (primary surface)
**Current:**
- **No model loaded → empty state**: brain icon, "No model loaded", copy, "Go to Models" CTA.
- **Loaded, no messages → landing hero**: time-based greeting ("Good morning,") + "What's
  on your mind?" with a pulsing brand logo (Gemini-style).
- **Conversation**: `FlatList` of `MessageBubble`s. User bubbles = solid primary, right
  aligned; AI bubbles = surface, left aligned, **Markdown-rendered**, with a "**N tok/s**"
  meta under finished AI replies. Auto-scroll only when parked at bottom. Streamed text is
  revealed by a smooth typewriter independent of model speed.
- **Status bar** (when messages exist): green dot + "{model} • on-device" (or "{model} •
  remote"), and a "New" chip.
- **Input pill**: leading **"+"** (opens the "+" sheet), multiline TextInput
  ("Ask {model}"), and a send button that becomes a **stop** button while generating.
  Footnote: "Runs fully on-device • your chats stay private".
- **Aurora background** animates while generating.
- **Header**: "Chat" + subtitle ("Offline • private" / "Remote • your computer" / "No model
  loaded") + **history icon** (top-left) opening the History panel.
**Opportunities:** No per-message **copy / regenerate / share / edit** actions. No "stop"
affordance discoverability beyond the button swap. No streaming for remote (full reply then
typewriter) — should feel consistent. The greeting/hero is nice but the jump from hero to
list could be smoother. Consider message timestamps, grouped days, "scroll to latest"
button, long-press actions, and a clearer "thinking…" indicator before first token.

### 6.4 History panel (slide-in from left, from Chat header)
**Current:** "Chats" title + close, big **"+ New chat"**, list of conversations (title from
first user message, relative time + message count), tap to open, **pencil (rename)** + **trash
(delete, confirm)** per row. Backdrop tap closes.
**Opportunities:** No search, no pinning, no grouping by date, no multi-select. Rename is a
small icon; could support swipe actions. Active conversation highlighting is subtle. Empty
state is a single line.

### 6.5 "+" chat sheet (bottom sheet, from input "+")
**Current:** Sections — **Attach** (Photo: enabled only if the model supports vision, else
"Current model can't see images"; File: "Coming soon"), **Model for this chat** (list of
downloaded local models with a check on the active one; tap to switch), a **"Your computers
(remote)"** section listing each connected server's models, and a primary **"New chat"**.
**Opportunities:** Mixes attachments (mostly disabled), model switching, and new-chat in one
sheet — hierarchy could be clearer. The model switcher is the real power; could surface the
current model + a one-tap "fast on-device ↔ big at home" toggle. Disabled rows may confuse.

### 6.6 Models (marketplace)
**Current:**
- Intro line + **device banner** ("{device} · {RAM} RAM • estimates tailored to it").
- Models **sorted by device fit** into sections with headers: **Runs great → Runs well →
  May run slowly → Too large**. Each `ModelCard`: name, tagline, meta pills (params · quant ·
  size), a colored **fit badge** (green/amber/red dot + label), a chevron, and actions
  (Download → progress → Load/Unload, trash to remove). "LOADED" badge when active.
- Tap a card body → **Model detail sheet**: name + publisher, a personalized **fit hero**
  ("On your {device} ({RAM}), this should run great"), **"Good for"** chips, description,
  a specs grid (params · quant · size · context · license), Download/Load actions, "View on
  Hugging Face".
- **"Browse Hugging Face"** (primary) → search modal. **"Add from GGUF URL"** (secondary).
- "Your added models" group for custom/HF-added models.
**Opportunities:** Download UX is thin — only bytes + %, **no resume, no pause, and it can
corrupt if backgrounded** (see `docs/BACKLOG.md`); no queue, no background indicator, no
"downloaded ✓" celebration. No **set-as-default model** (backlog). Cards are dense; the
green/amber/red language is good but could be more visual (a capability bar). Detail sheet
specs read like a table; "good for" chips could drive filtering. No filtering/search of the
*featured* list, no compare.

### 6.7 Hugging Face search (full-screen modal)
**Current:** Search field (debounced; empty = trending), result rows (repo name, author,
↓downloads, ♥likes, chevron). Tap → **quant sheet**: a **Recommended** quant (with size +
device fit badge) and "More quantizations" (full list, each with size + fit). Pick → added.
**Opportunities:** Results are text-dense and undifferentiated; no publisher logos/verified
badges, no category/size filters, no "too big for your phone" pre-filter, no recently-added.
Quant names (Q4_K_M, IQ4_XS) are jargon — could be translated to plain "Balanced / Smaller /
Higher quality" with the technical label secondary. No loading skeletons.

### 6.8 AI Tools
**Current:**
- **List**: header + 3 category sections (**Writing, Productivity, Business**); 6 tools —
  Email Generator, Email Reply Suggester, Text Rewriter (Writing); Meeting Notes Summarizer,
  Daily Planner (Productivity); Review Response Writer (Business). Each card: gradient-accent
  icon, title, description, chevron.
- **Runner**: fields (with hints, multiline), option chips (Tone, Length, etc.), **one-tap
  examples** that prefill, a Generate CTA, streamed result with copy. Requires a loaded model
  (else prompts to load).
**Opportunities:** Tools feel separate from chat; could share the result surface/markdown.
No saved/recent outputs, no "send to chat", no favourites. Category chips are static; the
runner form could feel more guided/wizard-like. Result actions limited to copy.

### 6.9 Settings
**Current:** Sections — **Personalization** ("Adapt to me · On/Off" → Personalization sheet),
**Your computers** ("Remote models · N connected" → Connections sheet), **Status** (loaded
model, downloaded count, runs offline), **About** (logo, version, privacy line, credit).
**Opportunities:** **No theme toggle UI** even though light/dark/system are supported in code
— users can't choose. No model storage management (size used, clear cache), no default-model
setting, no data export/delete-all, no font-size/accessibility options. Status is read-only
info; could be more actionable.

### 6.10 Personalization sheet
**Current:** Master **"Adapt to me"** switch (with privacy copy), editable **facts** list
(add/remove), a **preferred style** text field, **"Learn from this chat"** (runs the
on-device model to extract facts/style), and **"Clear everything it knows"**. All local.
**Opportunities:** "Learn" is a manual button with a one-line result note — no preview of
what changed, no diff/confirm. Facts are plain rows; could categorize (about me / how I like
answers). No per-conversation memory scoping. Transparency is good but could be more visual.

### 6.11 Connections sheet (remote compute)
**Current:** Intro, list of connected servers (name, kind, URL, remove), an **Add** form
(type chips Ollama / OpenAI-compatible, name, base URL, optional API key) with a
test-on-add note.
**Opportunities:** Setup is technical (URLs, ports, Tailscale). Could add discovery,
QR/paste-config, connection health indicators, and per-model "good for big tasks" guidance.
No streaming from remote yet (full reply then reveal).

---

## 7. Cross-cutting UX opportunities (priority candidates)

1. **Default tab = Models, not Chat.** For a chat-first product the cold landing arguably
   should be Chat (with a gentle "load a model" nudge), or a smart router.
2. **No theme switcher UI** despite full light/dark support — surface it.
3. **Download experience** is the weakest flow: no resume/pause, can corrupt on backgrounding,
   no clear completion, no storage view (see `docs/BACKLOG.md`).
4. **Message-level actions** (copy/regenerate/share/edit) are missing in chat.
5. **Jargon** in model/quant naming could be translated to plain language with technical
   detail secondary.
6. **Empty / loading / error states** lack a consistent visual language (skeletons, friendly
   errors, retry).
7. **Onboarding → first value** could be tighter (end on "load your first model").
8. **Accessibility**: verify contrast (esp. textFaint), dynamic type, hit targets, VoiceOver
   labels, reduced-motion fallback for aurora/typewriter.
9. **Model switching** (local ↔ your remote) is a differentiator buried in a "+" sheet —
   could be a first-class, delightful control.
10. **Consistency**: unify sheet headers, section labels, button hierarchy, and elevation.

---

## 8. Asks for Fable (the brief)

**Goal:** Propose high-impact UI/UX improvements across the flows above, then provide concrete,
RN-implementable redesigns.

**Please deliver:**
1. A prioritized list of UX problems → recommendations (impact vs effort).
2. Redesigned **key flows**: first-run → first model → first chat; the chat surface;
   the Models marketplace + download; in-chat model switching.
3. Component-level specs (layout, spacing, states, motion) expressed with the **existing
   theme tokens** in §4 — don't introduce a new palette unless you also map it to light+dark.
4. Any new/renamed icons needed (we draw custom Feather-style strokes).
5. Microcopy improvements (we favor plain, warm, privacy-forward language).

**Constraints / do-not-break:**
- Stay **offline-first and private** — never imply data leaves the device for local chat.
- React Native primitives + `Animated` only; avoid heavy deps; honor **both themes**.
- Keep it approachable for non-technical users; keep technical detail secondary.
- Preserve the core IA (4 tabs) unless you make a strong, specific case to change it.

**Reference files in repo:** `docs/ROADMAP.md` (phases/vision), `docs/BACKLOG.md` (known
issues incl. downloads), `src/theme.ts`, `src/typography.ts`, `src/components/*`,
`src/screens/*`.

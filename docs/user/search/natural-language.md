# Natural-Language Search

In addition to keyword search, EkamCore supports natural-language questions.
Instead of searching for fragments, you can ask a full question and receive
an AI-generated answer grounded in your own data.

## How to trigger it

Natural-language mode activates automatically when your query:

- Starts with a **?** character (for example, `?when is Sarah's birthday`), or
- Begins with one of the question words: **who**, **what**, **when**,
  **where**, **why**, or **how**.

Any other query is treated as a standard keyword search.

## How it works

1. Your question is sent to the local Ollama model running on your Mac.
2. The model searches your indexed data (events, reminders, documents, photos,
   contacts) to find relevant sources.
3. It generates a concise answer and attaches the sources it used.

The entire process runs locally. Your question and your data never leave your
machine.

## Answer format

The answer appears at the top of the search results screen in a highlighted
card:

- **Answer text** -- a short, direct response to your question.
- **Source citations** -- numbered references to the specific items (events,
   files, contacts) the answer is based on. Tap a citation to open that item.
- **Confidence level** -- a badge indicating how confident the model is:

| Level | Badge colour | Meaning |
|-------|-------------|---------|
| High | Green | Multiple strong sources support the answer |
| Medium | Yellow | Some supporting evidence but not conclusive |
| Low | Grey | Limited data; treat the answer as a best guess |

Below the answer card, standard keyword search results for the same query are
still shown so you can browse them if the AI answer is insufficient.

## Examples

| Question | What EkamCore does |
|----------|--------------------|
| `?when did I last meet with Alex` | Searches calendar events for meetings with Alex and returns the most recent one |
| `who sent me the quarterly report` | Searches documents and events for context about the quarterly report |
| `where was my dentist appointment` | Finds the dentist event and returns its location field |
| `?what reminders are overdue` | Lists overdue reminders with their due dates |

## Fallback behaviour

If Ollama is not installed or the model is not loaded, natural-language queries
fall back to a standard keyword search. A small banner at the top of results
says "AI answers unavailable -- showing keyword results" with a link to
install or start Ollama.

## Privacy note

Natural-language search uses the same local Ollama instance as other AI
features. No data is sent to any external server. The model runs entirely on
your Apple Silicon GPU.

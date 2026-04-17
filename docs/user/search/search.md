# Search

The Search screen lets you find anything EkamCore has indexed -- events,
reminders, files, photos, and people -- from a single search bar.

## Search bar

Tap the search bar at the top of the screen and start typing. Results appear
as you type with a short debounce delay (around 300 ms). Press Enter or tap
the search icon to submit the query explicitly.

The search bar remembers your most recent queries. When you focus the bar
without typing, a **Recent Searches** list appears showing your last ten
searches. Tap any recent search to run it again, or tap the X next to it to
remove it from history.

## Filter chips

Below the search bar, a row of filter chips lets you narrow results by type:

| Chip | What it includes |
|------|------------------|
| All | Everything (default) |
| Events | Calendar events |
| Reminders | Reminders and tasks |
| Files | Documents indexed from your folders |
| Photos | Photos indexed from your folders |
| People | Contacts and confirmed persons from the People Graph |

Tap a chip to activate it. The active chip is highlighted. Only one chip can
be active at a time. Tap the active chip again to deselect it and return to
All.

## Sort order

A sort button to the right of the filter chips toggles between two modes:

- **Relevance** (default) -- results are ranked by how well they match your
  query, using full-text search scoring from Meilisearch.
- **Date** -- results are sorted by date, newest first. For files and photos,
  the date is the file modification date or EXIF date taken.

## Result cards

Each result is displayed as a card showing:

- **Type icon** -- a small icon indicating whether the result is an event,
  reminder, file, photo, or person.
- **Title or name** -- the event title, reminder text, file name, or person
  name.
- **Snippet** -- a short excerpt with the matching terms highlighted.
- **Date** -- the relevant date for the item.

Tap a result card to open its detail view.

## Infinite scroll

Results load in pages of 20. As you scroll down, the next page loads
automatically. A subtle loading indicator appears at the bottom while the
next batch is being fetched. Scroll position is preserved if you navigate
to a detail view and come back.

## Empty and error states

- **No results** -- "No results for [query]" with a suggestion to broaden
  your search or try different keywords.
- **Indexing in progress** -- if search returns nothing and indexing is still
  running, a banner reminds you that not all content has been indexed yet.
- **Service unavailable** -- if Meilisearch is not running, an error banner
  appears with a link to the Manager to restart services.

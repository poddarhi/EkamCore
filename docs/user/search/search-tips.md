# Search Tips

These tips help you get better results from EkamCore's search.

## Use specific terms

The more specific your query, the fewer irrelevant results you get. Instead
of "meeting", try "quarterly review meeting" or "standup with marketing".

## Filter by type

Use the filter chips below the search bar to restrict results to a single
category. If you know you are looking for a file, tap the **Files** chip
before searching. This eliminates noise from events and reminders that happen
to share the same keywords.

## Search by date range

Include dates or relative time expressions in your query to narrow results:

| Example query | What it finds |
|---------------|---------------|
| `invoice January 2026` | Files or events mentioning "invoice" around January 2026 |
| `meeting last week` | Events from the past seven days matching "meeting" |
| `photos December` | Photos taken or modified in December |

Date parsing is best-effort. If results are not what you expect, try a more
explicit date format such as `2026-01-15`.

## Search for people

Typing a person's name triggers People Graph context. EkamCore automatically
expands the search to include:

- Calendar events where that person was an attendee.
- Documents associated with that person.
- Photos where that person's face was detected (if face clustering is enabled).
- Reminders that mention the person's name.

This works for both full names ("Sarah Chen") and first names ("Sarah"), though
full names produce more precise results.

## Combine keywords

You can combine multiple keywords to intersect results. For example:

- `budget spreadsheet 2025` -- finds files about budgets from 2025.
- `dentist reminder overdue` -- finds overdue reminders related to the dentist.

Keywords are matched with AND logic by default, so every term must appear
somewhere in the result.

## Use natural-language questions

For complex queries, switch to natural-language mode by starting with `?` or
a question word. See [Natural-Language Search](natural-language.md) for details.

Examples:

- `?what meetings do I have with the design team this month`
- `when was the last time I updated the project plan`

## Check recent searches

When you focus the search bar, your last ten searches appear. Tap one to re-run
it instantly. This is useful for queries you repeat frequently.

## Troubleshooting poor results

- **No results at all** -- make sure indexing has finished. Check
  **Settings > Indexing** for progress.
- **Too many results** -- add more keywords or apply a type filter.
- **Missing files** -- verify the folder is listed in
  **Settings > Data Sources > Document Folders** and that its status badge is
  green.
- **Person not found** -- confirm the contact exists in Apple Contacts and
  that Contacts access is enabled in Settings.

# Recap

The Recap screen gives you a backward-looking summary of what happened --
events attended, reminders completed, and items that slipped through. It is
available from the **Recap** tab in the bottom navigation bar.

## Daily vs Weekly toggle

At the top of the screen, two tabs let you switch between views:

- **Daily** -- shows a single day's recap.
- **Weekly** -- aggregates the last seven days into one summary.

The toggle remembers your last choice across sessions.

## Date navigation

Below the toggle, left and right arrows let you step through dates:

- In Daily mode, each tap moves one day forward or backward.
- In Weekly mode, each tap moves one full week.

Tap the date label in the centre to open a calendar picker and jump directly
to any date. The most recent available recap is shown by default when you open
the tab.

## Sections

### Events attended

A list of calendar events from the selected period. Each entry shows the event
title, time, and calendar colour. Events that were declined or cancelled are
excluded.

### Reminders completed

Reminders you marked as done during the period. Each entry shows the reminder
title, the list it belonged to, and the time it was completed.

### Newly overdue

Reminders that had a due date within the period but were not completed. These
appear with a red overdue label. Tapping an overdue reminder opens its detail
view where you can mark it done or reschedule.

### People seen (Weekly only)

In Weekly mode, an additional section lists people who appeared in events
during the week. Each person links to their profile in the People Graph.

## Caching

Recaps are cached locally for 24 hours. When you view a recap within the cache
window, it loads instantly without re-querying the database. After 24 hours
the cache entry expires and the recap is regenerated on next view.

Pull to refresh forces an immediate regeneration regardless of cache age.

## Empty state

If no events or reminders exist for a given day, the Recap screen shows
"Nothing to recap" with a subtle illustration. Weekly view may still have
content even if individual days are empty.

## Tips

- Use Weekly mode on Sundays for a quick review of the past week.
- Overdue reminders in Recap are a good prompt to clean up forgotten tasks.
- Tap any event or reminder to see its full details and related people.

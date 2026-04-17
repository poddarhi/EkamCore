# Today

The Today screen is the first thing you see when you open EkamCore. It gives
you a glanceable summary of your day -- events, reminders, birthdays, and
smart suggestions -- all in one place.

## Time-of-day greeting

The top of the screen shows a greeting that changes with the time of day:

- **Good morning** -- before noon
- **Good afternoon** -- noon to 5 pm
- **Good evening** -- after 5 pm

Below the greeting is today's date and a one-line summary such as
"3 events, 2 reminders due, 1 birthday".

## Card types

Today is built from cards. Each card has a coloured left border and an icon
indicating its type:

| Card type | Icon | What it shows |
|-----------|------|---------------|
| Event | Calendar dot | Upcoming or in-progress calendar event with time, title, and location |
| Reminder | Checkbox | Reminder due today or overdue, with list name and priority |
| Status | Info circle | System status such as indexing progress or a service warning |
| Person | Avatar | A contact's birthday today, with their name and photo |
| Pack | Lightbulb | An AI-generated suggestion from your active PLA Packs |

Cards are sorted chronologically. Events and reminders with specific times
appear at their scheduled position. All-day events and untimed reminders
appear at the top.

## Confidence badges

Pack suggestion cards include a confidence badge:

- **High** (green) -- the suggestion is strongly supported by your data.
- **Medium** (yellow) -- the suggestion is plausible but based on limited
  signals.
- **Low** (grey) -- speculative; the model had little data to work with.

Tap the badge to see a brief explanation of why the suggestion was made.

## Pull to refresh

On both web and mobile, pull down (or click the refresh icon) to re-fetch
data. This triggers an immediate sync of Calendar, Reminders, and Contacts
and regenerates pack suggestions. The refresh typically completes in under
two seconds.

## Empty state

If there are no events, reminders, or suggestions for today, the screen shows
a calm illustration with the message "Nothing on the agenda." You can still
search or navigate to other sections from the tab bar.

## Interaction

Tap any card to open its detail view. For pack suggestion cards, you can also
swipe or use action buttons to accept, dismiss, or snooze the suggestion.
See [Card Actions](card-actions.md) for full details.

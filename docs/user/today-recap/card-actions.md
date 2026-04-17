# Card Actions

Every card on the Today and Recap screens supports a set of actions. The
available actions depend on the card type.

## Tap to open detail

Tap (or click) any card to open its full detail view:

- **Event cards** open the event detail with title, time, location, notes,
  attendees, and a link to the original calendar entry.
- **Reminder cards** open the reminder detail with title, due date, priority,
  list name, and a button to mark it complete.
- **Person cards** open the person's profile in the People Graph, showing
  their photos, files, events, and reminders.
- **Status cards** open the relevant Settings page (for example, the Indexing
  status page).
- **Pack suggestion cards** open the suggestion detail with a full explanation,
  confidence level, and source citations.

## Pack suggestion actions

Pack suggestion cards have three action buttons, visible on the card itself
without needing to open the detail view:

### Done

Mark the suggestion as completed. The card is removed from Today and logged
in your Recap. Use this when you have already acted on the suggestion or it
is no longer relevant.

### Dismiss

Permanently dismiss the suggestion. The card is removed and will not reappear.
EkamCore uses dismissals as a signal to improve future suggestions.

### Snooze

Postpone the suggestion to a later time. Tapping Snooze opens a date picker
where you can choose when the suggestion should reappear:

- **Later today** -- reappears in 4 hours.
- **Tomorrow** -- reappears the next morning.
- **Next week** -- reappears Monday morning.
- **Pick a date** -- opens a calendar picker for any future date.

Snoozed suggestions are hidden until the chosen time, then they reappear on
the Today screen as if they were new.

## Reminder quick-complete

Reminder cards show a checkbox on the left edge. Tap the checkbox to mark the
reminder as done without opening the detail view. The card animates out and
the completion syncs back to Apple Reminders.

## Keyboard shortcuts (web)

When using EkamCore in a browser, the following shortcuts work while a card
is focused:

| Key | Action |
|-----|--------|
| Enter | Open detail view |
| D | Mark pack suggestion as done |
| X | Dismiss pack suggestion |
| S | Snooze pack suggestion |
| Space | Toggle reminder complete |

## Swipe gestures (mobile)

On the mobile app:

- **Swipe right** on a pack suggestion to mark it as done.
- **Swipe left** on a pack suggestion to dismiss it.
- **Long press** on a pack suggestion to open the snooze date picker.
- **Swipe right** on a reminder to mark it complete.

## Undo

After completing, dismissing, or snoozing a card, a brief undo toast appears
at the bottom of the screen for five seconds. Tap **Undo** to reverse the
action and restore the card.

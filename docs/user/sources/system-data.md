# System Data Sources

EkamCore can read from three built-in macOS data stores -- Calendar, Reminders,
and Contacts. All access is read-only, and the data never leaves your Mac.

## Granting permissions

Each source requires a macOS privacy permission. The first-run setup wizard
prompts for all three, but you can also enable them later:

1. Open **Settings > Data Sources > System Data**.
2. Toggle the switch next to the source you want to enable.
3. macOS shows a permission dialog. Click **Allow**.

If you previously denied a permission, macOS will not show the dialog again.
Instead, go to **System Settings > Privacy & Security**, find the relevant
category (Calendars, Reminders, or Contacts), and enable EkamCore manually.

## Calendar

| Detail | Value |
|--------|-------|
| Access | Read-only via EventKit |
| Data imported | Event title, start/end time, location, notes, attendees, calendar colour |
| Sync frequency | Every 5 minutes and on app launch |
| Scope | All calendars visible in Apple Calendar (iCloud, Google, Exchange, local) |

Calendar events power the **Today** screen (upcoming events), **Recap**
(events attended), and **Search** (find past events by keyword or date).

Recurring events are expanded into individual occurrences for the current and
next 30 days. Past recurrences are stored as they occurred.

## Reminders

| Detail | Value |
|--------|-------|
| Access | Read-only via EventKit |
| Data imported | Title, due date, priority, completion status, list name |
| Sync frequency | Every 5 minutes and on app launch |
| Scope | All reminder lists visible in Apple Reminders |

Reminders appear on the **Today** screen when they are due today or overdue.
Completed reminders appear in the **Recap** so you can see what you finished.

## Contacts

| Detail | Value |
|--------|-------|
| Access | Read-only via Contacts framework |
| Data imported | Display name, email addresses, phone numbers, birthday, organisation, thumbnail photo |
| Sync frequency | Every 15 minutes and on app launch |
| Scope | All contact groups in Apple Contacts |

Contact data feeds the **People Graph**. When a contact has a birthday, it
appears on the **Today** screen. Contact names are also used to enrich search
results -- searching a person's name returns events they attended, reminders
that mention them, and documents associated with them.

## What is not imported

EkamCore deliberately skips:

- Calendar attachments (only metadata is read).
- Reminder sub-tasks (top-level items only).
- Contact notes (to avoid importing sensitive free-text fields).

## Revoking access

Toggle any source off in **Settings > Data Sources > System Data**. Previously
imported data is removed from the index within one sync cycle (up to 15
minutes). You can also revoke access at the macOS level in System Settings.

# Person Profiles

A person profile is the central page for everything EkamCore knows about an
individual. Profiles are created when you confirm a face cluster or when a
contact is imported from Apple Contacts.

## Accessing profiles

- Open the **People** tab and browse or search the list of confirmed persons.
- Tap a person's name or avatar anywhere in the app (search results, event
  attendees, photo overlays) to jump to their profile.

## Profile header

The top of the profile shows:

- **Avatar** -- the best face thumbnail from the person's confirmed photos.
  If no face photos exist, a generic initial-based avatar is used.
- **Display name** -- the name you assigned during review, or the name from
  Apple Contacts if linked.
- **Face count** -- the total number of detected face occurrences across all
  photos (for example, "47 photos").
- **Linked contact** badge -- shows a link icon if this person is connected to
  an Apple Contact. Tap the badge to view the contact card.

## Tabs

Below the header, four tabs organise the person's related data:

### Photos

A grid of all photos where this person's face was detected. Tap a photo to
open the lightbox. Photos are sorted newest first.

### Files

Documents associated with this person. Association is based on the person's
name appearing in the document content or filename. Tap a file to open it
in PaperlessNGX.

### Events

Calendar events where this person was listed as an attendee, or where their
name appeared in the event title or notes. Sorted newest first.

### Reminders

Reminders that mention this person's name in the title. Sorted by due date.

## Renaming a person

1. Tap the pencil icon next to the display name.
2. Type the new name and tap **Save**.

The new name is applied everywhere the person appears -- search results,
photo overlays, and event attendee lists.

## Linking to an Apple Contact

If a person profile is not yet linked to a contact:

1. Tap **Link Contact** below the display name.
2. A contact picker appears. Search for and select the matching contact.
3. The profile inherits the contact's email addresses, phone numbers, and
   birthday.

To unlink, open the profile menu (three dots) and tap **Unlink Contact**.

## Merging profiles

If the same person has two profiles (for example, one from face clustering and
one from contacts):

1. Open one of the profiles.
2. Tap the three-dot menu and select **Merge with another person**.
3. Search for and select the other profile.
4. Confirm the merge. All photos, files, events, and reminders are combined
   under a single profile.

Merging cannot be undone, so review both profiles before confirming.

## Deleting a person

Open the three-dot menu and tap **Delete Person**. The profile is removed.
If face clustering is enabled, the associated face embeddings are also deleted.
Original photos and files are never affected.

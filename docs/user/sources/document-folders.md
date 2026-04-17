# Document Folders

EkamCore indexes documents you choose so they become searchable alongside your
calendar, reminders, and contacts. All processing happens locally on your Mac.

## Adding a folder

1. Open **Settings > Data Sources > Document Folders**.
2. Click **Add Folder**.
3. A macOS folder picker appears. Select the folder you want to index.
4. The folder and all of its subfolders are added to the index queue.

You can add as many folders as you like. To remove a folder, click the trash
icon next to it in the list. Removing a folder deletes its entries from the
search index but does not touch the original files.

## Supported file types

| Format | Extensions |
|--------|------------|
| PDF | `.pdf` |
| Word | `.docx` |
| Plain text | `.txt` |
| OpenDocument Text | `.odt` |
| Excel | `.xlsx` |
| CSV | `.csv` |
| PowerPoint | `.pptx` |
| Markdown | `.md` |
| HTML | `.html`, `.htm` |

Files that do not match a supported type are silently skipped. The maximum
file size is 100 MB per file.

## Sync status indicators

Each folder in the list shows a status badge:

| Badge | Meaning |
|-------|---------|
| Green circle | Fully indexed and up to date |
| Yellow spinner | Indexing in progress |
| Red exclamation | Error during last sync (tap for details) |
| Grey dash | Folder is queued but has not started yet |

EkamCore watches folders for changes using macOS file-system events. When you
add, edit, or delete a file inside an indexed folder, the change is picked up
automatically within a few seconds.

## PaperlessNGX integration

Behind the scenes, documents are ingested through PaperlessNGX, which runs as
a Docker container managed by the Manager app. PaperlessNGX handles OCR for
scanned PDFs, text extraction, and tagging.

You can open the PaperlessNGX web interface directly from
**Settings > Services > PaperlessNGX** if you want to review documents, add
custom tags, or adjust OCR settings. Any tags you create in PaperlessNGX
appear as filter options in the EkamCore search interface.

## Tips

- **Start small.** Add one or two key folders first, let indexing finish, then
  add more. This keeps your Mac responsive during the initial scan.
- **Avoid system folders.** Adding `/` or your entire home directory will work
  but will produce a lot of noise. Pick folders that contain documents you
  actually want to find.
- **Check the status page.** If a file fails to index, the error detail usually
  points to a corrupt file or an unsupported encoding.

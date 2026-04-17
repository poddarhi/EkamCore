# Files

The Files screen shows all documents indexed from your chosen folders. You can
browse, search, and open files directly from EkamCore.

## File list

Files are displayed in a scrollable list. Each row shows:

- **Type icon** -- a coloured icon indicating the file format (PDF, Word,
  spreadsheet, presentation, text, etc.).
- **File name** -- the original name of the file.
- **Folder path** -- the parent folder, shown in smaller text below the name.
- **Date modified** -- the last modification date of the file.
- **File size** -- displayed in human-readable units (KB, MB).

The list is sorted by date modified (newest first) by default. Tap the sort
button to switch to alphabetical or file-size ordering.

## Opening a file

Tap any file in the list to open it in PaperlessNGX. PaperlessNGX provides:

- A rendered preview of the document (PDF viewer, text display, etc.).
- OCR text for scanned documents.
- Tags and metadata assigned during indexing.
- A download button to save the original file.

PaperlessNGX opens in a built-in browser view on mobile or in a new tab on
the web.

## Searching within files

Use the search bar at the top of the Files screen to search within file
contents, not just file names. EkamCore uses full-text indexing powered by
Meilisearch, so the search covers:

- File names and paths.
- Extracted text content (including OCR text from scanned PDFs).
- PaperlessNGX tags.

Matching terms are highlighted in the result snippets.

You can also search files from the global Search screen by selecting the
**Files** filter chip.

## Supported formats

| Category | Formats |
|----------|---------|
| Documents | PDF, DOCX, TXT, ODT, MD, HTML |
| Spreadsheets | XLSX, CSV |
| Presentations | PPTX |

The maximum file size is 100 MB. See [Supported Formats](supported-formats.md)
for the complete reference.

## Sync status

A small status dot next to each file indicates its index state:

| Dot colour | Meaning |
|------------|---------|
| Green | Indexed and up to date |
| Yellow | Re-indexing after a file change |
| Red | Indexing failed (tap for error details) |

Files are re-indexed automatically when their contents change on disk.

## Tips

- Use the global search with the Files chip for the fastest way to find a
  specific document.
- If a PDF shows no text content, it may be a scanned image. PaperlessNGX
  runs OCR automatically, but low-quality scans may produce incomplete text.
- To add more folders, go to **Settings > Data Sources > Document Folders**.

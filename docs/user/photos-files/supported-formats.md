# Supported Formats

EkamCore indexes documents and photos from your local folders. This page lists
every file format that is supported, along with size limits and notes on how
each format is processed.

## Documents

| Format | Extensions | Processing notes |
|--------|------------|------------------|
| PDF | `.pdf` | Text-based PDFs are indexed directly. Scanned PDFs go through OCR via PaperlessNGX. |
| Word | `.docx` | Text, tables, and embedded headings are extracted. Legacy `.doc` files are not supported. |
| Plain text | `.txt` | Indexed as-is. UTF-8 encoding is expected; other encodings are handled on a best-effort basis. |
| OpenDocument Text | `.odt` | Full text extraction including headings and lists. |
| Excel | `.xlsx` | Cell contents are extracted as searchable text. Formulas are stored as their display values. Legacy `.xls` files are not supported. |
| CSV | `.csv` | All cell values are indexed. Large CSVs (over 50,000 rows) may take longer to process. |
| PowerPoint | `.pptx` | Slide text and speaker notes are extracted. Legacy `.ppt` files are not supported. |
| Markdown | `.md` | Indexed as plain text with Markdown syntax stripped for cleaner search results. |
| HTML | `.html`, `.htm` | Visible text is extracted; tags, scripts, and styles are stripped. |

## Photos

| Format | Extensions | Processing notes |
|--------|------------|------------------|
| JPEG | `.jpg`, `.jpeg` | EXIF metadata (date, GPS, camera) is extracted. Most common photo format. |
| PNG | `.png` | EXIF support is limited for PNG; file modification date is used as fallback. |
| HEIC | `.heic`, `.heif` | Native Apple format. Full EXIF extraction including Live Photo metadata. |
| TIFF | `.tif`, `.tiff` | EXIF metadata is extracted. Large TIFF files may be slow to thumbnail. |
| WebP | `.webp` | EXIF extraction supported. Animated WebP files are treated as a single frame. |

## File size limit

The maximum supported file size is **100 MB** per file. Files exceeding this
limit are skipped during indexing. A warning appears in
**Settings > Indexing** when a file is skipped due to size.

## Unsupported formats

Files that do not match any of the above extensions are silently ignored during
indexing. Common formats that are **not** currently supported include:

- Legacy Office formats: `.doc`, `.xls`, `.ppt`
- Image formats: `.bmp`, `.svg`, `.raw`, `.cr2`, `.nef`
- Video: `.mp4`, `.mov`, `.avi`
- Audio: `.mp3`, `.wav`, `.m4a`
- Archives: `.zip`, `.tar`, `.gz`

If you need support for an additional format, check the
[GitHub Issues](https://github.com/AKEkam/EkamCore/issues) page to see if
it has been requested or to file a new request.

## Encoding

Text-based formats (TXT, CSV, MD, HTML) are expected to use UTF-8 encoding.
Files in other encodings (Latin-1, Windows-1252, etc.) are processed on a
best-effort basis. If a file appears garbled in search results, re-saving it
as UTF-8 usually resolves the issue.

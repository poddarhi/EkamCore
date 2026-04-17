# Slow Queries

If search or natural-language queries are taking noticeably longer than
usual, this page covers the most common causes and solutions.

## Possible causes

### 1. Ollama loading a model (first query)

The most common reason for a slow first query is that Ollama needs to load
the language model into memory. This happens:

- After EkamCore services are started or restarted.
- After the Mac wakes from sleep.
- After an Ollama model update.

**What to expect**: The first query after a cold start can take 15 to 30
seconds. Subsequent queries should return in one to three seconds.

**Solution**: Simply wait for the first query to complete. Ollama keeps the
model loaded in memory for future requests. You can verify the model is
loaded by checking the Manager dashboard -- the Ollama tile shows "Model
loaded" in its subtitle when ready.

### 2. Large dataset

If you have indexed a very large number of files (over 100,000 documents or
50,000 photos), queries may be slower because:

- Meilisearch has more data to scan for full-text matches.
- Qdrant has more vectors to compare for semantic search.
- The API server spends more time aggregating results.

**Solution**:

- Use more specific queries. "Meeting notes from March about budget" is
  faster than "notes".
- Reduce the number of indexed source folders if some contain files you
  do not need (for example build artifacts or vendor directories).
- Add ignore patterns in **Settings > Sources > Ignore Patterns** for
  directories that should not be indexed.

### 3. Low available memory

EkamCore services use approximately 5 to 6 GB of RAM in total. On a Mac
with 8 GB of unified memory, there is little headroom.

**Symptoms**: Queries are slow and Activity Monitor shows high memory
pressure (yellow or red indicator).

**Solution**:

- Close other memory-intensive applications while using EkamCore.
- In the Manager, go to **Settings** and reduce the Ollama model size if
  a smaller model is available.
- Consider upgrading to a Mac with 16 GB or more of unified memory for
  the best experience.

### 4. Active background jobs

Folder scans, face clustering, and PLA generation compete for CPU and
memory with query processing.

**Symptoms**: Queries slow down during or just after adding a new source
folder.

**Solution**:

- Open the Manager and check the **Jobs** panel. Wait for active jobs to
  finish, or cancel non-urgent ones.
- Schedule heavy jobs for off-hours using the PLA Pack schedule settings.

## Checking query performance

The web interface shows query timing at the bottom of search results (for
example "42 results in 1.2s"). If times consistently exceed five seconds
for focused queries on a dataset under 50,000 files, something else may be
wrong -- see [Hub Unreachable](hub-unreachable.md) for service-level
diagnosis.

# Disk Full

When your Mac's disk runs low on space, EkamCore services can fail in
unpredictable ways. This page explains the symptoms and how to free up
space.

## Symptoms

- Document ingestion stalls or new files are not indexed.
- PostgreSQL crashes or refuses to start (shown as a red tile in the
  Manager dashboard).
- Meilisearch returns errors when indexing.
- Backup jobs fail with a "no space left on device" error.
- The Manager dashboard shows an orange banner: "Disk usage above 90%".

## How much space does EkamCore use?

Typical disk usage by component:

| Component | Typical size |
|-----------|-------------|
| Docker images | 3 -- 5 GB |
| PostgreSQL data | 500 MB -- 2 GB (depends on indexed files) |
| Meilisearch index | 500 MB -- 3 GB |
| Qdrant vectors | 200 MB -- 1 GB |
| Ollama models | 2 -- 8 GB per model |
| Backups | 500 MB -- 2 GB each |
| Docker build cache | 1 -- 5 GB (accumulates over time) |

## Solution steps

### 1. Clean Docker build cache

The fastest way to reclaim space:

1. Open the **Manager** app.
2. Go to **Storage > Clean Docker Cache**.
3. Confirm the action. This removes unused build layers and typically
   frees 1 to 5 GB.

Or from the terminal:

```
docker system prune -f
```

### 2. Delete old backups

1. In the Manager, go to **Updates > Backup History**.
2. Review the list and delete backups you no longer need.
3. Pinned backups are not auto-deleted, so check if any old pinned backups
   can be unpinned and removed.

Or manually delete files from:

```
~/Library/Application Support/EkamCore/backups/
```

### 3. Check Ollama model sizes

Ollama models can be large. List installed models:

```
docker exec ekamcore-ollama ollama list
```

If you see models you no longer use, remove them:

```
docker exec ekamcore-ollama ollama rm <model-name>
```

### 4. Prune unused Docker images

Old EkamCore images from previous updates may still be on disk:

```
docker image prune -a -f
```

This removes all images not used by running containers.

### 5. Remove unused source folders

If you added source folders you no longer need, remove them in
**Settings > Sources** and then click **Purge Index** to reclaim the
search index space.

## Preventing future issues

- Set a reasonable backup retention period (default is 7 days). Shorter
  retention means less disk usage.
- Schedule Docker cache cleanup monthly via the Manager's **Storage**
  panel.
- Monitor the **Disk Usage** KPI card on the dashboard. If it consistently
  exceeds 80 percent of your total disk, consider reducing indexed sources
  or upgrading storage.

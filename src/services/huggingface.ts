// Lightweight client for the public Hugging Face Hub API. All network calls
// are unauthenticated and never throw — they return [] / null on failure.

export interface HfRepo {
  id: string; // e.g. "bartowski/Llama-3.2-1B-Instruct-GGUF"
  author: string;
  downloads: number;
  likes: number;
}

export interface HfQuant {
  filename: string;
  quant: string;
  sizeBytes: number;
  url: string;
}

const API = 'https://huggingface.co/api/models';

/** Extract a quantization label from a GGUF filename, e.g. "Q4_K_M", "IQ4_XS", "F16". */
export function parseQuant(filename: string): string {
  const m = filename.match(
    /[-_.]((?:IQ|Q)\d+(?:_[A-Za-z0-9]+)*|F16|BF16|F32)\.gguf$/i,
  );
  return m ? m[1].toUpperCase() : 'GGUF';
}

/**
 * Choose a sensible default quant: prefer the common balanced ones, otherwise
 * the median by size. Returns null for an empty list.
 */
export function pickRecommended(quants: HfQuant[]): HfQuant | null {
  if (quants.length === 0) {
    return null;
  }
  for (const pref of ['Q4_K_M', 'Q4_K_S', 'Q4_0']) {
    const hit = quants.find(q => q.quant === pref);
    if (hit) {
      return hit;
    }
  }
  const bySize = [...quants].sort((a, b) => a.sizeBytes - b.sizeBytes);
  return bySize[Math.floor(bySize.length / 2)];
}

/** Search Hugging Face for GGUF model repos. Empty query → trending by downloads. */
export async function searchGgufModels(query: string): Promise<HfRepo[]> {
  try {
    const url =
      `${API}?filter=gguf&limit=25&sort=downloads&direction=-1` +
      (query.trim() ? `&search=${encodeURIComponent(query.trim())}` : '');
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!res.ok) {
      return [];
    }
    const data = await res.json();
    if (!Array.isArray(data)) {
      return [];
    }
    return data.map((m: any) => ({
      id: String(m.id ?? ''),
      author: String(m.author ?? (m.id ?? '').split('/')[0] ?? ''),
      downloads: Number(m.downloads ?? 0),
      likes: Number(m.likes ?? 0),
    }));
  } catch {
    return [];
  }
}

/**
 * List the single-file GGUF quantizations in a repo (excludes sharded
 * multi-part files), sorted smallest first.
 */
export async function listQuants(repoId: string): Promise<HfQuant[]> {
  try {
    const res = await fetch(
      `${API}/${repoId}/tree/main?recursive=true`,
      { headers: { Accept: 'application/json' } },
    );
    if (!res.ok) {
      return [];
    }
    const data = await res.json();
    if (!Array.isArray(data)) {
      return [];
    }
    const quants: HfQuant[] = [];
    for (const f of data) {
      const path: string = f?.path ?? '';
      if (!path.toLowerCase().endsWith('.gguf')) {
        continue;
      }
      if (/-\d{5}-of-\d{5}/i.test(path)) {
        continue; // skip sharded multi-part files
      }
      const sizeBytes = Number(f?.lfs?.size ?? f?.size ?? 0);
      if (!sizeBytes) {
        continue;
      }
      quants.push({
        filename: path,
        quant: parseQuant(path),
        sizeBytes,
        url: `https://huggingface.co/${repoId}/resolve/main/${path}`,
      });
    }
    return quants.sort((a, b) => a.sizeBytes - b.sizeBytes);
  } catch {
    return [];
  }
}

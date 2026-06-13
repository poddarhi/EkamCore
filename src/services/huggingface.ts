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

/** True for a multimodal projector file (the second file a vision model needs). */
export function isMmproj(path: string): boolean {
  return /mmproj/i.test(path);
}

/**
 * Search Hugging Face for GGUF model repos. Empty query → trending by downloads.
 * When `vision` is set, restricts to image-text-to-text (vision) models so the
 * results are actual vision repos rather than text models.
 */
export async function searchGgufModels(
  query: string,
  vision = false,
): Promise<HfRepo[]> {
  try {
    const url =
      `${API}?filter=gguf&limit=25&sort=downloads&direction=-1` +
      (vision ? '&pipeline_tag=image-text-to-text' : '') +
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
      if (isMmproj(path)) {
        continue; // mmproj is a companion, not a selectable base quant
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

/**
 * List a repo's GGUF files split into base quants and mmproj projectors. A repo
 * is a usable vision model only when it has at least one of each. Used by the
 * vision browse to pair a chosen base quant with its projector.
 */
export async function listGgufRepo(
  repoId: string,
): Promise<{ quants: HfQuant[]; mmprojs: HfQuant[] }> {
  try {
    const res = await fetch(`${API}/${repoId}/tree/main?recursive=true`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      return { quants: [], mmprojs: [] };
    }
    const data = await res.json();
    if (!Array.isArray(data)) {
      return { quants: [], mmprojs: [] };
    }
    const quants: HfQuant[] = [];
    const mmprojs: HfQuant[] = [];
    for (const f of data) {
      const path: string = f?.path ?? '';
      if (!path.toLowerCase().endsWith('.gguf')) {
        continue;
      }
      if (/-\d{5}-of-\d{5}/i.test(path)) {
        continue;
      }
      const sizeBytes = Number(f?.lfs?.size ?? f?.size ?? 0);
      if (!sizeBytes) {
        continue;
      }
      const entry: HfQuant = {
        filename: path,
        quant: parseQuant(path),
        sizeBytes,
        url: `https://huggingface.co/${repoId}/resolve/main/${path}`,
      };
      (isMmproj(path) ? mmprojs : quants).push(entry);
    }
    quants.sort((a, b) => a.sizeBytes - b.sizeBytes);
    mmprojs.sort((a, b) => a.sizeBytes - b.sizeBytes);
    return { quants, mmprojs };
  } catch {
    return { quants: [], mmprojs: [] };
  }
}

/** Pick the projector to pair with a base model: prefer Q8_0, then F16, else smallest. */
export function pickMmproj(mmprojs: HfQuant[]): HfQuant | null {
  if (mmprojs.length === 0) {
    return null;
  }
  for (const pref of ['Q8_0', 'F16', 'BF16']) {
    const hit = mmprojs.find(m => m.quant === pref);
    if (hit) {
      return hit;
    }
  }
  return mmprojs[0]; // already smallest-first
}

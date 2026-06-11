import RNBlobUtil, {
  type StatefulPromise,
  type FetchBlobResponse,
} from 'react-native-blob-util';
import { ModelInfo } from '../types';

const MODELS_DIR = `${RNBlobUtil.fs.dirs.DocumentDir}/models`;

export function modelFilePath(model: ModelInfo): string {
  // Derive a stable, filesystem-safe filename from the model id.
  return `${MODELS_DIR}/${model.id}.gguf`;
}

export async function ensureModelsDir(): Promise<void> {
  const exists = await RNBlobUtil.fs.exists(MODELS_DIR);
  if (!exists) {
    await RNBlobUtil.fs.mkdir(MODELS_DIR);
  }
}

export async function fileSize(path: string): Promise<number> {
  try {
    const stat = await RNBlobUtil.fs.stat(path);
    return Number(stat.size) || 0;
  } catch {
    return 0;
  }
}

/**
 * A model counts as "downloaded" only if the file exists AND is a plausible
 * size (a few MB at minimum). This guards against half-written files or HTML
 * error pages that some CDNs return with a 200 status.
 */
export async function isModelDownloaded(model: ModelInfo): Promise<boolean> {
  const path = modelFilePath(model);
  if (!(await RNBlobUtil.fs.exists(path))) {
    return false;
  }
  const size = await fileSize(path);
  return size > 1_000_000; // > 1 MB
}

export async function deleteModel(model: ModelInfo): Promise<void> {
  const path = modelFilePath(model);
  if (await RNBlobUtil.fs.exists(path)) {
    await RNBlobUtil.fs.unlink(path);
  }
  const tmp = `${path}.part`;
  if (await RNBlobUtil.fs.exists(tmp)) {
    await RNBlobUtil.fs.unlink(tmp);
  }
}

export interface DownloadHandle {
  task: Promise<void>;
  cancel: () => void;
}

/**
 * Start downloading a model GGUF file. Returns a handle whose `task` resolves
 * when the download finishes (and the file is verified) or rejects with a
 * descriptive error. `cancel()` aborts mid-flight.
 */
export function startDownload(
  model: ModelInfo,
  onProgress: (received: number, total: number) => void,
): DownloadHandle {
  const dest = modelFilePath(model);
  const tmp = `${dest}.part`;

  const fetchTask: StatefulPromise<FetchBlobResponse> = RNBlobUtil.config({
    path: tmp,
    fileCache: false,
    overwrite: true,
    followRedirect: true,
  }).fetch('GET', model.url, {
    'User-Agent': 'EkamCore/1.0 (react-native)',
    Accept: 'application/octet-stream',
  });

  fetchTask.progress({ interval: 300 }, (received, total) => {
    onProgress(Number(received) || 0, Number(total) || 0);
  });

  const task: Promise<void> = (async () => {
    let res: FetchBlobResponse;
    try {
      res = await fetchTask;
    } catch (e: any) {
      await safeUnlink(tmp);
      throw new Error(`Network error: ${e?.message ?? 'download failed'}`);
    }

    const status = Number(res.info()?.status ?? 0);
    if (status >= 400) {
      await safeUnlink(tmp);
      throw new Error(`Server returned HTTP ${status}`);
    }

    // Verify what actually landed on disk.
    const partSize = await fileSize(tmp);
    if (partSize <= 1_000_000) {
      // Likely an error/HTML page rather than a real model.
      await safeUnlink(tmp);
      throw new Error(
        `Downloaded file is too small (${partSize} bytes) — the link may be invalid or require a Hugging Face token.`,
      );
    }

    await safeUnlink(dest);
    await RNBlobUtil.fs.mv(tmp, dest);

    if (!(await RNBlobUtil.fs.exists(dest))) {
      throw new Error('Failed to finalize the downloaded file.');
    }
  })();

  return {
    task,
    cancel: () => {
      fetchTask.cancel();
      safeUnlink(tmp);
    },
  };
}

async function safeUnlink(path: string): Promise<void> {
  try {
    if (await RNBlobUtil.fs.exists(path)) {
      await RNBlobUtil.fs.unlink(path);
    }
  } catch {
    // ignore
  }
}

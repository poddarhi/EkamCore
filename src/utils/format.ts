/**
 * Translate a GGUF quantization label (Q4_K_M, IQ4_XS, Q8_0…) into plain
 * language. The technical label stays available as secondary detail; this is
 * what non-technical users read first.
 */
export function quantLabel(quant: string): string {
  const q = (quant || '').toUpperCase();
  if (/Q2|Q3|IQ1|IQ2|IQ3/.test(q)) return 'Smallest';
  if (/IQ4|Q4_0|Q4_1/.test(q)) return 'Compact';
  if (/Q4/.test(q)) return 'Balanced';
  if (/Q5/.test(q)) return 'High quality';
  if (/Q6|Q8|F16|BF16|F32/.test(q)) return 'Max quality';
  return 'Standard';
}

export function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) {
    return '—';
  }
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

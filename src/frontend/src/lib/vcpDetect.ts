/** Deteccao rapida de Verification Case Package (VCP) (.vcp.zip) sem enviar o arquivo ao servidor. */

const ZIP_SIG = [0x50, 0x4b, 0x03, 0x04] as const;

async function readBytes(file: File, start: number, length: number): Promise<Uint8Array> {
  const end = Math.min(start + length, file.size);
  if (start >= end) return new Uint8Array(0);
  return new Uint8Array(await file.slice(start, end).arrayBuffer());
}

function hasZipLocalHeader(bytes: Uint8Array): boolean {
  if (bytes.length < 4) return false;
  return (
    bytes[0] === ZIP_SIG[0] &&
    bytes[1] === ZIP_SIG[1] &&
    (bytes[2] === ZIP_SIG[2] || bytes[2] === 0x03 || bytes[2] === 0x05 || bytes[2] === 0x07)
  );
}

/** Nomes tipicos do VCP aparecem sem compressao no central directory (final do ZIP). */
function centralDirectoryLooksLikeVcp(text: string): boolean {
  return (
    text.includes("package.json") &&
    text.includes("case/case.json") &&
    text.includes("case/custody_records.json") &&
    text.includes("crypto/public_key.pem")
  );
}

/**
 * Sonda estrutura VCP lendo apenas cabecalho e cauda do arquivo (~256 KiB).
 * Instantaneo mesmo para pacotes grandes.
 */
export async function probeVcpPackage(file: File): Promise<{
  isZip: boolean;
  looksLikeVcp: boolean;
}> {
  const head = await readBytes(file, 0, 4);
  const isZip = hasZipLocalHeader(head);
  if (!isZip) {
    return { isZip: false, looksLikeVcp: false };
  }

  const tailSize = Math.min(256 * 1024, file.size);
  const tailStart = Math.max(0, file.size - tailSize);
  const tail = await readBytes(file, tailStart, tailSize);
  const tailText = new TextDecoder("utf-8", { fatal: false }).decode(tail);

  return {
    isZip: true,
    looksLikeVcp: centralDirectoryLooksLikeVcp(tailText),
  };
}

export function isLikelyVcpFilename(name: string): boolean {
  const lower = name.toLowerCase();
  return lower.endsWith(".vcp.zip") || lower.endsWith(".zip");
}

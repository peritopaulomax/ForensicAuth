/** Deteccao rapida de pacote Peritus (.zip) sem enviar o arquivo ao servidor. */

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

/** Nome do manifesto aparece no central directory (final do ZIP) e, em ZIPs pequenos, no cabecalho. */
function looksLikePeritusInText(text: string): boolean {
  return (
    text.includes("peritusCase.xml") ||
    text.includes("<peritus>") ||
    text.includes("peritusCase")
  );
}

/**
 * Sonda estrutura Peritus lendo cabecalho e cauda do arquivo.
 * Pacotes grandes (ex.: 2+ GB) tem peritusCase.xml apenas no central directory — nao no primeiro MB.
 */
export async function probePeritusPackage(file: File): Promise<{
  isZip: boolean;
  looksLikePeritus: boolean;
}> {
  if (!file.name.toLowerCase().endsWith(".zip") && file.type !== "application/zip") {
    return { isZip: false, looksLikePeritus: false };
  }

  try {
    const head = await readBytes(file, 0, 4);
    const isZip = hasZipLocalHeader(head);
    if (!isZip) {
      return { isZip: false, looksLikePeritus: false };
    }

    const headScan = Math.min(512 * 1024, file.size);
    const headBuf = await readBytes(file, 0, headScan);
    const headText = new TextDecoder("utf-8", { fatal: false }).decode(headBuf);
    if (looksLikePeritusInText(headText)) {
      return { isZip: true, looksLikePeritus: true };
    }

    const tailSize = Math.min(512 * 1024, file.size);
    const tailStart = Math.max(0, file.size - tailSize);
    const tailBuf = await readBytes(file, tailStart, tailSize);
    const tailText = new TextDecoder("utf-8", { fatal: false }).decode(tailBuf);

    return {
      isZip: true,
      looksLikePeritus: looksLikePeritusInText(tailText),
    };
  } catch {
    return { isZip: false, looksLikePeritus: false };
  }
}

export function isLikelyPeritusFilename(name: string): boolean {
  return name.toLowerCase().endsWith(".zip");
}

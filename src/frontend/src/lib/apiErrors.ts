/** Extrai mensagem legivel de erros Axios/FastAPI. */

function formatConflictDetail(detail: Record<string, unknown>): string {
  const conflicts = detail.conflicts;
  if (Array.isArray(conflicts) && conflicts.length > 0) {
    const parts = conflicts.map((c) => {
      if (c && typeof c === "object") {
        const o = c as Record<string, unknown>;
        if (o.type === "case_id_exists") return "Ja existe um caso ativo com o mesmo ID";
        if (o.type === "protocol_exists") {
          return `Protocolo em uso: ${o.protocol_number ?? ""}`;
        }
        return JSON.stringify(o);
      }
      return String(c);
    });
    return parts.join("; ");
  }
  if (typeof detail.message === "string") {
    const extra =
      typeof detail.detail === "string" && detail.detail.length < 200
        ? detail.detail
        : "";
    return extra ? `${detail.message} (${extra})` : detail.message;
  }
  if (typeof detail.detail === "string") return detail.detail;
  return JSON.stringify(detail);
}

export function parseApiError(err: unknown, fallback: string): string {
  if (!err || typeof err !== "object") {
    return err instanceof Error ? err.message : fallback;
  }

  if ("response" in err) {
    const resp = (err as { response?: { data?: unknown; status?: number } }).response;
    const data = resp?.data;
    const status = resp?.status;

    if (data && typeof data === "object" && data !== null) {
      const obj = data as Record<string, unknown>;
      if (typeof obj.detail === "string") return obj.detail;
      if (Array.isArray(obj.detail)) {
        return obj.detail
          .map((d) =>
            d && typeof d === "object" && "msg" in d
              ? String((d as { msg: string }).msg)
              : String(d)
          )
          .join("; ");
      }
      if (obj.detail && typeof obj.detail === "object") {
        const d = obj.detail as Record<string, unknown>;
        if (typeof d.msg === "string") return d.msg;
        const parsed = formatConflictDetail(d);
        if (parsed) return parsed;
      }
      if (typeof obj.message === "string") return obj.message;
    }

    if (status === 409) {
      return "Conflito na importacao (409). Verifique se o caso ja existe ou se houve falha parcial anterior.";
    }
    if (status === 413) return "Arquivo muito grande para o servidor.";
    if (status === 504 || status === 408) {
      return "Tempo esgotado — pacotes grandes podem levar varios minutos. Tente novamente.";
    }
  }

  if ("message" in err && typeof (err as Error).message === "string") {
    const msg = (err as Error).message;
    if (msg === "Network Error") {
      return "Falha de rede ou tempo esgotado durante o envio do pacote.";
    }
    if (msg && !/^Request failed with status code \d+$/i.test(msg)) {
      return msg;
    }
  }

  return fallback;
}

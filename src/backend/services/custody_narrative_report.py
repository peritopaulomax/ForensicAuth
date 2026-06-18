"""Relatorio narrativo da cadeia de custodia — leitura humana (HTML / Markdown)."""

from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.case import Case
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from models.user import User
from services.custody_service import CustodyService
from services.custody_signing_service import CustodySigningService
from services.forensic_integrity_service import ForensicIntegrityService

_RECORD_TYPE_PT: dict[str, str] = {
    "evidence_upload": "Evidencia recebida",
    "evidence_deleted": "Evidencia removida",
    "derivative_saved": "Derivado forense gerado",
    "case_shared": "Caso compartilhado",
    "case_unshared": "Compartilhamento revogado",
    "case_closed": "Caso fechado",
    "case_reopened": "Caso reaberto",
    "case_closure_signed": "Assinatura de fechamento",
    "case_deleted": "Caso excluido",
    "report_generated": "Laudo gerado",
    "custody_signing_repair": "Correcao de assinaturas do sistema",
    "case_imported": "Caso importado de outra instancia",
    "case_imported_peritus": "Caso Peritus importado (pacote nativo)",
    "peritus_file_imported": "Arquivo Peritus importado (cadeia)",
    "case_exported_peritus": "Caso Peritus exportado (pacote nativo)",
    "analysis_started": "Analise iniciada (registro historico)",
    "analysis_completed": "Analise concluida (registro historico)",
    "analysis_failed": "Analise falhou (registro historico)",
}

_TECHNIQUE_PT: dict[str, str] = {
    "ela": "ELA (Error Level Analysis)",
    "jpeg_ghosts": "JPEG Ghosts",
    "dct": "Analise DCT",
    "resampling": "Reamostragem / deteccao de resize",
    "prnu": "PRNU (camera fingerprint)",
    "metadata": "Metadados",
    "pdf_forensic_extract": "Extracao forense PDF",
    "audio_forensics": "Audio forense",
    "audio_spectral": "Espectrograma de audio",
    "audio_levels": "Niveis de audio",
    "deepfake": "Deteccao de deepfake",
    "synthetic_image_detection": "Detecção de Imagens Sintéticas",
    "sepael": "Detecção de Imagens Sintéticas",
}


def _fmt_ts(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            raw = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%d/%m/%Y às %H:%M:%S")


def _fmt_size(n: Any) -> str:
    try:
        size = int(n)
    except (TypeError, ValueError):
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def _short_hash(h: str | None, n: int = 16) -> str:
    if not h:
        return "—"
    if len(h) <= n * 2:
        return h
    return f"{h[:n]}…{h[-n:]}"


def _evidence_label(ev: Evidence | None, eid: str | None = None) -> str:
    if ev:
        return f"«{ev.original_filename}»"
    if eid:
        return f"evidencia {eid[:8]}…"
    return "evidencia desconhecida"


def _format_params(params: Any) -> list[str]:
    if not params or not isinstance(params, dict):
        return []
    lines: list[str] = []
    for key, val in sorted(params.items(), key=lambda x: str(x[0])):
        if val is None or val == "" or val == {} or val == []:
            continue
        if isinstance(val, (dict, list)):
            text = json.dumps(val, ensure_ascii=False, indent=0)
            if len(text) > 200:
                text = text[:200] + "…"
        else:
            text = str(val)
        lines.append(f"{key}: {text}")
    return lines


class CustodyNarrativeReportService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, case_id: uuid.UUID) -> dict[str, Any]:
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError(f"Caso {case_id} nao encontrado")

        creator = self.db.query(User).filter(User.id == case.created_by).first()
        records = (
            self.db.query(CustodyRecord)
            .filter(CustodyRecord.case_id == case_id)
            .order_by(CustodyRecord.chain_sequence.asc())
            .all()
        )
        evidences = (
            self.db.query(Evidence)
            .filter(Evidence.case_id == case_id)
            .all()
        )
        evidence_by_id: dict[str, Evidence] = {str(e.id): e for e in evidences}

        chain = CustodyService(self.db).verify_chain(case_id)
        forensic = ForensicIntegrityService(self.db).verify_case_forensic_integrity(case_id)
        signing = CustodySigningService()

        events: list[dict[str, Any]] = []
        for rec in records:
            events.append(
                self._narrate_event(rec, evidence_by_id, signing)
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "case": {
                "id": str(case.id),
                "protocol_number": case.protocol_number,
                "title": case.title,
                "description": case.description,
                "status": case.status,
                "inquiry_number": case.inquiry_number,
                "process_number": case.process_number,
                "created_at": case.created_at.isoformat() if case.created_at else None,
                "creator_username": creator.username if creator else None,
            },
            "integrity": {
                "chain_valid": chain.get("valid", False),
                "records_checked": chain.get("records_checked", 0),
                "forensic_valid": forensic.get("valid", False),
                "signing_key_id": signing.key_id,
            },
            "statistics": {
                "custody_events": len(records),
                "evidences_total": len(evidences),
                "evidences_active": sum(1 for e in evidences if e.deleted_at is None),
            },
            "events": events,
        }

    def _narrate_event(
        self,
        rec: CustodyRecord,
        evidence_by_id: dict[str, Evidence],
        signing: CustodySigningService,
    ) -> dict[str, Any]:
        details = rec.details or {}
        actor = details.get("actor_username") or "usuario do sistema"
        ev = evidence_by_id.get(str(rec.evidence_id)) if rec.evidence_id else None
        title = _RECORD_TYPE_PT.get(rec.record_type, rec.record_type.replace("_", " ").title())
        paragraphs: list[str] = []
        bullets: list[str] = []

        if rec.record_type == "evidence_upload":
            fname = details.get("original_filename") or (ev.original_filename if ev else "arquivo")
            paragraphs.append(
                f"{actor} registrou o recebimento da evidencia «{fname}» no caso."
            )
            bullets.extend(
                [
                    f"Identificador: {rec.evidence_id or details.get('evidence_id', '—')}",
                    f"Tipo: {details.get('file_type') or (ev.file_type if ev else '—')}",
                    f"Tamanho: {_fmt_size(details.get('file_size') or (ev.file_size if ev else None))}",
                    f"SHA-256: {details.get('sha256') or rec.sha256_input or '—'}",
                ]
            )

        elif rec.record_type == "derivative_saved":
            technique = details.get("technique") or (details.get("operation") or {}).get(
                "technique"
            )
            tech_label = _TECHNIQUE_PT.get(str(technique), str(technique or "procedimento forense"))
            proc = details.get("procedure_summary") or (details.get("operation") or {}).get(
                "procedure_summary"
            )
            out_name = (
                details.get("derivative_filename")
                or details.get("artifact_filename")
                or (ev.original_filename if ev else "derivado")
            )
            parents = details.get("parent_inputs") or []
            parent_bits: list[str] = []
            for p in parents:
                pid = p.get("evidence_id")
                pe = evidence_by_id.get(str(pid)) if pid else None
                role = p.get("role") or "insumo"
                parent_bits.append(
                    f"{role}: {_evidence_label(pe, str(pid) if pid else None)} "
                    f"(SHA-256 {_short_hash(p.get('sha256'), 12)})"
                )
            if not parent_bits and details.get("parent_evidence_id"):
                pid = details.get("parent_evidence_id")
                pe = evidence_by_id.get(str(pid))
                parent_bits.append(f"insumo: {_evidence_label(pe, str(pid))}")

            intro = f"{actor} gerou o derivado «{out_name}» mediante {tech_label}"
            if proc:
                intro += f" ({proc})"
            intro += "."
            paragraphs.append(intro)
            if parent_bits:
                paragraphs.append("Insumos utilizados: " + "; ".join(parent_bits) + ".")
            param_lines = _format_params(details.get("parameters"))
            if param_lines:
                bullets.append("Parametros do procedimento:")
                bullets.extend(f"  · {line}" for line in param_lines)
            bullets.extend(
                [
                    f"Papel do artefato: {details.get('artifact_role') or '—'}",
                    f"SHA-256 do derivado: {rec.sha256_output or '—'}",
                    f"Hash dos parametros: {_short_hash(rec.sha256_params)}",
                ]
            )
            if rec.job_id:
                bullets.append(f"Job de analise: {rec.job_id}")

        elif rec.record_type == "evidence_deleted":
            fname = details.get("original_filename") or (ev.original_filename if ev else "evidencia")
            paragraphs.append(
                f"{actor} removeu a evidencia «{fname}» do caso (exclusao logica; registro permanece na cadeia)."
            )
            bullets.append(f"SHA-256 no momento da exclusao: {rec.sha256_input or '—'}")

        elif rec.record_type == "case_shared":
            who = details.get("shared_with_username") or details.get("shared_with_user_id")
            role = details.get("role", "—")
            paragraphs.append(
                f"{actor} compartilhou o caso com {who}, com permissao de {role}."
            )

        elif rec.record_type == "case_unshared":
            who = details.get("shared_with_username") or details.get("shared_with_user_id")
            paragraphs.append(f"{actor} revogou o compartilhamento com {who}.")

        elif rec.record_type == "case_closed":
            note = details.get("note")
            seq = details.get("closure_sequence")
            pending = details.get("pending_signers") or []
            if details.get("closure_mode") == "bilateral":
                text = f"{actor} iniciou o fechamento bilateral do caso"
                if seq is not None:
                    text += f" (rodada nº {seq})"
                text += "."
                if pending:
                    text += (
                        f" Aguardando assinatura de: {', '.join(str(p) for p in pending)}."
                    )
            else:
                text = f"{actor} encerrou o caso"
                if seq is not None:
                    text += f" (fechamento nº {seq})"
                text += "."
            if note:
                text += f" Observacao: {note}"
            paragraphs.append(text)
            if rec.sha256_output:
                bullets.append(f"Manifesto de fechamento (SHA-256): {rec.sha256_output}")

        elif rec.record_type == "case_reopened":
            paragraphs.append(f"{actor} reabriu o caso para continuidade das analises.")

        elif rec.record_type == "case_closure_signed":
            extra = details.get("additional_signature")
            if extra:
                paragraphs.append(f"{actor} adicionou assinatura complementar ao fechamento do caso.")
            else:
                paragraphs.append(
                    f"{actor} assinou digitalmente o manifesto de fechamento do caso (Ed25519)."
                )

        elif rec.record_type == "custody_signing_repair":
            n = details.get("records_resigned", "?")
            paragraphs.append(
                f"Operador do sistema ({actor}) reaplicou assinaturas Ed25519 em {n} registro(s) "
                f"apos estabilizacao da chave de assinatura ({details.get('reason', 'manutencao')}). "
                f"Os hashes da cadeia nao foram alterados."
            )

        elif rec.record_type in ("analysis_started", "analysis_completed", "analysis_failed"):
            paragraphs.append(
                f"{actor}: evento historico de analise ({rec.record_type}). "
                f"Consulte os derivados subsequentes para o rastro tecnico completo."
            )

        elif rec.record_type == "case_imported_peritus":
            paragraphs.append(
                f"{actor} importou o pacote nativo Peritus neste caso ForensicAuth."
            )
            paragraphs.append(
                "A ancora forense Peritus e o SHA-256 do peritusCase.xml; o ZIP original "
                "foi preservado para exportacao bit-identica."
            )
            bullets.extend(
                [
                    f"SHA-256 do ZIP: {details.get('original_zip_sha256') or rec.sha256_input or '—'}",
                    f"SHA-256 do XML (ancora): {details.get('peritus_chain_anchor') or rec.sha256_output or '—'}",
                    f"Evidencias no manifesto: {details.get('evidence_count', '—')}",
                    f"Derivados no manifesto: {details.get('derived_count', '—')}",
                ]
            )

        elif rec.record_type == "peritus_file_imported":
            fname = details.get("original_filename") or details.get("peritus_path") or "arquivo"
            folder = details.get("folder") or "—"
            kind = (
                "manifesto peritusCase.xml"
                if details.get("is_manifest")
                else "derivado Peritus"
                if details.get("is_derived")
                else "evidencia Peritus"
            )
            paragraphs.append(
                f"{actor} encadeou o arquivo Peritus «{fname}» ({kind}, pasta {folder}) "
                f"na cadeia de custodia do caso."
            )
            bullets.extend(
                [
                    f"Caminho no pacote: {details.get('peritus_path') or '—'}",
                    f"Tipo: {details.get('file_type') or '—'}",
                    f"SHA-256: {rec.sha256_output or '—'}",
                    f"Ancora XML do caso: {_short_hash(details.get('peritus_chain_anchor'), 16)}",
                ]
            )

        elif rec.record_type == "case_imported":
            origin = (details.get("source_origin") or {}) if details else {}
            paragraphs.append(
                f"{actor} importou este caso na instancia local a partir de um Verification Case Package (VCP) "
                f"(protocolo de origem: {details.get('source_protocol', '—')})."
            )
            if origin.get("hostname"):
                paragraphs.append(
                    f"Origem exportadora: {origin.get('hostname')} "
                    f"({origin.get('app_name', 'ForensicAuth')} {origin.get('app_version', '')})."
                )

        else:
            paragraphs.append(
                f"{actor} registrou o evento «{title}» na cadeia de custodia."
            )

        sig_ok = None
        if rec.system_signature and rec.record_hash:
            sig_ok = signing.verify_digest_hex(
                rec.record_hash, rec.system_signature, rec.signing_key_id
            )

        return {
            "sequence": rec.chain_sequence,
            "id": str(rec.id),
            "record_type": rec.record_type,
            "title": title,
            "timestamp": rec.timestamp.isoformat() if rec.timestamp else "",
            "timestamp_display": _fmt_ts(rec.timestamp),
            "actor": actor,
            "paragraphs": paragraphs,
            "bullets": bullets,
            "technical": {
                "record_hash": rec.record_hash,
                "previous_record_hash": rec.previous_record_hash,
                "system_signature": _short_hash(rec.system_signature, 24) if rec.system_signature else None,
                "signing_key_id": rec.signing_key_id,
                "signature_valid": sig_ok,
            },
        }

    def render_html(self, report: dict[str, Any]) -> str:
        case = report["case"]
        integrity = report["integrity"]
        stats = report["statistics"]
        events = report["events"]

        chain_badge = (
            '<span class="badge ok">Cadeia integra</span>'
            if integrity["chain_valid"]
            else '<span class="badge err">Cadeia com falha</span>'
        )
        forensic_badge = (
            '<span class="badge ok">Verificacao forense OK</span>'
            if integrity["forensic_valid"]
            else '<span class="badge warn">Verificacao forense com ressalvas</span>'
        )

        timeline_html = []
        for ev in events:
            bullets_html = ""
            if ev["bullets"]:
                items = "".join(f"<li>{html.escape(b)}</li>" for b in ev["bullets"])
                bullets_html = f"<ul class='detail-list'>{items}</ul>"
            paras = "".join(f"<p>{html.escape(p)}</p>" for p in ev["paragraphs"])
            sig = ev["technical"].get("signature_valid")
            sig_label = (
                "Assinatura Ed25519 valida"
                if sig is True
                else "Assinatura invalida ou ausente"
                if sig is False
                else "Sem assinatura"
            )
            sig_class = "ok" if sig is True else "warn" if sig is False else "muted"

            timeline_html.append(
                f"""
                <article class="event">
                  <div class="event-marker">
                    <span class="seq">{ev['sequence']}</span>
                  </div>
                  <div class="event-body">
                    <header>
                      <h3>{html.escape(ev['title'])}</h3>
                      <time>{html.escape(ev['timestamp_display'])}</time>
                    </header>
                    <div class="actor">Por <strong>{html.escape(ev['actor'])}</strong></div>
                    <div class="narrative">{paras}</div>
                    {bullets_html}
                    <details class="tech">
                      <summary>Detalhes tecnicos do elo</summary>
                      <dl>
                        <dt>ID do registro</dt><dd><code>{html.escape(ev['id'])}</code></dd>
                        <dt>Hash do registro</dt><dd><code>{html.escape(ev['technical']['record_hash'])}</code></dd>
                        <dt>Elo anterior</dt><dd><code>{html.escape(ev['technical']['previous_record_hash'] or '— (genesis)')}</code></dd>
                        <dt>Assinatura</dt><dd class="{sig_class}">{html.escape(sig_label)}</dd>
                      </dl>
                    </details>
                  </div>
                </article>
                """
            )

        desc_block = ""
        if case.get("description"):
            desc_block = f'<p class="case-desc">{html.escape(case["description"])}</p>'

        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Cadeia de custodia — {html.escape(case['protocol_number'])}</title>
  <style>
    :root {{
      --navy: #1a1a2e;
      --accent: #0369a1;
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --ok: #059669;
      --warn: #d97706;
      --err: #dc2626;
      --line: #e5e7eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.55;
    }}
    .hero {{
      background: linear-gradient(135deg, var(--navy) 0%, #16213e 100%);
      color: #fff; padding: 2rem 2.5rem 2.5rem;
    }}
    .hero h1 {{ margin: 0 0 0.35rem; font-size: 1.65rem; font-weight: 600; }}
    .hero .protocol {{ opacity: 0.9; font-size: 0.95rem; }}
    .hero .meta {{ margin-top: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }}
    .badge {{
      display: inline-block; padding: 0.25rem 0.65rem; border-radius: 999px;
      font-size: 0.75rem; font-weight: 600;
    }}
    .badge.ok {{ background: #d1fae5; color: #065f46; }}
    .badge.warn {{ background: #fef3c7; color: #92400e; }}
    .badge.err {{ background: #fee2e2; color: #991b1b; }}
    .wrap {{ max-width: 52rem; margin: 0 auto; padding: 1.5rem 1.25rem 3rem; }}
    .intro {{
      background: var(--card); border-radius: 10px; padding: 1.25rem 1.5rem;
      margin-bottom: 1.75rem; box-shadow: 0 1px 3px rgba(0,0,0,.06);
      border: 1px solid var(--line);
    }}
    .intro h2 {{ margin: 0 0 0.75rem; font-size: 1.1rem; color: var(--navy); }}
    .intro dl {{
      display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 1rem;
      margin: 0; font-size: 0.9rem;
    }}
    .intro dt {{ color: var(--muted); font-weight: 500; }}
    .case-desc {{ margin: 0.75rem 0 0; font-size: 0.9rem; color: var(--muted); }}
    .timeline-title {{
      font-size: 1.15rem; color: var(--navy); margin: 0 0 1.25rem;
      padding-bottom: 0.5rem; border-bottom: 2px solid var(--accent);
    }}
    .timeline {{ position: relative; padding-left: 0.5rem; }}
    .event {{
      display: flex; gap: 1rem; margin-bottom: 1.5rem; position: relative;
    }}
    .event::before {{
      content: ""; position: absolute; left: 1.15rem; top: 2.5rem; bottom: -1.5rem;
      width: 2px; background: var(--line);
    }}
    .event:last-child::before {{ display: none; }}
    .event-marker {{
      flex-shrink: 0; width: 2.3rem; text-align: center; z-index: 1;
    }}
    .event-marker .seq {{
      display: inline-flex; align-items: center; justify-content: center;
      width: 2.3rem; height: 2.3rem; border-radius: 50%;
      background: var(--accent); color: #fff; font-size: 0.8rem; font-weight: 700;
    }}
    .event-body {{
      flex: 1; background: var(--card); border-radius: 10px; padding: 1rem 1.25rem;
      border: 1px solid var(--line); box-shadow: 0 1px 2px rgba(0,0,0,.04);
    }}
    .event-body header {{
      display: flex; flex-wrap: wrap; justify-content: space-between;
      align-items: baseline; gap: 0.5rem; margin-bottom: 0.35rem;
    }}
    .event-body h3 {{ margin: 0; font-size: 1.05rem; color: var(--navy); }}
    .event-body time {{ font-size: 0.8rem; color: var(--muted); }}
    .actor {{ font-size: 0.85rem; color: var(--muted); margin-bottom: 0.5rem; }}
    .narrative p {{ margin: 0 0 0.5rem; }}
    .detail-list {{
      margin: 0.5rem 0 0; padding-left: 1.2rem; font-size: 0.85rem; color: #374151;
    }}
    .tech {{
      margin-top: 0.75rem; font-size: 0.8rem;
    }}
    .tech summary {{ cursor: pointer; color: var(--accent); font-weight: 500; }}
    .tech dl {{
      margin: 0.5rem 0 0; display: grid; grid-template-columns: 8rem 1fr; gap: 0.25rem;
    }}
    .tech dt {{ color: var(--muted); }}
    .tech code {{ font-size: 0.72rem; word-break: break-all; }}
    .tech .ok {{ color: var(--ok); }}
    .tech .warn {{ color: var(--warn); }}
    .footer {{
      margin-top: 2rem; font-size: 0.75rem; color: var(--muted); text-align: center;
    }}
    @media print {{
      body {{ background: #fff; }}
      .event-body {{ break-inside: avoid; }}
      .tech {{ display: block; }}
      .tech details {{ open: true; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="protocol">Protocolo {html.escape(case['protocol_number'])}</div>
    <h1>{html.escape(case['title'])}</h1>
    <div class="meta">{chain_badge} {forensic_badge}</div>
  </header>
  <main class="wrap">
    <section class="intro">
      <h2>Contexto do caso</h2>
      <dl>
        <dt>Identificador</dt><dd><code>{html.escape(case['id'])}</code></dd>
        <dt>Status</dt><dd>{html.escape(str(case.get('status', '—')))}</dd>
        <dt>Abertura</dt><dd>{html.escape(_fmt_ts(case.get('created_at')))}</dd>
        <dt>Responsavel</dt><dd>{html.escape(case.get('creator_username') or '—')}</dd>
        <dt>Inquerito / processo</dt><dd>{html.escape(case.get('inquiry_number') or '—')} / {html.escape(case.get('process_number') or '—')}</dd>
        <dt>Eventos na cadeia</dt><dd>{stats['custody_events']} registro(s) · {stats['evidences_active']} evidencia(s) ativa(s)</dd>
        <dt>Chave de assinatura</dt><dd>{html.escape(integrity.get('signing_key_id') or '—')}</dd>
        <dt>Relatorio gerado em</dt><dd>{html.escape(_fmt_ts(report.get('generated_at')))}</dd>
      </dl>
      {desc_block}
      <p style="margin:1rem 0 0;font-size:0.9rem;">
        A narrativa abaixo segue a ordem cronologica da cadeia criptografica (elo 1 ao {stats['custody_events']}).
        Cada evento encadeia o hash do registro anterior, garantindo deteccao de alteracao posterior.
      </p>
    </section>
    <h2 class="timeline-title">Linha do tempo — do inicio ao estado atual</h2>
    <div class="timeline">
      {''.join(timeline_html)}
    </div>
    <p class="footer">ForensicAuth — Relatorio narrativo de cadeia de custodia. Documento gerado automaticamente; preserve o JSON de verificacao forense para auditoria tecnica complementar.</p>
  </main>
</body>
</html>"""

    def render_markdown(self, report: dict[str, Any]) -> str:
        case = report["case"]
        integrity = report["integrity"]
        lines = [
            f"# Cadeia de custodia — {case['protocol_number']}",
            "",
            f"**{case['title']}**",
            "",
            f"- **Status:** {case.get('status', '—')}",
            f"- **Aberto em:** {_fmt_ts(case.get('created_at'))}",
            f"- **Responsavel:** {case.get('creator_username') or '—'}",
            f"- **Cadeia:** {'integra' if integrity['chain_valid'] else 'COM FALHA'}",
            f"- **Forense:** {'OK' if integrity['forensic_valid'] else 'com ressalvas'}",
            f"- **Gerado em:** {_fmt_ts(report.get('generated_at'))}",
            "",
        ]
        if case.get("description"):
            lines.extend([case["description"], ""])

        lines.extend(
            [
                "## Linha do tempo",
                "",
                "Narrativa em ordem cronologica da cadeia (do primeiro ao ultimo elo).",
                "",
            ]
        )

        for ev in report["events"]:
            lines.append(f"### {ev['sequence']}. {ev['title']}")
            lines.append(f"*{ev['timestamp_display']} — {ev['actor']}*")
            lines.append("")
            for p in ev["paragraphs"]:
                lines.append(p)
                lines.append("")
            for b in ev["bullets"]:
                lines.append(f"- {b}")
            if ev["bullets"]:
                lines.append("")
            tech = ev["technical"]
            lines.append(
                f"> Elo `{ev['id'][:8]}…` · hash `{_short_hash(tech['record_hash'], 10)}`"
            )
            lines.append("")

        lines.append("---")
        lines.append("*ForensicAuth — relatorio narrativo de cadeia de custodia*")
        return "\n".join(lines)

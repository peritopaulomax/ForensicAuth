#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdfsig_forense.py — Análise forense de assinaturas digitais em PDF (PAdES/CAdES),
com ênfase em ICP-Brasil, produzindo relatório humanizado em Markdown.

Integrado ao ForensicAuth: o pipeline chama `analyze_pdf_file`.

Uso básico:
    python3 pdfsig_forense.py documento.pdf
    python3 pdfsig_forense.py documento.pdf -o relatorio.md --json dados.json

Dependências:
    pip install pyhanko asn1crypto cryptography

O script é 100%% offline por padrão (não consulta rede). Use --fetch para
permitir download de intermediárias/LCR/OCSP durante a validação de caminho.

Licença: uso livre. Fornecido "como está", sem garantia.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import logging
import os
import re
import sys
import textwrap
import traceback
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------------------
# Dependências externas
# ----------------------------------------------------------------------------
try:
    from asn1crypto import cms, core, crl as asn1crl, ocsp as asn1ocsp, tsp, x509
except ImportError:  # pragma: no cover
    sys.exit("Falta a biblioteca asn1crypto. Instale: pip install asn1crypto")

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes as chashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils as asym_utils
    from cryptography.hazmat.primitives.serialization import load_der_public_key
except ImportError:  # pragma: no cover
    sys.exit("Falta a biblioteca cryptography. Instale: pip install cryptography")

try:
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.diff_analysis import DEFAULT_DIFF_POLICY
    from pyhanko.sign.validation.settings import KeyUsageConstraints  # noqa: F401
    from pyhanko_certvalidator import CertificateValidator, ValidationContext
except ImportError:  # pragma: no cover
    sys.exit("Falta a biblioteca pyHanko. Instale: pip install pyhanko")

VERSION = "1.4"

# A varredura histórica consulta objetos que podem não existir em revisões
# antigas; o pyHanko registra isso como aviso. É esperado, e poluiria o console.
logging.getLogger("pyhanko").setLevel(logging.ERROR)
logging.getLogger("pyhanko_certvalidator").setLevel(logging.ERROR)

# ----------------------------------------------------------------------------
# Tabelas de OIDs
# ----------------------------------------------------------------------------

# subjectAltName / otherName da ICP-Brasil (DOC-ICP-04).
# 'sensivel' marca campos que carregam CPF/RG/NIS e são redigidos por padrão.
ICPBR_SAN_OIDS = {
    "2.16.76.1.3.1": ("Dados do titular PF (nascimento+CPF+NIS+RG)", True),
    "2.16.76.1.3.2": ("Nome do responsável pelo certificado PJ", False),
    "2.16.76.1.3.3": ("CNPJ da pessoa jurídica", False),
    "2.16.76.1.3.4": ("Dados do responsável PJ (nascimento+CPF+NIS+RG)", True),
    "2.16.76.1.3.5": ("Dados de título de eleitor", True),
    "2.16.76.1.3.6": ("INSS/CEI da pessoa física", True),
    "2.16.76.1.3.7": ("CEI da pessoa jurídica", False),
    "2.16.76.1.3.8": ("Nome empresarial", False),
}

# Arcos de política de certificado da ICP-Brasil (leitura aproximada do prefixo).
ICPBR_POLICY_ARCS = [
    ("2.16.76.1.2.1.", "Certificado de assinatura tipo A1 (ICP-Brasil)"),
    ("2.16.76.1.2.2.", "Certificado de assinatura tipo A2 (ICP-Brasil)"),
    ("2.16.76.1.2.3.", "Certificado de assinatura tipo A3 (ICP-Brasil)"),
    ("2.16.76.1.2.4.", "Certificado de assinatura tipo A4 (ICP-Brasil)"),
    ("2.16.76.1.2.101.", "Certificado de sigilo tipo S1 (ICP-Brasil)"),
    ("2.16.76.1.2.102.", "Certificado de sigilo tipo S2 (ICP-Brasil)"),
    ("2.16.76.1.2.103.", "Certificado de sigilo tipo S3 (ICP-Brasil)"),
    ("2.16.76.1.2.104.", "Certificado de sigilo tipo S4 (ICP-Brasil)"),
    ("2.16.76.1.6.", "Política de Carimbo do Tempo (ICP-Brasil)"),
    ("2.16.76.3.", "Assinatura eletrônica AVANÇADA gov.br — hierarquia do Governo "
                   "Federal, distinta da ICP-Brasil"),
    ("2.16.76.1.", "Política ICP-Brasil (arco não mapeado por este script)"),
]

# Extensões proprietárias encontradas dentro de TSTInfo na ICP-Brasil.
TST_EXT_HINTS = {
    "1.3.6.1.4.1.44588": "Arco ITI/ICP-Brasil — Declaração de Sincronismo da "
                         "Entidade de Auditoria do Tempo (EAT)",
}

SEVERITY_ORDER = {"CRITICO": 0, "ALERTA": 1, "ATENCAO": 2, "OK": 3, "INFO": 4}
SEVERITY_LABEL = {
    "CRITICO": "Verificações com resultado negativo",
    "ALERTA": "Divergências em relação à especificação",
    "ATENCAO": "Elementos ausentes ou não apurados",
    "OK": "Verificações com resultado positivo",
    "INFO": "Constatações estruturais",
}

# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------

def fp(cert: x509.Certificate, algo: str = "sha256") -> str:
    return getattr(cert, algo).hex().upper()

def dn(name) -> str:
    """Distinguished Name legível, em ordem estável."""
    try:
        return name.human_friendly
    except Exception:
        return str(name.native)

def cn_of(cert: x509.Certificate) -> str:
    try:
        v = cert.subject.native.get("common_name")
        if isinstance(v, list):
            v = v[0]
        return v or dn(cert.subject)
    except Exception:
        return "<sem CN>"

def fmt_dt(dt: Optional[datetime.datetime], tz_offset_hours: Optional[float] = None) -> str:
    if dt is None:
        return "—"
    base = dt.astimezone(datetime.timezone.utc)
    out = base.strftime("%d/%m/%Y %H:%M:%S")
    if base.microsecond:
        out += f",{base.microsecond // 1000:03d}"
    out += " UTC"
    if tz_offset_hours is not None:
        loc = base + datetime.timedelta(hours=tz_offset_hours)
        sign = "+" if tz_offset_hours >= 0 else "-"
        out += (f" ({loc.strftime('%d/%m/%Y %H:%M:%S')} UTC{sign}"
                f"{abs(int(tz_offset_hours)):02d})")
    return out

def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}".replace(",", ".") if unit == "B" else f"{n / 1:,.1f} {unit}".replace(",", ".")
        n /= 1024.0
    return str(n)

def human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.2f} MB"

def thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")

def redact_digits(s: str, keep_head: int = 0) -> str:
    out = []
    for i, ch in enumerate(s):
        if ch.isdigit() and i >= keep_head:
            out.append("•")
        else:
            out.append(ch)
    return "".join(out)

def policy_meaning(oid: str) -> Optional[str]:
    for prefix, label in ICPBR_POLICY_ARCS:
        if oid.startswith(prefix):
            return label
    return None

def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default

# ----------------------------------------------------------------------------
# Achados
# ----------------------------------------------------------------------------

@dataclass
class Finding:
    severity: str          # CRITICO | ALERTA | ATENCAO | OK | INFO
    code: str
    title: str
    detail: str = ""
    scope: str = "documento"

    def as_dict(self) -> dict:
        return {
            "severity": self.severity, "code": self.code, "title": self.title,
            "detail": self.detail, "scope": self.scope,
        }

# ----------------------------------------------------------------------------
# Verificação criptográfica genérica
# ----------------------------------------------------------------------------

HASHES = {
    "md5": chashes.MD5, "sha1": chashes.SHA1, "sha224": chashes.SHA224,
    "sha256": chashes.SHA256, "sha384": chashes.SHA384, "sha512": chashes.SHA512,
    "sha3_256": chashes.SHA3_256, "sha3_384": chashes.SHA3_384,
    "sha3_512": chashes.SHA3_512,
}

WEAK_HASHES = {"md5", "sha1"}

def algo_label(name: Optional[str]) -> str:
    """'sha256' -> 'SHA-256'; 'sha3_512' -> 'SHA3-512'."""
    if not name:
        return "—"
    n = name.lower().replace("-", "_")
    if n.startswith("sha3_"):
        return "SHA3-" + n[5:]
    if n.startswith("sha") and n[3:].isdigit():
        return "SHA-" + n[3:]
    return name.upper()

def digest_bytes(data: bytes, algo: str) -> bytes:
    algo = algo.replace("-", "_")
    h = hashlib.new({"sha3_256": "sha3_256", "sha3_384": "sha3_384",
                     "sha3_512": "sha3_512"}.get(algo, algo))
    h.update(data)
    return h.digest()

def verify_raw_signature(pubkey_der: bytes, signature: bytes, signed_bytes: bytes,
                         sig_algo, fallback_hash: Optional[str] = None
                         ) -> Tuple[bool, str]:
    """
    Verifica assinatura RSA (PKCS#1 v1.5 ou PSS), ECDSA ou DSA.

    Em CMS é comum o signatureAlgorithm ser apenas 'rsaEncryption', sem indicar a
    função de hash — que nesse caso vem do campo digestAlgorithm do SignerInfo.
    É para isso que serve fallback_hash.
    """
    try:
        pub = load_der_public_key(pubkey_der)
    except Exception as e:
        return False, f"não foi possível carregar a chave pública: {e}"

    try:
        algo_family = sig_algo.signature_algo
    except Exception as e:
        return False, f"algoritmo de assinatura não reconhecido: {e}"
    hash_name = safe(lambda: sig_algo.hash_algo) or fallback_hash
    if hash_name is None:
        return False, ("não foi possível determinar a função de hash da assinatura")

    hcls = HASHES.get((hash_name or "").replace("-", "_"))
    if hcls is None:
        return False, f"função de hash não suportada: {hash_name}"

    try:
        if algo_family == "rsassa_pkcs1v15":
            pub.verify(signature, signed_bytes, padding.PKCS1v15(), hcls())
        elif algo_family == "rsassa_pss":
            params = sig_algo["parameters"]
            salt_len = safe(lambda: params["salt_length"].native, hcls.digest_size)
            pub.verify(
                signature, signed_bytes,
                padding.PSS(mgf=padding.MGF1(hcls()), salt_length=salt_len),
                hcls(),
            )
        elif algo_family == "ecdsa":
            pub.verify(signature, signed_bytes, ec.ECDSA(hcls()))
        elif algo_family == "dsa":
            pub.verify(signature, signed_bytes, hcls())
        else:
            return False, f"família de algoritmo não suportada: {algo_family}"
        return True, f"{algo_family} / {hash_name}"
    except InvalidSignature:
        return False, "assinatura matematicamente INVÁLIDA"
    except Exception as e:
        return False, f"erro na verificação: {e}"

def verify_cert_signature(child: x509.Certificate,
                          parent: x509.Certificate) -> Tuple[bool, str]:
    return verify_raw_signature(
        parent.public_key.dump(), child["signature_value"].native,
        child["tbs_certificate"].dump(), child["signature_algorithm"],
    )

def verify_crl_signature(crl_obj: asn1crl.CertificateList,
                         issuer: x509.Certificate) -> Tuple[bool, str]:
    return verify_raw_signature(
        issuer.public_key.dump(), crl_obj["signature"].native,
        crl_obj["tbs_cert_list"].dump(), crl_obj["signature_algorithm"],
    )

def key_description(cert: x509.Certificate) -> str:
    try:
        algo = cert.public_key.algorithm
        bits = cert.public_key.bit_size
        if algo == "ec":
            curve = safe(lambda: cert.public_key.curve, "?")
            return f"EC {bits} bits (curva {curve})"
        return f"{algo.upper()} {bits} bits"
    except Exception:
        return "?"

# ----------------------------------------------------------------------------
# Coleta de material criptográfico espalhado pelo arquivo
# ----------------------------------------------------------------------------

@dataclass
class Harvest:
    """Todos os certificados, LCRs e respostas OCSP encontrados no arquivo."""
    certs: Dict[bytes, x509.Certificate] = dc_field(default_factory=dict)
    crls: Dict[bytes, asn1crl.CertificateList] = dc_field(default_factory=dict)
    ocsps: Dict[bytes, Any] = dc_field(default_factory=dict)
    origins: Dict[bytes, List[str]] = dc_field(default_factory=dict)

    def _note(self, key: bytes, origin: str):
        self.origins.setdefault(key, [])
        if origin not in self.origins[key]:
            self.origins[key].append(origin)

    def add_cert(self, cert: x509.Certificate, origin: str):
        k = cert.sha256
        self.certs.setdefault(k, cert)
        self._note(k, origin)

    def add_crl(self, obj: asn1crl.CertificateList, origin: str):
        k = hashlib.sha256(obj.dump()).digest()
        self.crls.setdefault(k, obj)
        self._note(k, origin)

    def add_ocsp(self, obj, origin: str):
        k = hashlib.sha256(obj.dump()).digest()
        self.ocsps.setdefault(k, obj)
        self._note(k, origin)

    def cert_origin(self, cert: x509.Certificate) -> str:
        return ", ".join(self.origins.get(cert.sha256, ["?"]))

    def crl_origin(self, obj) -> str:
        return ", ".join(self.origins.get(hashlib.sha256(obj.dump()).digest(), ["?"]))

    @property
    def cert_list(self) -> List[x509.Certificate]:
        return list(self.certs.values())

    @property
    def crl_list(self) -> List[asn1crl.CertificateList]:
        return list(self.crls.values())

def try_parse_der(blob: bytes, harvest: Harvest, origin: str) -> bool:
    """Tenta interpretar um blob como certificado, LCR ou resposta OCSP."""
    if not blob or len(blob) < 64 or blob[0] != 0x30:
        return False
    for loader, adder in (
        (x509.Certificate.load, harvest.add_cert),
        (asn1crl.CertificateList.load, harvest.add_crl),
        (asn1ocsp.OCSPResponse.load, harvest.add_ocsp),
        (asn1ocsp.BasicOCSPResponse.load, harvest.add_ocsp),
    ):
        try:
            obj = loader(blob)
            # força o parse completo para descartar falsos positivos
            obj.native
            adder(obj, origin)
            return True
        except Exception:
            continue
    return False

def harvest_from_pdf(reader: PdfFileReader, max_obj_scan: int = 100000) -> Harvest:
    """
    Varre TODOS os objetos de TODAS as revisões procurando certificados, LCRs e
    respostas OCSP em DER — inclusive objetos órfãos (desreferenciados por
    revisões incrementais posteriores), que validadores comuns não veem.
    """
    h = Harvest()
    seen_refs = set()
    total_revs = reader.xrefs.total_revisions
    for rev in range(total_revs):
        try:
            refs = list(reader.xrefs.explicit_refs_in_revision(rev))
        except Exception:
            continue
        for ref in refs:
            key = (ref.idnum, ref.generation, rev)
            if key in seen_refs or len(seen_refs) > max_obj_scan:
                continue
            seen_refs.add(key)
            obj = safe(lambda: reader.get_object(ref, revision=rev))
            if obj is None:
                continue
            data = None
            if isinstance(obj, generic.StreamObject):
                data = safe(lambda: obj.data)
            elif isinstance(obj, generic.ByteStringObject):
                data = bytes(obj)
            if data:
                origin = f"objeto {ref.idnum} (rev. {rev + 1})"
                try_parse_der(data, h, origin)
    return h

def harvest_from_cms(signed_data: cms.SignedData, harvest: Harvest, label: str):
    """Certificados, LCRs e revinfo embutidos no próprio CMS."""
    for c in signed_data["certificates"] or []:
        if c.name == "certificate":
            harvest.add_cert(c.chosen, f"CMS de {label}")
    revs = signed_data["crls"]
    if revs is not None and not isinstance(revs, core.Void):
        for r in revs:
            try:
                if r.name == "crl":
                    harvest.add_crl(r.chosen, f"CMS de {label} (campo crls)")
                elif r.name == "other":
                    other = r.chosen
                    if other["other_rev_info_format"].native == "ocsp_response":
                        harvest.add_ocsp(other["other_rev_info"], f"CMS de {label}")
            except Exception:
                continue

def harvest_from_revinfo_attr(signer_info: cms.SignerInfo, harvest: Harvest, label: str):
    """Atributo adbe-revocationInfoArchival (1.2.840.113583.1.1.8)."""
    attrs = signer_info["unsigned_attrs"]
    if attrs is None or isinstance(attrs, core.Void):
        return
    for attr in attrs:
        oid = safe(lambda: attr["type"].dotted, "")
        if oid != "1.2.840.113583.1.1.8":
            continue
        for val in attr["values"]:
            raw = safe(lambda: val.dump())
            if not raw:
                continue
            # estrutura: SEQUENCE { [0] crls, [1] ocsps, [2] otherRevInfo }
            try:
                seq = core.Sequence.load(raw)
            except Exception:
                continue
            for child in safe(lambda: list(_iter_any(raw)), []) or []:
                try_parse_der(child, harvest, f"adbe-revocationInfoArchival de {label}")

class _AnySeq(core.SequenceOf):
    _child_spec = core.Any

def _iter_any(raw: bytes) -> List[bytes]:
    """Extrai recursivamente sub-estruturas DER de nível 1 e 2."""
    out: List[bytes] = []

    def walk(blob: bytes, depth: int):
        if depth > 3:
            return
        try:
            seq = _AnySeq.load(blob)
        except Exception:
            return
        for child in seq:
            d = safe(lambda: child.dump())
            if not d:
                continue
            out.append(d)
            walk(d, depth + 1)
            inner = safe(lambda: child.contents)
            if inner:
                out.append(inner)

    walk(raw, 0)
    return out

# ----------------------------------------------------------------------------
# Descrição de certificados
# ----------------------------------------------------------------------------

@dataclass
class CertReport:
    cert: x509.Certificate
    role: str = ""
    findings: List[Finding] = dc_field(default_factory=list)
    info: Dict[str, Any] = dc_field(default_factory=dict)

def describe_cert(cert: x509.Certificate, redact: bool = True) -> Dict[str, Any]:
    tbs = cert["tbs_certificate"]
    d: Dict[str, Any] = {
        "subject": dn(cert.subject),
        "cn": cn_of(cert),
        "issuer": dn(cert.issuer),
        "serial_hex": f"0x{cert.serial_number:X}",
        "serial_dec": str(cert.serial_number),
        "not_before": tbs["validity"]["not_before"].native,
        "not_after": tbs["validity"]["not_after"].native,
        "key": key_description(cert),
        "sig_algo": safe(lambda: tbs["signature"]["algorithm"].native, "?"),
        "sha256": fp(cert, "sha256"),
        "sha1": fp(cert, "sha1"),
        "is_ca": bool(cert.ca),
        "self_signed": cert.self_signed,
        "key_usage": sorted(cert.key_usage_value.native) if cert.key_usage_value else [],
        "eku": sorted(cert.extended_key_usage_value.native) if safe(
            lambda: cert.extended_key_usage_value) else [],
        "crl_urls": list(cert.crl_distribution_points_value.native) if False else [],
        "ocsp_urls": list(safe(lambda: cert.ocsp_urls, []) or []),
        "policies": [],
        "san_icpbr": [],
        "san_other": [],
        "aia": [],
    }

    # CRL DPs
    urls: List[str] = []
    try:
        for dp in (cert.crl_distribution_points_value or []):
            for u in (dp["distribution_point"].native or []):
                if isinstance(u, str):
                    urls.append(u)
    except Exception:
        pass
    d["crl_urls"] = urls

    # AIA
    try:
        for entry in (cert.authority_information_access_value or []):
            d["aia"].append(f"{entry['access_method'].native}: "
                            f"{entry['access_location'].native}")
    except Exception:
        pass

    # Políticas
    try:
        for pol in (cert.certificate_policies_value or []):
            oid = pol["policy_identifier"].dotted
            cps = None
            for q in (pol["policy_qualifiers"] or []):
                if q["policy_qualifier_id"].native == "certification_practice_statement":
                    cps = q["qualifier"].native
            d["policies"].append({"oid": oid, "meaning": policy_meaning(oid), "cps": cps})
    except Exception:
        pass

    # subjectAltName (com atenção aos otherName da ICP-Brasil)
    try:
        san = cert.subject_alt_name_value
        if san is not None:
            for gn in san:
                if gn.name == "other_name":
                    oid = gn.chosen["type_id"].dotted
                    val = safe(lambda: gn.chosen["value"].native, None)
                    if isinstance(val, bytes):
                        val = safe(lambda: core.load(val).native, val.hex())
                    val = "" if val is None else str(val)
                    label, sensitive = ICPBR_SAN_OIDS.get(oid, (None, True))
                    shown = redact_digits(val) if (sensitive and redact) else val
                    d["san_icpbr"].append({
                        "oid": oid, "label": label or "otherName não mapeado",
                        "value": shown, "sensitive": sensitive,
                    })
                else:
                    d["san_other"].append(f"{gn.name}: {gn.native}")
    except Exception:
        pass

    return d

def cert_time_findings(cert: x509.Certificate, role: str,
                       moment: Optional[datetime.datetime]) -> List[Finding]:
    out: List[Finding] = []
    tbs = cert["tbs_certificate"]["validity"]
    nb, na = tbs["not_before"].native, tbs["not_after"].native
    if moment is not None:
        if moment < nb:
            out.append(Finding("CRITICO", "CERT_NOT_YET_VALID",
                               f"{role}: certificado ainda não era válido no instante de referência",
                               f"Início da validade: {fmt_dt(nb)}; referência: {fmt_dt(moment)}."))
        elif moment > na:
            out.append(Finding("CRITICO", "CERT_EXPIRED_AT_SIGNING",
                               f"{role}: certificado já estava expirado no instante de referência",
                               f"Fim da validade: {fmt_dt(na)}; referência: {fmt_dt(moment)}."))
        else:
            out.append(Finding("OK", "CERT_VALID_AT_MOMENT",
                               f"{role}: certificado vigente no instante de referência",
                               f"Validade {fmt_dt(nb)} → {fmt_dt(na)}."))
    now = datetime.datetime.now(datetime.timezone.utc)
    if na < now:
        out.append(Finding("INFO", "CERT_EXPIRED_NOW",
                           f"{role}: certificado expirado na data desta análise",
                           f"Fim da validade: {fmt_dt(na)}."))
    # Robustez de chave
    try:
        if cert.public_key.algorithm == "rsa" and cert.public_key.bit_size < 2048:
            out.append(Finding("ALERTA", "WEAK_KEY",
                               f"{role}: chave RSA de {cert.public_key.bit_size} bits",
                               "Inferior aos 2048 bits exigidos pela ETSI TS 119 312."))
    except Exception:
        pass
    halgo = safe(lambda: cert["signature_algorithm"].hash_algo, "")
    if halgo in WEAK_HASHES:
        out.append(Finding("ALERTA", "WEAK_CERT_HASH",
                           f"{role}: certificado emitido com {algo_label(halgo)}",
                           "Função não admitida pela ETSI TS 119 312 para assinatura "
                           "de certificados."))
    return out

# ----------------------------------------------------------------------------
# Cadeia de certificação
# ----------------------------------------------------------------------------

@dataclass
class ChainLink:
    child: x509.Certificate
    issuer: Optional[x509.Certificate]
    verified: Optional[bool]
    note: str = ""

def build_chain(leaf: x509.Certificate,
                pool: Sequence[x509.Certificate]) -> Tuple[List[x509.Certificate], List[ChainLink], List[Finding]]:
    """Monta a cadeia do folha até a raiz usando o material disponível."""
    by_subject: Dict[bytes, List[x509.Certificate]] = {}
    for c in pool:
        by_subject.setdefault(c.subject.dump(), []).append(c)

    chain = [leaf]
    links: List[ChainLink] = []
    findings: List[Finding] = []
    current = leaf
    seen = {current.sha256}

    while True:
        if current.self_signed in ("yes", "maybe") and current.subject.dump() == current.issuer.dump():
            ok, note = verify_cert_signature(current, current)
            links.append(ChainLink(current, current, ok,
                                   "âncora autoassinada" + ("" if ok else f" — {note}")))
            break
        candidates = by_subject.get(current.issuer.dump(), [])
        parent = None
        for cand in candidates:
            ok, _ = verify_cert_signature(current, cand)
            if ok:
                parent = cand
                break
        if parent is None:
            if candidates:
                parent = candidates[0]
                links.append(ChainLink(current, parent, False,
                                       "emissor encontrado, mas a assinatura NÃO confere"))
                findings.append(Finding(
                    "CRITICO", "CHAIN_BROKEN",
                    f"Vínculo não verificado: {cn_of(current)} ← {cn_of(parent)}",
                    "A assinatura do certificado não confere com a chave pública do emissor "
                    "encontrado no arquivo."))
            else:
                links.append(ChainLink(current, None, None,
                                       "certificado emissor NÃO está presente no arquivo"))
                findings.append(Finding(
                    "ALERTA", "CHAIN_INCOMPLETE",
                    f"Cadeia incompleta no arquivo: falta o emissor de {cn_of(current)}",
                    f"Emissor requerido: {dn(current.issuer)}. O certificado não consta "
                    f"em nenhum objeto do arquivo."))
            break
        links.append(ChainLink(current, parent, True))
        if parent.sha256 in seen:
            findings.append(Finding("ALERTA", "CHAIN_LOOP",
                                    "Laço na cadeia de certificação", ""))
            break
        seen.add(parent.sha256)
        chain.append(parent)
        current = parent

    return chain, links, findings

def validate_path(cert: x509.Certificate, pool: Sequence[x509.Certificate],
                  crls: Sequence[asn1crl.CertificateList],
                  ocsps: Sequence[Any],
                  anchors: Sequence[x509.Certificate],
                  moment: Optional[datetime.datetime],
                  revocation_mode: str, allow_fetching: bool) -> Tuple[bool, str]:
    if not anchors:
        return False, "nenhuma âncora de confiança disponível"
    try:
        vc = ValidationContext(
            trust_roots=list(anchors), other_certs=list(pool), crls=list(crls),
            ocsps=list(ocsps), allow_fetching=allow_fetching,
            revocation_mode=revocation_mode, moment=moment,
        )
        validator = CertificateValidator(cert, intermediate_certs=list(pool),
                                         validation_context=vc)
        path = asyncio.run(validator.async_validate_usage(set()))
        length = len(path[0]) if isinstance(path, tuple) else len(path)
        return True, f"caminho válido, {length} níveis"
    except Exception as e:
        msg = str(e).strip().replace("\n", " ")
        return False, f"{type(e).__name__}: {msg[:400]}"

def revocation_status(cert: x509.Certificate,
                      crls: Sequence[asn1crl.CertificateList],
                      moment: Optional[datetime.datetime]) -> Dict[str, Any]:
    """Verifica o número de série do certificado nas LCRs cujo emissor coincide."""
    result = {"checked": False, "revoked": False, "matching_crls": [],
              "revocation_date": None, "reason": None, "fresh": None}
    for c in crls:
        tbs = c["tbs_cert_list"]
        if tbs["issuer"].dump() != cert.issuer.dump():
            continue
        result["checked"] = True
        this_u = tbs["this_update"].native
        next_u = safe(lambda: tbs["next_update"].native)
        fresh = None
        if moment is not None and next_u is not None:
            fresh = this_u <= moment <= next_u
        result["matching_crls"].append({
            "issuer": dn(tbs["issuer"]), "this_update": this_u, "next_update": next_u,
            "entries": len(tbs["revoked_certificates"] or []),
            "fresh_at_moment": fresh,
            "size": len(c.dump()),
        })
        if fresh:
            result["fresh"] = True
        elif result["fresh"] is None:
            result["fresh"] = fresh
        for entry in (tbs["revoked_certificates"] or []):
            if entry["user_certificate"].native == cert.serial_number:
                result["revoked"] = True
                result["revocation_date"] = entry["revocation_date"].native
                for ext in (entry["crl_entry_extensions"] or []):
                    if ext["extn_id"].native == "crl_reason":
                        result["reason"] = safe(lambda: ext["extn_value"].parsed.native)
    return result

# ----------------------------------------------------------------------------
# Carimbos de tempo
# ----------------------------------------------------------------------------

@dataclass
class TimestampReport:
    kind: str                     # "signature-time-stamp" | "DocTimeStamp" | "content-time-stamp"
    gen_time: Optional[datetime.datetime] = None
    policy: Optional[str] = None
    serial: Optional[str] = None
    imprint_algo: Optional[str] = None
    accuracy: Optional[str] = None
    nonce: Optional[str] = None
    tsa_name: Optional[str] = None
    tsa_cert: Optional[x509.Certificate] = None
    imprint_matches: Optional[bool] = None
    imprint_target: str = ""
    sig_ok: Optional[bool] = None
    sig_note: str = ""
    eku_ok: Optional[bool] = None
    extensions: List[Dict[str, Any]] = dc_field(default_factory=list)
    findings: List[Finding] = dc_field(default_factory=list)
    chain: List[x509.Certificate] = dc_field(default_factory=list)
    chain_links: List[ChainLink] = dc_field(default_factory=list)
    path_results: Dict[str, str] = dc_field(default_factory=dict)
    revocation: Dict[str, Any] = dc_field(default_factory=dict)

def fmt_accuracy(acc) -> Optional[str]:
    if acc is None:
        return None
    try:
        n = acc.native or {}
    except Exception:
        return None
    parts = []
    if n.get("seconds"):
        parts.append(f"{n['seconds']} s")
    if n.get("millis"):
        parts.append(f"{n['millis']} ms")
    if n.get("micros"):
        parts.append(f"{n['micros']} µs")
    return "± " + " ".join(parts) if parts else None

def analyze_tst(tst: cms.ContentInfo, kind: str, imprint_target_bytes: bytes,
                imprint_target_label: str, harvest: Harvest) -> TimestampReport:
    rep = TimestampReport(kind=kind, imprint_target=imprint_target_label)
    sd = tst["content"]
    harvest_from_cms(sd, harvest, f"carimbo de tempo ({kind})")

    try:
        tstinfo = sd["encap_content_info"]["content"].parsed
    except Exception as e:
        rep.findings.append(Finding("CRITICO", "TST_UNPARSEABLE",
                                    "Não foi possível interpretar o TSTInfo do carimbo",
                                    str(e)))
        return rep

    rep.gen_time = safe(lambda: tstinfo["gen_time"].native)
    rep.policy = safe(lambda: tstinfo["policy"].dotted)
    rep.serial = safe(lambda: str(tstinfo["serial_number"].native))
    rep.imprint_algo = safe(
        lambda: tstinfo["message_imprint"]["hash_algorithm"]["algorithm"].native)
    rep.accuracy = fmt_accuracy(safe(lambda: tstinfo["accuracy"]))
    nonce = safe(lambda: tstinfo["nonce"].native)
    rep.nonce = None if nonce is None else hex(nonce)
    rep.tsa_name = safe(lambda: dn(tstinfo["tsa"].chosen)) if safe(
        lambda: tstinfo["tsa"]) else None

    # extensões proprietárias (ex.: sincronismo ICP-Brasil)
    for ext in (safe(lambda: tstinfo["extensions"], None) or []):
        oid = safe(lambda: ext["extn_id"].dotted, "?")
        hint = None
        for arc, label in TST_EXT_HINTS.items():
            if oid.startswith(arc):
                hint = label
        raw = safe(lambda: ext["extn_value"].native, b"") or b""
        details = describe_sync_declaration(raw) if hint else None
        rep.extensions.append({"oid": oid, "hint": hint,
                               "size": len(raw), "details": details})

    # o carimbo cobre realmente o alvo?
    imp = safe(lambda: tstinfo["message_imprint"]["hashed_message"].native)
    if imp is not None and rep.imprint_algo:
        calc = safe(lambda: digest_bytes(imprint_target_bytes, rep.imprint_algo))
        rep.imprint_matches = (calc == imp)
        if rep.imprint_matches:
            rep.findings.append(Finding(
                "OK", "TST_IMPRINT_MATCH",
                "O messageImprint do carimbo corresponde ao alvo",
                f"{algo_label(rep.imprint_algo)} de {imprint_target_label} confere com o "
                f"messageImprint do token."))
        else:
            rep.findings.append(Finding(
                "CRITICO", "TST_IMPRINT_MISMATCH",
                "O messageImprint do carimbo não corresponde ao alvo",
                f"O messageImprint não é o {algo_label(rep.imprint_algo)} de "
                f"{imprint_target_label}."))
        if rep.imprint_algo.replace("-", "_") in WEAK_HASHES:
            rep.findings.append(Finding("ALERTA", "TST_WEAK_IMPRINT",
                                        f"messageImprint do carimbo calculado com {algo_label(rep.imprint_algo)}",
                                        "Função não admitida pela ETSI TS 119 312."))

    # assinatura do próprio token
    tsi = sd["signer_infos"][0]
    tsa_cert = pick_signer_cert(sd, tsi)
    rep.tsa_cert = tsa_cert
    if tsa_cert is not None:
        signed_bytes = cms_signed_bytes(sd, tsi)
        ok, note = verify_raw_signature(
            tsa_cert.public_key.dump(), tsi["signature"].native, signed_bytes,
            tsi["signature_algorithm"],
            fallback_hash=safe(lambda: tsi["digest_algorithm"]["algorithm"].native))
        rep.sig_ok, rep.sig_note = ok, note
        rep.findings.append(Finding(
            "OK" if ok else "CRITICO",
            "TST_SIG_OK" if ok else "TST_SIG_BAD",
            "A assinatura do token de tempo confere" if ok
            else "A assinatura do token de tempo não confere", note))
        eku = safe(lambda: tsa_cert.extended_key_usage_value.native, []) or []
        rep.eku_ok = (list(eku) == ["time_stamping"])
        if not rep.eku_ok:
            rep.findings.append(Finding(
                "ALERTA", "TSA_EKU",
                "Certificado da ACT sem extendedKeyUsage exclusivo de timeStamping",
                f"EKU presente: {', '.join(eku) if eku else 'nenhum'}. A RFC 3161, "
                f"seção 2.3, exige timeStamping como único EKU."))
        else:
            rep.findings.append(Finding("OK", "TSA_EKU_OK",
                                        "Certificado da ACT com EKU exclusivo de timeStamping", ""))
    else:
        rep.findings.append(Finding(
            "ALERTA", "TSA_CERT_MISSING",
            "O certificado da Autoridade de Carimbo do Tempo não consta no token",
            "A assinatura do token não pôde ser verificada."))
    return rep

def describe_sync_declaration(raw: bytes) -> Optional[Dict[str, Any]]:
    """
    Tenta ler a Declaração de Sincronismo da ICP-Brasil embutida no TSTInfo.
    A estrutura é SEQUENCE { tbs, algoritmo, assinatura }, com nomes e janela
    de validade dentro do tbs. Extraímos o que for legível sem depender de
    esquema proprietário.
    """
    if not raw:
        return None
    out: Dict[str, Any] = {"names": [], "times": [], "signed": False}
    try:
        top = _AnySeq.load(raw)
        out["signed"] = len(top) == 3
    except Exception:
        return None
    # varre recursivamente por GeneralizedTime e por strings tipo host/DN
    def walk(blob: bytes, depth: int = 0):
        if depth > 8:
            return
        i = 0
        while i < len(blob) - 2:
            tag = blob[i]
            ln = blob[i + 1]
            hdr = 2
            if ln & 0x80:
                nb = ln & 0x7F
                if nb == 0 or nb > 4 or i + 2 + nb > len(blob):
                    return
                ln = int.from_bytes(blob[i + 2:i + 2 + nb], "big")
                hdr = 2 + nb
            body = blob[i + hdr:i + hdr + ln]
            if len(body) < ln:
                return
            if tag == 0x18 and 13 <= ln <= 19:  # GeneralizedTime
                try:
                    out["times"].append(core.GeneralizedTime.load(
                        blob[i:i + hdr + ln]).native)
                except Exception:
                    pass
            elif tag in (0x13, 0x0C, 0x16) and 3 <= ln <= 80:  # Printable/UTF8/IA5
                try:
                    s = body.decode("utf-8", "ignore").strip()
                    if s and any(ch.isalpha() for ch in s) and s not in out["names"]:
                        out["names"].append(s)
                except Exception:
                    pass
            elif tag & 0x20:  # construído: desce
                walk(body, depth + 1)
            i += hdr + ln

    walk(raw)
    out["times"] = sorted(set(out["times"]))
    interesting = [n for n in out["names"]
                   if any(k in n.upper() for k in
                          ("EAT", "ICPBRASIL", "ICP-BRASIL", "AC ", "AUTORIDADE",
                           ".GOV.BR", "TIMESTAMP", "SINCRON"))]
    out["names"] = interesting[:12] or out["names"][:8]
    return out

# ----------------------------------------------------------------------------
# Helpers de CMS
# ----------------------------------------------------------------------------

def pick_signer_cert(sd: cms.SignedData,
                     si: cms.SignerInfo) -> Optional[x509.Certificate]:
    """Localiza o certificado do signatário pelo SignerIdentifier."""
    sid = si["sid"]
    certs = [c.chosen for c in (sd["certificates"] or []) if c.name == "certificate"]
    if sid.name == "issuer_and_serial_number":
        iss = sid.chosen["issuer"].dump()
        ser = sid.chosen["serial_number"].native
        for c in certs:
            if c.issuer.dump() == iss and c.serial_number == ser:
                return c
    else:  # subject_key_identifier
        skid = sid.chosen.native
        for c in certs:
            if safe(lambda: c.key_identifier) == skid:
                return c
    return certs[0] if certs else None

def cms_signed_bytes(sd: cms.SignedData, si: cms.SignerInfo) -> bytes:
    """Bytes efetivamente cobertos pela assinatura do SignerInfo."""
    attrs = si["signed_attrs"]
    if attrs is not None and not isinstance(attrs, core.Void):
        return attrs.untag().dump()
    content = sd["encap_content_info"]["content"]
    return content.native if isinstance(content.native, bytes) else content.dump()

def attr_map(si: cms.SignerInfo, which: str) -> Dict[str, List[Any]]:
    out: Dict[str, List[Any]] = {}
    attrs = si[which]
    if attrs is None or isinstance(attrs, core.Void):
        return out
    for a in attrs:
        name = safe(lambda: a["type"].native) or safe(lambda: a["type"].dotted, "?")
        out.setdefault(str(name), []).extend(list(a["values"]))
    return out

def check_signing_cert_attr(si: cms.SignerInfo,
                            cert: Optional[x509.Certificate]) -> List[Finding]:
    """
    Confere o atributo signingCertificate / signingCertificateV2 (ESS):
    cardinalidade e coincidência do hash com o certificado apresentado.
    """
    out: List[Finding] = []
    signed = si["signed_attrs"]
    if signed is None or isinstance(signed, core.Void):
        out.append(Finding("ALERTA", "NO_SIGNED_ATTRS",
                           "CMS sem o campo signedAttrs",
                           "A assinatura recai diretamente sobre o conteúdo. A ETSI "
                           "EN 319 122-1 exige signedAttrs."))
        return out

    counts: Dict[str, int] = {}
    holders: Dict[str, Any] = {}
    for a in signed:
        name = str(safe(lambda: a["type"].native) or safe(lambda: a["type"].dotted, "?"))
        counts[name] = counts.get(name, 0) + 1
        if name in ("signing_certificate_v2", "signing_certificate"):
            holders[name] = a["values"][0]

    for name in ("signing_certificate_v2", "signing_certificate"):
        if counts.get(name, 0) > 1:
            out.append(Finding(
                "ALERTA", "SIGNING_CERT_ATTR_MULTIVALUED",
                f"Atributo '{name}' aparece {counts[name]} vezes no campo signedAttrs",
                "A RFC 5035, seção 5.4, e a ETSI EN 319 122-1 exigem cardinalidade 1. "
                "O pyHanko interrompe a validação nesse caso, com o código "
                "AdESIndeterminate.NO_SIGNING_CERTIFICATE_FOUND. As duas instâncias "
                "presentes neste arquivo têm conteúdo idêntico."))

    if not holders:
        out.append(Finding(
            "ATENCAO", "NO_SIGNING_CERT_ATTR",
            "Ausente o atributo signingCertificate(V2)",
            "Atributo exigido pela ETSI EN 319 122-1. O único elo entre a assinatura "
            "e o certificado é a verificação da assinatura com a chave pública."))
        return out

    # confere o hash declarado
    if cert is None:
        return out
    for name, val in holders.items():
        try:
            entries = val["certs"]
            first = entries[0]
            if name == "signing_certificate_v2":
                algo = safe(lambda: first["hash_algorithm"]["algorithm"].native, "sha256")
            else:
                algo = "sha1"
            declared = first["cert_hash"].native
            calc = digest_bytes(cert.dump(), algo)
            if declared == calc:
                out.append(Finding("OK", "SIGNING_CERT_ATTR_MATCH",
                                   f"Atributo {name} confere com o certificado apresentado",
                                   f"Hash {algo_label(algo)} idêntico."))
            else:
                out.append(Finding(
                    "CRITICO", "SIGNING_CERT_ATTR_MISMATCH",
                    f"Atributo {name} não corresponde ao certificado embutido",
                    "O hash declarado no atributo difere do hash do certificado "
                    "presente no CMS."))
        except Exception:
            continue
    return out

# ----------------------------------------------------------------------------
# Análise do DSS / VRI (material de validação de longo prazo)
# ----------------------------------------------------------------------------

@dataclass
class DSSReport:
    present: bool = False
    has_certs: bool = False
    n_certs: int = 0
    n_crls: int = 0
    n_ocsps: int = 0
    vri_keys: List[str] = dc_field(default_factory=list)
    vri_detail: Dict[str, Dict[str, int]] = dc_field(default_factory=dict)
    history: List[str] = dc_field(default_factory=list)
    findings: List[Finding] = dc_field(default_factory=list)

def dss_history(reader_hist: PdfFileReader) -> List[Tuple[int, List[str]]]:
    """Chaves presentes no dicionário DSS em cada revisão em que ele aparece."""
    out: List[Tuple[int, List[str]]] = []
    total = reader_hist.xrefs.total_revisions
    for rev in range(total):
        for ref in (safe(lambda: reader_hist.xrefs.explicit_refs_in_revision(rev), []) or []):
            obj = safe(lambda: reader_hist.get_object(ref, revision=rev))
            if not isinstance(obj, generic.DictionaryObject):
                continue
            keys = {str(k) for k in obj.keys()}
            if "/VRI" in keys or ({"/Certs", "/CRLs", "/OCSPs"} & keys):
                if "/Type" in keys and str(obj.get("/Type")) not in ("", "None"):
                    continue
                out.append((rev + 1, sorted(keys)))
    return out

def analyze_dss(reader: PdfFileReader, harvest: Harvest) -> DSSReport:
    rep = DSSReport()
    root = reader.root
    dss = safe(lambda: root["/DSS"])
    if dss is None:
        rep.findings.append(Finding(
            "ATENCAO", "NO_DSS",
            "Documento sem Document Security Store (DSS)",
            "Não há certificados, LCR nem OCSP arquivados no PDF."))
        return rep

    rep.present = True
    dss = dss.get_object()

    def count(key: str) -> int:
        arr = safe(lambda: dss[key])
        if arr is None:
            return 0
        arr = arr.get_object()
        return len(arr)

    rep.n_certs = count("/Certs")
    rep.n_crls = count("/CRLs")
    rep.n_ocsps = count("/OCSPs")
    rep.has_certs = rep.n_certs > 0

    for key, origin in (("/Certs", "DSS /Certs"), ("/CRLs", "DSS /CRLs"),
                        ("/OCSPs", "DSS /OCSPs")):
        arr = safe(lambda: dss[key])
        if arr is None:
            continue
        for entry in arr.get_object():
            data = safe(lambda: entry.get_object().data)
            if data:
                try_parse_der(data, harvest, origin)

    vri = safe(lambda: dss["/VRI"])
    if vri is not None:
        vri = vri.get_object()
        for k in vri.keys():
            key = str(k).lstrip("/")
            rep.vri_keys.append(key)
            sub = safe(lambda: vri[k].get_object())
            detail = {}
            if sub is not None:
                for sk in ("/Cert", "/CRL", "/OCSP"):
                    arr = safe(lambda: sub[sk])
                    if arr is not None:
                        arr = arr.get_object()
                        detail[sk.lstrip("/")] = len(arr)
                        for entry in arr:
                            data = safe(lambda: entry.get_object().data)
                            if data:
                                try_parse_der(data, harvest, f"DSS /VRI{sk}")
                ts = safe(lambda: sub["/TU"]) or safe(lambda: sub["/TS"])
                if ts is not None:
                    detail["timestamp_declarado"] = 1
            rep.vri_detail[key] = detail

    if not rep.has_certs:
        rep.findings.append(Finding(
            "ALERTA", "DSS_WITHOUT_CERTS",
            "O DSS não arquiva certificados (/Certs ausente ou vazio)",
            "O perfil PAdES B-LT (ETSI EN 319 142-1) requer a cadeia no DSS."))
    else:
        rep.findings.append(Finding(
            "OK", "DSS_CERTS",
            f"O DSS arquiva {rep.n_certs} certificado(s)", ""))

    if rep.n_crls == 0 and rep.n_ocsps == 0:
        rep.findings.append(Finding(
            "ALERTA", "DSS_WITHOUT_REVINFO",
            "O DSS não arquiva informação de revogação (nem LCR nem OCSP)", ""))
    else:
        rep.findings.append(Finding(
            "OK", "DSS_REVINFO",
            f"O DSS arquiva {rep.n_crls} LCR(s) e {rep.n_ocsps} resposta(s) OCSP", ""))
    return rep

# ----------------------------------------------------------------------------
# Revisões incrementais
# ----------------------------------------------------------------------------

@dataclass
class RevisionReport:
    index: int                     # 1-based, para leitura humana
    n_objects: int
    startxref: Optional[int]
    objects: List[int] = dc_field(default_factory=list)
    notes: List[str] = dc_field(default_factory=list)

def analyze_revisions(reader: PdfFileReader) -> Tuple[List[RevisionReport], List[Finding]]:
    reps: List[RevisionReport] = []
    findings: List[Finding] = []
    total = reader.xrefs.total_revisions
    for rev in range(total):
        refs = list(safe(lambda: reader.xrefs.explicit_refs_in_revision(rev), []) or [])
        ids = sorted({r.idnum for r in refs})
        rr = RevisionReport(index=rev + 1, n_objects=len(refs),
                            startxref=safe(lambda: reader.xrefs.get_startxref_for_revision(rev)),
                            objects=ids)
        # o que aparece de relevante nesta revisão?
        for ref in refs:
            obj = safe(lambda: reader.get_object(ref, revision=rev))
            if obj is None:
                continue
            if isinstance(obj, generic.DictionaryObject):
                t = str(safe(lambda: obj.get("/Type"), ""))
                if t == "/Catalog":
                    if "/DSS" in obj:
                        rr.notes.append("catálogo passa a apontar /DSS")
                    if "/Extensions" in obj:
                        rr.notes.append("declara /Extensions (nível de extensão ESIC)")
                    if "/Perms" in obj:
                        rr.notes.append("declara /Perms")
                elif t == "/Sig":
                    rr.notes.append("grava dicionário de assinatura /Sig")
                elif t == "/DocTimeStamp":
                    rr.notes.append("grava carimbo de tempo de documento /DocTimeStamp")
                elif "/VRI" in obj or "/CRLs" in obj or "/Certs" in obj:
                    keys = [str(k) for k in obj.keys()]
                    rr.notes.append(f"grava/atualiza DSS com {', '.join(sorted(keys))}")
                elif "/Producer" in obj or "/CreationDate" in obj:
                    rr.notes.append("grava/atualiza dicionário /Info (metadados)")
                elif str(safe(lambda: obj.get("/FT"), "")) == "/Sig":
                    rr.notes.append("cria/atualiza campo de assinatura no AcroForm")
        if rev == 0:
            rr.notes = ["documento base (versão original, antes de qualquer "
                        "atualização incremental)"]
        rr.notes = list(dict.fromkeys(rr.notes))
        reps.append(rr)
    return reps, findings

def diff_dicts(reader: PdfFileReader, idnum: int, rev_a: int,
               rev_b: int) -> Optional[Dict[str, Tuple[str, str]]]:
    a = safe(lambda: reader.get_object(generic.Reference(idnum, 0, reader), revision=rev_a))
    b = safe(lambda: reader.get_object(generic.Reference(idnum, 0, reader), revision=rev_b))
    if not isinstance(a, generic.DictionaryObject) or not isinstance(b, generic.DictionaryObject):
        return None
    out = {}
    for k in set(list(a.keys()) + list(b.keys())):
        va, vb = safe(lambda: a.get(k)), safe(lambda: b.get(k))
        if str(va) != str(vb):
            out[str(k)] = (str(va), str(vb))
    return out or None

def find_info_and_metadata_changes(reader: PdfFileReader, signed_rev: int
                                   ) -> List[Finding]:
    """Compara /Info e XMP entre a revisão assinada e a última."""
    out: List[Finding] = []
    last = reader.xrefs.total_revisions - 1
    if last <= signed_rev:
        return out
    # /Info
    info_ref = safe(lambda: reader.trailer.raw_get("/Info"))
    if info_ref is not None:
        idnum = safe(lambda: info_ref.idnum)
        if idnum:
            d = diff_dicts(reader, idnum, signed_rev, last)
            if d:
                lines = "; ".join(f"{k}: «{v[0][:60]}» → «{v[1][:60]}»"
                                  for k, v in sorted(d.items()))
                out.append(Finding(
                    "ATENCAO", "INFO_CHANGED_AFTER_SIGNING",
                    "O dicionário /Info foi reescrito após a assinatura",
                    f"Mudanças: {lines}."))
    # XMP
    md_ref = safe(lambda: reader.root.raw_get("/Metadata"))
    if md_ref is not None and hasattr(md_ref, "idnum"):
        a = safe(lambda: reader.get_object(generic.Reference(md_ref.idnum, 0, reader),
                                           revision=signed_rev))
        b = safe(lambda: reader.get_object(generic.Reference(md_ref.idnum, 0, reader),
                                           revision=last))
        da = safe(lambda: a.data) if a is not None else None
        db = safe(lambda: b.data) if b is not None else None
        if da is not None and db is not None:
            if da == db:
                out.append(Finding("OK", "XMP_UNCHANGED",
                                   "Os metadados XMP são idênticos antes e depois da assinatura", ""))
            else:
                out.append(Finding(
                    "ATENCAO", "XMP_CHANGED",
                    "Os metadados XMP foram alterados após a assinatura", ""))
    return out

# ----------------------------------------------------------------------------
# Análise de cada assinatura
# ----------------------------------------------------------------------------

@dataclass
class SigReport:
    index: int
    field_name: str
    obj_type: str                       # /Sig ou /DocTimeStamp
    subfilter: str = ""
    filt: str = ""
    declared_time: Optional[str] = None
    reason: Optional[str] = None
    location: Optional[str] = None
    contact: Optional[str] = None
    name_entry: Optional[str] = None
    byte_range: List[int] = dc_field(default_factory=list)
    covered_bytes: int = 0
    file_size: int = 0
    tail_bytes: int = 0
    placeholder_bytes: int = 0
    cms_der_bytes: int = 0
    coverage_level: str = ""
    coverage_exact: bool = False
    digest_algo: str = ""
    sig_algo: str = ""
    detached: bool = True
    n_certs_in_cms: int = 0
    signed_attrs: Dict[str, int] = dc_field(default_factory=dict)
    unsigned_attrs: Dict[str, int] = dc_field(default_factory=dict)
    digest_ok: Optional[bool] = None
    digest_expected: str = ""
    digest_found: str = ""
    math_ok: Optional[bool] = None
    math_note: str = ""
    signer_cert: Optional[x509.Certificate] = None
    signer_info: Dict[str, Any] = dc_field(default_factory=dict)
    chain: List[x509.Certificate] = dc_field(default_factory=list)
    chain_links: List[ChainLink] = dc_field(default_factory=list)
    revocation: Dict[str, Any] = dc_field(default_factory=dict)
    path_results: Dict[str, str] = dc_field(default_factory=dict)
    timestamps: List[TimestampReport] = dc_field(default_factory=list)
    reference_time: Optional[datetime.datetime] = None
    reference_source: str = ""
    signed_revision: int = 0
    total_revisions: int = 0
    modification_level: Optional[str] = None
    diff_error: Optional[str] = None
    changed_fields: List[str] = dc_field(default_factory=list)
    docmdp: Optional[int] = None
    fieldmdp: bool = False
    pades_level: str = ""
    pades_note: str = ""
    orphan: bool = False
    orphan_reason: str = ""
    obj_idnum: Optional[int] = None
    widget_idnum: Optional[int] = None
    alignment: Dict[str, Any] = dc_field(default_factory=dict)
    findings: List[Finding] = dc_field(default_factory=list)

class RawSignatureRef:
    """
    Adaptador que expõe um dicionário /Sig cru com a mesma interface que o
    pyHanko oferece para assinaturas registradas no AcroForm.

    Serve para analisar assinaturas ÓRFÃS: o dicionário existe no arquivo, mas
    não é alcançável pelo formulário, de modo que validadores (inclusive o
    pyHanko e o Adobe) simplesmente não a enxergam.
    """

    def __init__(self, sig_dict, idnum: int, revision: int,
                 field_name: str, widget_idnum: Optional[int]):
        self.sig_object = sig_dict
        self.idnum = idnum
        self.signed_revision = revision
        self.field_name = field_name
        self.widget_idnum = widget_idnum
        self._sd = None

    @property
    def sig_object_type(self):
        return str(safe(lambda: self.sig_object["/Type"], "/Sig"))

    @property
    def signed_data(self) -> cms.SignedData:
        if self._sd is None:
            raw = bytes(self.sig_object["/Contents"])
            self._sd = cms.ContentInfo.load(raw)["content"]
        return self._sd

    @property
    def self_reported_timestamp(self):
        return parse_pdf_date(safe(lambda: str(self.sig_object["/M"])))

    @property
    def docmdp_level(self):
        for ref in (safe(lambda: self.sig_object["/Reference"], []) or []):
            ref = safe(lambda: ref.get_object())
            if ref is None:
                continue
            if str(safe(lambda: ref["/TransformMethod"], "")) == "/DocMDP":
                params = safe(lambda: ref["/TransformParams"].get_object())
                if params is not None:
                    return safe(lambda: int(params["/P"]), 2)
                return 2
        return None

    @property
    def fieldmdp(self):
        for ref in (safe(lambda: self.sig_object["/Reference"], []) or []):
            ref = safe(lambda: ref.get_object())
            if ref is not None and str(safe(lambda: ref["/TransformMethod"], "")) == "/FieldMDP":
                return ref
        return None

    def evaluate_signature_coverage(self):
        raise NotImplementedError("assinatura órfã: cobertura avaliada manualmente")

def parse_pdf_date(raw: Optional[str]) -> Optional[datetime.datetime]:
    """Converte D:YYYYMMDDHHmmSS[+-]HH'mm' em datetime com fuso."""
    if not raw:
        return None
    t = raw.strip()
    if t.startswith("D:"):
        t = t[2:]
    t = t.replace("'", "")
    try:
        base = datetime.datetime.strptime(t[:14], "%Y%m%d%H%M%S")
    except Exception:
        return None
    tzpart = t[14:]
    if tzpart and tzpart[0] in "+-" and len(tzpart) >= 3:
        sign = 1 if tzpart[0] == "+" else -1
        hh = int(tzpart[1:3] or 0)
        mm = int(tzpart[3:5] or 0) if len(tzpart) >= 5 else 0
        off = datetime.timezone(sign * datetime.timedelta(hours=hh, minutes=mm))
    else:
        off = datetime.timezone.utc
    return base.replace(tzinfo=off)

def find_all_signature_dicts(reader_hist: PdfFileReader
                             ) -> List[Tuple[int, int, Any, Optional[int], str]]:
    """
    Varre TODOS os objetos de TODAS as revisões procurando dicionários de
    assinatura, estejam eles registrados no AcroForm ou não.

    Retorna (idnum, revisão, dicionário, idnum do widget, nome do campo).
    """
    found: Dict[int, Tuple[int, int, Any, Optional[int], str]] = {}
    widgets: Dict[int, Tuple[int, str]] = {}   # idnum do /Sig -> (widget, nome)

    total = reader_hist.xrefs.total_revisions
    for rev in range(total):
        for ref in (safe(lambda: reader_hist.xrefs.explicit_refs_in_revision(rev), []) or []):
            obj = safe(lambda: reader_hist.get_object(ref, revision=rev))
            if not isinstance(obj, generic.DictionaryObject):
                continue
            # campo/widget de assinatura: guarda o nome e o alvo
            if str(safe(lambda: obj.get("/FT"), "")) == "/Sig":
                v = safe(lambda: obj.raw_get("/V"))
                target = safe(lambda: v.idnum) if v is not None else None
                name = str(safe(lambda: obj.get("/T"), "") or "")
                if target is not None:
                    widgets[target] = (ref.idnum, name)
            # dicionário de assinatura propriamente dito
            is_sig = str(safe(lambda: obj.get("/Type"), "")) in ("/Sig", "/DocTimeStamp")
            has_parts = "/ByteRange" in obj and "/Contents" in obj
            if (is_sig or has_parts) and "/Contents" in obj:
                found.setdefault(ref.idnum, (ref.idnum, rev, obj, None, ""))

    out = []
    for idnum, (i, rev, obj, _, _) in found.items():
        w, name = widgets.get(idnum, (None, ""))
        out.append((i, rev, obj, w, name))
    return sorted(out, key=lambda x: x[0])

def check_byterange_alignment(data: bytes, br: Sequence[int],
                              contents_len: int) -> Dict[str, Any]:
    """
    Verifica se o /ByteRange ainda aponta para o lugar certo dentro do arquivo.

    Num PDF assinado íntegro, o byte imediatamente após o primeiro trecho é o
    '<' que abre a cadeia hexadecimal de /Contents, e o byte anterior ao início
    do segundo trecho é o '>' que a fecha. Se isso não bate, o arquivo foi
    reescrito depois de assinado e o /ByteRange ficou defasado — a assinatura
    passa a apontar para bytes que não são mais os dela.
    """
    res: Dict[str, Any] = {"aligned": None, "open_char": None, "close_char": None,
                           "gap_ok": None, "ends_at_eof": None, "shift": None}
    if len(br) < 4:
        return res
    a, b = br[0] + br[1], br[2]
    res["gap_ok"] = (b - a) == 2 * contents_len + 2
    if 0 <= a < len(data):
        res["open_char"] = data[a:a + 1]
    if 0 < b <= len(data):
        res["close_char"] = data[b - 1:b]
    res["aligned"] = (res["open_char"] == b"<" and res["close_char"] == b">")
    end = br[-2] + br[-1]
    tail = data[max(0, end - 24):end]
    res["ends_at_eof"] = tail.rstrip().endswith(b"%%EOF")
    if not res["aligned"]:
        # tenta localizar o deslocamento procurando o '<' mais próximo
        window = 1 << 16
        lo, hi = max(0, a - window), min(len(data), a + window)
        best = None
        for pos in range(lo, hi):
            if data[pos:pos + 1] == b"<" and \
                    data[pos + 1 + 2 * contents_len:pos + 2 + 2 * contents_len] == b">":
                if best is None or abs(pos - a) < abs(best - a):
                    best = pos
        if best is not None:
            res["shift"] = best - a
    return res

def compute_diff(pdf_path: str, signed_revision: int) -> Tuple[Optional[str], List[str], Optional[str]]:
    """
    Compara a revisão assinada com a versão final do arquivo.

    Roda em um leitor recém-aberto e exclusivo: o pyHanko percorre as revisões
    históricas para procurar objetos órfãos e falha se o mesmo leitor já tiver
    sido usado para outras leituras (os objetos ficam em cache numa forma que
    perde a referência ao contêiner original).
    """
    try:
        with open(pdf_path, "rb") as fh:
            r = PdfFileReader(fh, strict=False)
            diff = DEFAULT_DIFF_POLICY.review_file(r, signed_revision)
            lvl = getattr(diff, "modification_level", None)
            fields = sorted(str(x) for x in
                            (getattr(diff, "changed_form_fields", set()) or set()))
            return (lvl.name if lvl is not None else None), fields, None
    except Exception as e:
        return None, [], f"{type(e).__name__}: {e}"

def analyze_signature(reader: PdfFileReader, sig, index: int, data: bytes,
                      harvest: Harvest, anchors: Sequence[x509.Certificate],
                      dss: DSSReport, args) -> SigReport:
    sd = sig.signed_data
    si = sd["signer_infos"][0]
    obj_type = str(safe(lambda: sig.sig_object_type, "/Sig"))

    rep = SigReport(
        index=index,
        field_name=str(sig.field_name),
        obj_type=obj_type,
        subfilter=str(safe(lambda: sig.sig_object["/SubFilter"], "?")),
        filt=str(safe(lambda: sig.sig_object["/Filter"], "?")),
        declared_time=safe(lambda: str(sig.sig_object["/M"])),
        reason=safe(lambda: str(sig.sig_object["/Reason"])),
        location=safe(lambda: str(sig.sig_object["/Location"])),
        contact=safe(lambda: str(sig.sig_object["/ContactInfo"])),
        name_entry=safe(lambda: str(sig.sig_object["/Name"])),
        file_size=len(data),
        total_revisions=reader.xrefs.total_revisions,
        signed_revision=safe(lambda: sig.signed_revision, 0),
    )

    # A comparação entre revisões é feita ANTES de qualquer outra leitura: o
    # pyHanko é sensível ao estado interno do leitor e falha se o arquivo já
    # tiver sido percorrido de outras formas.
    rep.modification_level, rep.changed_fields, rep.diff_error = compute_diff(
        args.pdf, sig.signed_revision)

    harvest_from_cms(sd, harvest, f"assinatura #{index}")
    harvest_from_revinfo_attr(si, harvest, f"assinatura #{index}")

    # ---- cobertura do ByteRange ------------------------------------------
    br = [int(x) for x in safe(lambda: sig.sig_object["/ByteRange"], []) or []]
    rep.byte_range = br
    if len(br) >= 4:
        rep.covered_bytes = sum(br[1::2])
        end = br[-2] + br[-1]
        rep.tail_bytes = len(data) - end
        rep.placeholder_bytes = br[2] - (br[0] + br[1])
        signed_bytes_pdf = b"".join(data[br[i]:br[i] + br[i + 1]]
                                    for i in range(0, len(br), 2))
    else:
        signed_bytes_pdf = b""
        rep.findings.append(Finding("CRITICO", "NO_BYTERANGE",
                                    "Assinatura sem /ByteRange utilizável", ""))

    rep.coverage_level = str(safe(lambda: sig.evaluate_signature_coverage().name,
                                  "não avaliável (assinatura fora do formulário)"))
    contents = bytes(safe(lambda: sig.sig_object["/Contents"], b"") or b"")
    rep.alignment = check_byterange_alignment(data, br, len(contents))
    rep.cms_der_bytes = len(safe(
        lambda: cms.ContentInfo.load(contents).dump(), b"") or b"") or len(sd.dump())
    if len(br) >= 4:
        # o intervalo termina exatamente no fim de uma revisão?
        rep.coverage_exact = data[max(0, br[-2] + br[-1] - 6): br[-2] + br[-1]].rstrip().endswith(b"%%EOF")
        if rep.tail_bytes == 0:
            rep.findings.append(Finding(
                "OK", "COVERAGE_WHOLE_FILE",
                "O /ByteRange cobre o arquivo do byte 0 ao fim", ""))
        elif rep.signed_revision >= rep.total_revisions - 1:
            rep.findings.append(Finding(
                "ALERTA", "TRAILING_GARBAGE",
                f"Existem {human_bytes(rep.tail_bytes)} após o trecho assinado sem "
                f"revisão correspondente",
                "Não há revisão posterior à revisão assinada, e os bytes finais não "
                "formam uma atualização incremental (ausência de xref/startxref/%%EOF "
                "correspondente)."))
        else:
            rep.findings.append(Finding(
                "ATENCAO", "COVERAGE_INCREMENTAL",
                f"Existem {human_bytes(rep.tail_bytes)} acrescentados após o trecho assinado",
                "Correspondem a atualizações incrementais posteriores. O conteúdo de "
                "cada uma consta na seção de revisões incrementais."))
        al = rep.alignment
        if al.get("aligned") is False:
            shift = al.get("shift")
            detalhe = (
                f"Na posição {br[0] + br[1]}, indicada pelo /ByteRange como início do "
                f"espaço reservado ao /Contents, o byte encontrado é "
                f"{al.get('open_char')!r}; o esperado é b'<'. Na posição {br[2] - 1}, "
                f"fim desse espaço, o byte encontrado é {al.get('close_char')!r}; o "
                f"esperado é b'>'.")
            if shift:
                detalhe += (
                    f" A cadeia hexadecimal do /Contents inicia {abs(shift)} bytes "
                    f"{'adiante' if shift > 0 else 'atrás'} da posição declarada.")
            rep.findings.append(Finding(
                "CRITICO", "BYTERANGE_MISALIGNED",
                "O /ByteRange não coincide com a posição física da assinatura no "
                "arquivo", detalhe))
        elif al.get("ends_at_eof") is False and rep.tail_bytes > 0:
            rep.findings.append(Finding(
                "ATENCAO", "BYTERANGE_NOT_AT_EOF",
                "O trecho assinado não termina em um marcador %%EOF",
                "O limite superior do /ByteRange não coincide com o fim de nenhuma "
                "revisão do arquivo."))

        gap_expected = 2 * len(contents) + 2
        if rep.placeholder_bytes != gap_expected:
            rep.findings.append(Finding(
                "CRITICO", "COVERAGE_GAP",
                "Há bytes não cobertos dentro do intervalo do /ByteRange, além do "
                "espaço reservado ao /Contents",
                f"Lacuna de {rep.placeholder_bytes} bytes entre os dois trechos "
                f"cobertos; o espaço reservado ao /Contents é de {gap_expected} bytes. "
                f"Diferença: {rep.placeholder_bytes - gap_expected} bytes não cobertos."))
        else:
            rep.findings.append(Finding(
                "OK", "COVERAGE_NO_GAP",
                "A única parte não coberta dentro do intervalo é o espaço reservado "
                "ao /Contents", ""))

    # ---- CMS -------------------------------------------------------------
    rep.digest_algo = str(safe(lambda: si["digest_algorithm"]["algorithm"].native, "?"))
    rep.sig_algo = str(safe(lambda: si["signature_algorithm"]["algorithm"].native, "?"))
    econtent = sd["encap_content_info"]["content"]
    rep.detached = econtent is None or isinstance(econtent, core.Void) or econtent.native is None
    rep.n_certs_in_cms = len([c for c in (sd["certificates"] or [])])
    rep.signed_attrs = {k: len(v) for k, v in attr_map(si, "signed_attrs").items()}
    rep.unsigned_attrs = {k: len(v) for k, v in attr_map(si, "unsigned_attrs").items()}

    if rep.digest_algo.replace("-", "_") in WEAK_HASHES:
        rep.findings.append(Finding("ALERTA", "WEAK_DIGEST",
                                    f"Assinatura calculada com {algo_label(rep.digest_algo)}",
                                    "Função não admitida pela ETSI TS 119 312."))

    if "signing_time" in rep.signed_attrs and obj_type == "/Sig":
        rep.findings.append(Finding(
            "INFO", "SIGNING_TIME_PRESENT",
            "O CMS declara o atributo signingTime",
            "Valor gravado pelo software do signatário, não aferido por terceiro. "
            "A ETSI EN 319 142-1 determina sua ausência em PAdES."))

    # ---- integridade: recomputa o digest ---------------------------------
    # Num /DocTimeStamp não existe messageDigest sobre o ByteRange: o que amarra o
    # carimbo ao PDF é o messageImprint do TSTInfo. O tratamento é feito adiante,
    # na análise do próprio token.
    if signed_bytes_pdf and obj_type != "/DocTimeStamp":
        calc = digest_bytes(signed_bytes_pdf, rep.digest_algo)
        declared = None
        for a in attr_map(si, "signed_attrs").get("message_digest", []):
            declared = a.native
        if declared is None:
            # CMS sem atributos assinados: assinatura direta sobre o conteúdo
            rep.digest_ok = None
            rep.findings.append(Finding("ATENCAO", "NO_MESSAGE_DIGEST",
                                        "Sem atributo messageDigest para conferir", ""))
        else:
            rep.digest_ok = (calc == declared)
            rep.digest_expected = declared.hex()
            rep.digest_found = calc.hex()
            rep.findings.append(Finding(
                "OK" if rep.digest_ok else "CRITICO",
                "DIGEST_MATCH" if rep.digest_ok else "DIGEST_MISMATCH",
                "O digest recalculado sobre o intervalo do /ByteRange é idêntico ao "
                "declarado no atributo messageDigest" if rep.digest_ok else
                "O digest recalculado sobre o intervalo do /ByteRange difere do "
                "declarado no atributo messageDigest",
                f"{algo_label(rep.digest_algo)} calculado sobre o arquivo = "
                f"{calc.hex()}; declarado dentro da assinatura = {declared.hex()}."))

    # ---- verificação matemática ------------------------------------------
    rep.signer_cert = pick_signer_cert(sd, si)
    if obj_type == "/DocTimeStamp":
        pass  # verificado como token de tempo, logo abaixo
    elif rep.signer_cert is not None:
        ok, note = verify_raw_signature(
            rep.signer_cert.public_key.dump(), si["signature"].native,
            cms_signed_bytes(sd, si), si["signature_algorithm"],
            fallback_hash=rep.digest_algo)
        rep.math_ok, rep.math_note = ok, note
        rep.findings.append(Finding(
            "OK" if ok else "CRITICO",
            "SIG_MATH_OK" if ok else "SIG_MATH_BAD",
            "A assinatura do campo signedAttrs confere com a chave pública do "
            "certificado" if ok else "A assinatura do campo signedAttrs não confere com a chave pública do certificado", note))
        rep.findings.extend(check_signing_cert_attr(si, rep.signer_cert))
        rep.signer_info = describe_cert(rep.signer_cert, redact=args.redact)
    else:
        rep.findings.append(Finding(
            "CRITICO", "NO_SIGNER_CERT",
            "O certificado do signatário não consta no CMS",
            "A assinatura não pôde ser verificada."))

    if rep.digest_ok is False and rep.math_ok:
        rep.findings.append(Finding(
            "CRITICO", "SIGNATURE_DETACHED_FROM_CONTENT",
            "A assinatura do bloco CMS confere; o messageDigest nele declarado não "
            "corresponde ao conteúdo do arquivo",
            "As duas verificações têm objetos distintos: a primeira recai sobre o "
            "campo signedAttrs, a segunda sobre o intervalo do /ByteRange. O conteúdo "
            "cujo resumo consta no messageDigest não está presente neste arquivo."))

    # ---- carimbos de tempo ------------------------------------------------
    if obj_type == "/DocTimeStamp":
        ci = cms.ContentInfo({"content_type": "signed_data", "content": sd})
        t = analyze_tst(ci, "DocTimeStamp", signed_bytes_pdf,
                        "trecho assinado do PDF", harvest)
        rep.timestamps.append(t)
        # para um carimbo de documento, integridade == imprint confere;
        # autoria == assinatura do token confere
        rep.digest_ok = t.imprint_matches
        rep.math_ok = t.sig_ok
        rep.math_note = t.sig_note
        if t.tsa_cert is not None:
            rep.signer_cert = t.tsa_cert
            rep.signer_info = describe_cert(t.tsa_cert, redact=args.redact)
        if t.imprint_matches:
            rep.findings.append(Finding(
                "OK", "DTS_COVERS_FILE",
                "O messageImprint do carimbo de documento corresponde ao intervalo "
                "assinado",
                f"{algo_label(t.imprint_algo)} do ByteRange confere com o "
                f"messageImprint do token."))
        elif t.imprint_matches is False:
            rep.findings.append(Finding(
                "CRITICO", "DTS_MISMATCH",
                "O messageImprint do carimbo de documento não corresponde ao intervalo assinado", ""))
    else:
        for name, kind, target, label in (
            ("signature_time_stamp_token", "signature-time-stamp",
             si["signature"].native, "valor da assinatura (signatureValue)"),
            ("content_time_stamp", "content-time-stamp",
             signed_bytes_pdf, "conteúdo assinado"),
        ):
            for val in attr_map(si, "unsigned_attrs").get(name, []):
                try:
                    ci = cms.ContentInfo.load(val.dump())
                except Exception:
                    continue
                rep.timestamps.append(analyze_tst(ci, kind, target, label, harvest))

    if obj_type == "/Sig" and not any(t.kind == "signature-time-stamp"
                                      for t in rep.timestamps):
        rep.findings.append(Finding(
            "ALERTA", "NO_TIMESTAMP",
            "Ausente carimbo de tempo criptográfico",
            "Não há atributo signature-time-stamp no CMS nem /DocTimeStamp no "
            "documento. As únicas datas presentes são as gravadas pelo software do "
            "signatário."))

    # ---- instante de referência para validação ---------------------------
    tsts = [t for t in rep.timestamps if t.gen_time and t.imprint_matches is not False]
    if tsts:
        rep.reference_time = min(t.gen_time for t in tsts)
        rep.reference_source = f"carimbo de tempo ({tsts[0].kind})"
    else:
        rep.reference_time = safe(lambda: sig.self_reported_timestamp)
        rep.reference_source = "hora autodeclarada no dicionário /M (sem valor probatório)"
    if rep.reference_time is None:
        rep.reference_time = datetime.datetime.now(datetime.timezone.utc)
        rep.reference_source = "data atual (não havia hora confiável no documento)"

    # ---- cadeia, revogação, validação de caminho -------------------------
    pool = harvest.cert_list
    if rep.signer_cert is not None:
        rep.chain, rep.chain_links, cf = build_chain(rep.signer_cert, pool)
        rep.findings.extend(cf)
        rep.findings.extend(cert_time_findings(rep.signer_cert, "Signatário",
                                               rep.reference_time))
        rep.revocation = revocation_status(rep.signer_cert, harvest.crl_list,
                                           rep.reference_time)
        if rep.revocation["revoked"]:
            rep.findings.append(Finding(
                "CRITICO", "CERT_REVOKED",
                "O certificado do signatário consta como REVOGADO",
                f"Data da revogação: {fmt_dt(rep.revocation['revocation_date'])}; "
                f"motivo declarado na LCR: "
                f"{rep.revocation.get('reason') or 'não informado'}."))
        elif rep.revocation["checked"]:
            rep.findings.append(Finding(
                "OK", "CERT_NOT_REVOKED",
                "O número de série do certificado não consta nas LCRs presentes no arquivo", ""))
        else:
            rep.findings.append(Finding(
                "ATENCAO", "REVOCATION_UNCHECKED",
                "Não há LCR/OCSP no arquivo que cubra o emissor do signatário",
                "A situação de revogação não foi apurada."))

        for label, mode, moment in (
            ("no instante do carimbo, exigindo revogação (hard-fail)", "hard-fail",
             rep.reference_time),
            ("no instante do carimbo, tolerando falta de revogação (soft-fail)",
             "soft-fail", rep.reference_time),
            ("na data de hoje (hard-fail)", "hard-fail", None),
        ):
            ok, note = validate_path(rep.signer_cert, pool, harvest.crl_list,
                                     list(harvest.ocsps.values()), anchors,
                                     moment, mode, args.fetch)
            rep.path_results[label] = ("VÁLIDO — " + note) if ok else ("FALHOU — " + note)

    # cadeias das ACTs
    for t in rep.timestamps:
        if t.tsa_cert is not None:
            t.chain, t.chain_links, tf = build_chain(t.tsa_cert, pool)
            t.findings.extend(tf)
            t.revocation = revocation_status(t.tsa_cert, harvest.crl_list, t.gen_time)
            if not t.revocation["checked"]:
                t.findings.append(Finding(
                    "ATENCAO", "TSA_REVOCATION_UNCHECKED",
                    "Sem LCR/OCSP no arquivo para a cadeia da Autoridade de Carimbo "
                    "do Tempo",
                    "A validação do caminho do carimbo em modo hard-fail não se "
                    "completa por ausência desse material."))
            elif t.revocation["revoked"]:
                t.findings.append(Finding("CRITICO", "TSA_REVOKED",
                                          "Certificado da ACT consta como revogado", ""))
            for label, mode in (("no instante do carimbo (hard-fail)", "hard-fail"),
                                ("no instante do carimbo (soft-fail)", "soft-fail")):
                ok, note = validate_path(t.tsa_cert, pool, harvest.crl_list,
                                         list(harvest.ocsps.values()), anchors,
                                         t.gen_time, mode, args.fetch)
                t.path_results[label] = ("VÁLIDO — " + note) if ok else ("FALHOU — " + note)

    # ---- modificações posteriores (calculado no início) ------------------
    lvl = rep.modification_level or ""
    if rep.tail_bytes == 0:
        pass
    elif rep.diff_error:
        rep.findings.append(Finding(
            "ATENCAO", "DIFF_UNAVAILABLE",
            "A comparação automática entre revisões não pôde ser concluída",
            f"Erro retornado: {rep.diff_error}. Os objetos gravados por cada "
            f"revisão constam na seção de revisões incrementais."))
    elif "NONE" in lvl:
        rep.findings.append(Finding("OK", "DIFF_NONE",
                                    "As revisões posteriores não alteraram nada de relevante", ""))
    elif "LTA_UPDATES" in lvl:
        rep.findings.append(Finding(
            "OK", "DIFF_LTA",
            "As alterações posteriores restringem-se a objetos de validação de "
            "longo prazo (DSS e carimbo de documento)",
            "Classificação ModificationLevel.LTA_UPDATES do pyHanko. Nenhuma página, "
            "campo de formulário ou objeto de conteúdo foi alterado."))
    elif "FORM_FILLING" in lvl:
        rep.findings.append(Finding(
            "ATENCAO", "DIFF_FORM",
            "Houve preenchimento de formulário após esta assinatura",
            f"Campos afetados: {', '.join(rep.changed_fields) or 'não identificados'}."))
    elif "ANNOTATIONS" in lvl:
        rep.findings.append(Finding("ATENCAO", "DIFF_ANNOT",
                                    "Anotações foram acrescentadas após esta assinatura", ""))
    else:
        rep.findings.append(Finding(
            "ALERTA", "DIFF_SUSPECT",
            f"Alterações posteriores classificadas pelo pyHanko como '{lvl}'",
            "Nível fora das categorias NONE, LTA_UPDATES, FORM_FILLING e ANNOTATIONS."))

    rep.docmdp = safe(lambda: sig.docmdp_level and int(sig.docmdp_level))
    rep.fieldmdp = safe(lambda: sig.fieldmdp is not None, False)
    if obj_type == "/Sig":
        if rep.docmdp is None:
            rep.findings.append(Finding(
                "INFO", "NO_DOCMDP",
                "Assinatura de aprovação: ausente /Reference com TransformMethod "
                "/DocMDP",
                "O documento não declara restrição de alterações."))
        else:
            nivel_txt = {1: "nenhuma alteração permitida",
                         2: "permite apenas preenchimento de formulário",
                         3: "permite preenchimento e anotações"}.get(rep.docmdp, "")
            quebrada = (rep.digest_ok is False or rep.orphan
                        or rep.alignment.get("aligned") is False)
            if quebrada:
                rep.findings.append(Finding(
                    "CRITICO", "DOCMDP_VIOLATED",
                    f"Estado do arquivo incompatível com a restrição DocMDP "
                    f"nível {rep.docmdp} declarada na assinatura",
                    f"O /TransformParams declara /P {rep.docmdp} ({nivel_txt}). O "
                    f"estado atual do arquivo não é compatível com essa restrição."))
            else:
                rep.findings.append(Finding(
                    "OK", "DOCMDP",
                    f"Assinatura de certificação com DocMDP nível {rep.docmdp}",
                    nivel_txt))

    # ---- nível PAdES -----------------------------------------------------
    rep.pades_level, rep.pades_note = pades_level(rep, dss, harvest)
    return rep

def pades_level(rep: SigReport, dss: DSSReport, harvest: Harvest,
                has_doctimestamp: bool = False) -> Tuple[str, str]:
    if rep.obj_type == "/DocTimeStamp":
        return "—", "Objeto /DocTimeStamp."
    has_t = any(t.kind == "signature-time-stamp" and t.sig_ok for t in rep.timestamps)
    if not has_t:
        return "B-B", ("Ausente carimbo de tempo verificado.")
    chain_ok = all(l.verified for l in rep.chain_links if l.verified is not None) \
        and not any(l.issuer is None for l in rep.chain_links)
    revinfo_ok = rep.revocation.get("checked") and all(
        t.revocation.get("checked") for t in rep.timestamps if t.tsa_cert is not None)
    if dss.present and dss.has_certs and chain_ok and revinfo_ok:
        if has_doctimestamp:
            return "B-LTA", ("Material de validação completo no DSS e selado por "
                             "carimbo de tempo de documento — perfil de arquivamento "
                             "de longo prazo.")
        return "B-LT", ("Material de validação completo arquivado no DSS "
                        "(cadeia + revogação de todas as cadeias).")
    if dss.present:
        faltas = []
        if not dss.has_certs:
            faltas.append("a cadeia de certificados no DSS")
        if not chain_ok:
            faltas.append("a cadeia completa e verificável")
        if not rep.revocation.get("checked"):
            faltas.append("a informação de revogação do certificado do signatário")
        if any(not t.revocation.get("checked")
               for t in rep.timestamps if t.tsa_cert is not None):
            faltas.append("a informação de revogação da cadeia da ACT")
        nivel = "B-T" if not has_doctimestamp else "B-LTA (requisitos não satisfeitos)"
        return nivel, ("Há carimbo de tempo válido e material de validação "
                       "parcialmente arquivado; falta " + "; ".join(faltas) + ".")
    return "B-T", ("Há carimbo de tempo válido, mas nenhum material de validação "
                   "arquivado no documento (sem DSS).")

# ----------------------------------------------------------------------------
# Análise do documento
# ----------------------------------------------------------------------------

@dataclass
class DocReport:
    path: str = ""
    size: int = 0
    sha256: str = ""
    sha512: str = ""
    pdf_version: str = ""
    n_pages: Optional[int] = None
    producer: Optional[str] = None
    creator: Optional[str] = None
    title: Optional[str] = None
    creation_date: Optional[str] = None
    mod_date: Optional[str] = None
    pdfa_claim: Optional[str] = None
    extension_level: Optional[str] = None
    sig_flags: Optional[int] = None
    has_perms: bool = False
    encrypted: bool = False
    n_revisions: int = 0
    n_startxref: int = 0
    empty_sig_fields: List[str] = dc_field(default_factory=list)
    findings: List[Finding] = dc_field(default_factory=list)

def analyze_document(reader: PdfFileReader, data: bytes, path: str) -> DocReport:
    d = DocReport(path=path, size=len(data),
                  sha256=hashlib.sha256(data).hexdigest().upper(),
                  sha512=hashlib.sha512(data).hexdigest().upper())
    d.pdf_version = safe(lambda: data[:16].split(b"\n")[0].decode("latin-1").strip(), "?")
    d.n_pages = safe(lambda: reader.root["/Pages"]["/Count"])
    d.n_revisions = reader.xrefs.total_revisions
    d.n_startxref = data.count(b"startxref")
    d.encrypted = bool(safe(lambda: reader.security_handler is not None, False))

    info = safe(lambda: reader.trailer["/Info"])
    if info is not None:
        info = info.get_object()
        d.producer = safe(lambda: str(info["/Producer"]))
        d.creator = safe(lambda: str(info["/Creator"]))
        d.title = safe(lambda: str(info["/Title"]))
        d.creation_date = safe(lambda: str(info["/CreationDate"]))
        d.mod_date = safe(lambda: str(info["/ModDate"]))

    md = safe(lambda: reader.root["/Metadata"])
    if md is not None:
        xmp = safe(lambda: md.get_object().data, b"") or b""
        txt = xmp.decode("utf-8", "ignore")
        part = conf = None
        for token, target in (("pdfaid:part='", "part"), ('pdfaid:part="', "part"),
                              ("pdfaid:conformance='", "conf"),
                              ('pdfaid:conformance="', "conf")):
            if token in txt:
                val = txt.split(token, 1)[1][:3].split(token[-1])[0]
                if target == "part":
                    part = val
                else:
                    conf = val
        if part:
            d.pdfa_claim = f"PDF/A-{part}{conf or ''}"

    ext = safe(lambda: reader.root["/Extensions"])
    if ext is not None:
        try:
            parts = []
            for k, v in ext.get_object().items():
                v = v.get_object()
                parts.append(f"{str(k).lstrip('/')} base {v.get('/BaseVersion')} "
                             f"nível {v.get('/ExtensionLevel')}")
            d.extension_level = "; ".join(parts)
        except Exception:
            pass

    acro = safe(lambda: reader.root["/AcroForm"])
    if acro is not None:
        d.sig_flags = safe(lambda: int(acro.get_object()["/SigFlags"]))
    d.has_perms = "/Perms" in reader.root

    # campos de assinatura existentes mas NÃO preenchidos
    empty: List[str] = []
    if acro is not None:
        def walk_fields(arr, depth=0):
            if depth > 6 or arr is None:
                return
            for ref in arr:
                f = safe(lambda: ref.get_object())
                if f is None:
                    continue
                if str(safe(lambda: f.get("/FT"), "")) == "/Sig" and "/V" not in f:
                    empty.append(str(safe(lambda: f.get("/T"), "<sem nome>")))
                walk_fields(safe(lambda: f.get("/Kids")), depth + 1)
        walk_fields(safe(lambda: acro.get_object().get("/Fields")))
    d.empty_sig_fields = empty
    if empty:
        d.findings.append(Finding(
            "INFO", "EMPTY_SIG_FIELDS",
            f"Há {len(empty)} campo(s) de assinatura ainda NÃO preenchido(s)",
            f"Campos: {', '.join(empty)}. Nenhum possui entrada /V."))

    if d.encrypted:
        d.findings.append(Finding("ATENCAO", "ENCRYPTED",
                                  "O PDF está cifrado/protegido por senha", ""))
    if d.n_startxref != d.n_revisions:
        d.findings.append(Finding(
            "INFO", "XREF_COUNT",
            f"O arquivo tem {d.n_startxref} marcas 'startxref' e "
            f"{d.n_revisions} revisões reconhecidas", ""))
    return d

def check_acroform_coherence(reader: PdfFileReader, reader_hist: PdfFileReader,
                             n_found: int, n_orphans: int) -> List[Finding]:
    """
    Cruza o que o AcroForm declara com o que existe de fato.

    Um /SigFlags anunciando que há assinaturas, com /Fields vazio, é a marca
    típica de um arquivo que foi assinado e depois reprocessado por uma
    ferramenta que descartou o campo — deixando a assinatura órfã.
    """
    out: List[Finding] = []
    acro = safe(lambda: reader.root["/AcroForm"])
    fields = []
    sigflags = None
    if acro is not None:
        acro = acro.get_object()
        sigflags = safe(lambda: int(acro["/SigFlags"]))
        fields = list(safe(lambda: acro["/Fields"], []) or [])

    if sigflags is not None and (sigflags & 1) and not fields and n_found:
        out.append(Finding(
            "CRITICO", "ACROFORM_GUTTED",
            "/SigFlags declara existência de assinaturas e /Fields está vazio",
            "O bit 1 de /SigFlags indica a existência de assinaturas; o array "
            "/Fields do AcroForm não contém elementos."))

    # histórico do AcroForm
    hist = []
    for rev in range(reader_hist.xrefs.total_revisions):
        for ref in (safe(lambda: reader_hist.xrefs.explicit_refs_in_revision(rev), []) or []):
            obj = safe(lambda: reader_hist.get_object(ref, revision=rev))
            if isinstance(obj, generic.DictionaryObject) and "/Fields" in obj \
                    and ("/SigFlags" in obj or "/DA" in obj):
                n = len(safe(lambda: obj["/Fields"], []) or [])
                hist.append((rev + 1, n, safe(lambda: int(obj["/SigFlags"]))))
    if hist:
        desc = "; ".join(f"revisão {r}: {n} campo(s), SigFlags={f}" for r, n, f in hist)
        out.append(Finding("INFO", "ACROFORM_HISTORY",
                           "Evolução do formulário ao longo das revisões", desc))

    if n_orphans:
        out.append(Finding(
            "ALERTA", "ORPHAN_COUNT",
            f"{n_orphans} assinatura(s) localizada(s) apenas por varredura direta "
            f"de objetos",
            "Não são alcançáveis pelo caminho AcroForm → /Fields → /V."))
    return out

def check_dss_history(dss: DSSReport, history: List[Tuple[int, List[str]]],
                      harvest: Harvest) -> List[Finding]:
    out: List[Finding] = []
    if not history:
        return out
    dss.history = [f"revisão {rev}: DSS com {', '.join(keys)}" for rev, keys in history]
    had_certs = [rev for rev, keys in history if "/Certs" in keys]
    if had_certs and not dss.has_certs:
        orphan = [c for c in harvest.cert_list
                  if "objeto" in harvest.cert_origin(c)
                  and "DSS" not in harvest.cert_origin(c)]
        out.append(Finding(
            "ALERTA", "DSS_CERTS_DROPPED",
            f"O DSS continha /Certs na revisão {', '.join(map(str, had_certs))} e "
            f"não contém na revisão final",
            f"O array /Certs não consta no DSS da revisão final. Os {len(orphan)} "
            f"fluxo(s) de certificado permanecem no arquivo como objetos não "
            f"referenciados pelo catálogo."))
    return out

def check_lta_seal(sigs: List[SigReport], dss: DSSReport) -> List[Finding]:
    """Verifica se o material de LTV está selado por carimbo de documento."""
    out: List[Finding] = []
    doctss = [s for s in sigs if s.obj_type == "/DocTimeStamp"]
    approvals = [s for s in sigs if s.obj_type != "/DocTimeStamp"]
    if not approvals:
        return out
    if not doctss:
        if dss.present:
            out.append(Finding(
                "ALERTA", "DSS_UNSEALED",
                "O DSS não está coberto por carimbo de tempo de documento",
                "O DSS foi gravado em revisão posterior à assinada e não está "
                "contido em nenhum /ByteRange do arquivo. O perfil PAdES B-LTA "
                "(ETSI EN 319 142-1) requer /DocTimeStamp cobrindo o DSS."))
        else:
            out.append(Finding("INFO", "NO_LTA",
                               "Ausente /DocTimeStamp no documento", ""))
    else:
        last = max(doctss, key=lambda s: s.signed_revision)
        out.append(Finding(
            "OK", "LTA_SEAL",
            f"Há {len(doctss)} carimbo(s) de tempo de documento selando o material "
            f"de validação (padrão PAdES B-LTA)",
            f"O último cobre até a revisão {last.signed_revision + 1}."))
    return out

def detect_content_replacement(reader_hist: PdfFileReader
                               ) -> Tuple[List[str], List[Finding]]:
    """Páginas cujo fluxo de conteúdo foi trocado entre a primeira e a última revisão."""
    notas: List[str] = []
    findings: List[Finding] = []
    total = reader_hist.xrefs.total_revisions
    if total < 2:
        return notas, findings
    trocadas = []
    for rev in range(total):
        for ref in (safe(lambda: reader_hist.xrefs.explicit_refs_in_revision(rev), []) or []):
            obj = safe(lambda: reader_hist.get_object(ref, revision=rev))
            if not isinstance(obj, generic.DictionaryObject):
                continue
            if str(safe(lambda: obj.get("/Type"), "")) != "/Page":
                continue
            antes = safe(lambda: reader_hist.get_object(ref, revision=rev - 1)) if rev else None
            if antes is None:
                continue
            a = safe(lambda: antes.raw_get("/Contents"))
            b = safe(lambda: obj.raw_get("/Contents"))
            ia = getattr(a, "idnum", None)
            ib = getattr(b, "idnum", None)
            if ia is not None and ib is not None and ia != ib:
                trocadas.append((ref.idnum, rev + 1, ia, ib))
    for objnum, rev, ia, ib in trocadas:
        notas.append(f"página (objeto {objnum}) teve o fluxo de conteúdo trocado na "
                     f"revisão {rev}: {ia} → {ib}")
    if trocadas:
        findings.append(Finding(
            "ALERTA", "PAGE_CONTENT_REPLACED",
            f"O fluxo de conteúdo de {len(trocadas)} página(s) foi SUBSTITUÍDO em "
            f"revisão posterior",
            "Não se trata de anotação nem de preenchimento de campo: o texto "
            "desenhado na página passou a vir de outro objeto. Isso é típico de um "
            "programa que reescreve o documento inteiro (e, nesse processo, descarta "
            "assinaturas). Compare visualmente as versões antes de assumir que o "
            "conteúdo é o mesmo. Páginas afetadas: "
            + "; ".join(f"objeto {n} (revisão {r})" for n, r, _, _ in trocadas) + "."))
    return notas, findings

def detect_govbr(cert: Optional[x509.Certificate]) -> Optional[Finding]:
    """Distingue assinatura avançada gov.br de certificado qualificado ICP-Brasil."""
    if cert is None:
        return None
    org = str(safe(lambda: cert.issuer.native.get("organization_name"), "") or "")
    cn = str(safe(lambda: cert.issuer.native.get("common_name"), "") or "")
    pols = []
    try:
        pols = [p["policy_identifier"].dotted for p in (cert.certificate_policies_value or [])]
    except Exception:
        pass
    govbr = ("gov-br" in org.lower() or "governo federal do brasil" in cn.lower()
             or any(p.startswith("2.16.76.3.") for p in pols))
    if not govbr:
        return None
    return Finding(
        "ATENCAO", "GOVBR_ADVANCED_SIGNATURE",
        "Assinatura produzida pelo gov.br (assinatura eletrônica AVANÇADA), não por "
        "certificado qualificado ICP-Brasil",
        "O certificado é emitido pela hierarquia do Governo Federal (gov.br), "
        "distinta da ICP-Brasil. Pela Lei 14.063/2020 é assinatura avançada: tem "
        "valor jurídico e presunção de autoria perante os órgãos públicos, mas não "
        "goza da presunção do art. 10, §1º da MP 2.200-2/2001, reservada à "
        "assinatura qualificada. Entre particulares, sua eficácia depende de o uso "
        "ser admitido pelas partes (art. 4º, II da Lei 14.063/2020). Certificados "
        "gov.br são de curta duração e emitidos no ato da assinatura.")

# ----------------------------------------------------------------------------
# Relatório em Markdown
# ----------------------------------------------------------------------------

def yn(v: Optional[bool], yes="Sim", no="Não", unknown="Não apurado") -> str:
    if v is None:
        return unknown
    return yes if v else no

class ReportWriter:
    def __init__(self, doc: DocReport, sigs: List[SigReport], dss: DSSReport,
                 revs: List[RevisionReport], harvest: Harvest,
                 extra: List[Finding], args):
        self.doc, self.sigs, self.dss = doc, sigs, dss
        self.revs, self.harvest, self.extra, self.args = revs, harvest, extra, args
        self.lines: List[str] = []
        self.tz = args.tz

    # -- helpers ---------------------------------------------------------
    def w(self, s: str = ""):
        self.lines.append(s)

    def h(self, level: int, text: str):
        self.w()
        self.w("#" * level + " " + text)
        self.w()

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[str]]):
        self.w("| " + " | ".join(headers) + " |")
        self.w("|" + "|".join(["---"] * len(headers)) + "|")
        for r in rows:
            cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in r]
            self.w("| " + " | ".join(cells) + " |")
        self.w()

    def bullets(self, items: Sequence[str]):
        for i in items:
            self.w(f"- {i}")
        self.w()

    def dt(self, d) -> str:
        return fmt_dt(d, self.tz)

    def all_findings(self) -> List[Finding]:
        out = list(self.doc.findings) + list(self.dss.findings) + list(self.extra)
        for s in self.sigs:
            for f in s.findings:
                f.scope = f"assinatura #{s.index} ({s.field_name})"
                out.append(f)
            for t in s.timestamps:
                for f in t.findings:
                    f.scope = f"carimbo de {s.field_name} ({t.kind})"
                    out.append(f)
        return out

    # -- seções ----------------------------------------------------------
    def build(self) -> str:
        self.header()
        self.summary_section()
        self.document_section()
        for s in self.sigs:
            self.signature_section(s)
        self.ltv_section()
        self.revisions_section()
        self.material_section()
        self.findings_section()
        return "\n".join(self.lines).rstrip() + "\n"

    def header(self):
        self.w("# Relatório — assinaturas digitais em PDF")
        self.w()
        self.w(f"**Arquivo analisado:** `{os.path.basename(self.doc.path)}`  ")
        self.w(f"**Tamanho:** {thousands(self.doc.size)} bytes "
               f"({human_bytes(self.doc.size)})  ")
        self.w(f"**SHA-256 do arquivo:** `{self.doc.sha256}`  ")
        self.w(f"**SHA-512 do arquivo:** `{self.doc.sha512}`  ")
        self.w(f"**Análise realizada em:** "
               f"{self.dt(datetime.datetime.now(datetime.timezone.utc))}  ")
        self.w(f"**Ferramenta:** pdfsig_forense.py v{VERSION} "
               f"(pyHanko + asn1crypto + cryptography)  ")
        mode = "offline (sem consulta à rede)" if not self.args.fetch else \
            "online (consultas AIA/LCR/OCSP habilitadas)"
        self.w(f"**Modo:** {mode}")

    def summary_section(self):
        self.h(2, "1. Resumo")
        approvals = [s for s in self.sigs if s.obj_type != "/DocTimeStamp"]
        if not self.sigs:
            self.w("**O arquivo NÃO contém assinatura digital alguma.** Não há campo "
                   "de assinatura preenchido no AcroForm nem dicionário `/Sig`. "
                   "Eventuais imagens de assinatura, selos ou textos como "
                   "\"documento assinado eletronicamente\" impressos na página são "
                   "meramente gráficos, sem qualquer valor criptográfico.")
            return

        rows = []
        rows.append(["Assinaturas encontradas",
                     f"{len(approvals)} assinatura(s) + "
                     f"{len(self.sigs) - len(approvals)} carimbo(s) de documento"])
        for s in self.sigs:
            tag = f"#{s.index} `{s.field_name}`"
            titular = s.signer_info.get("cn", "—") if s.signer_info else "—"
            rows.append([f"{tag} — titular", titular])
            rows.append([f"{tag} — assinatura do bloco CMS × chave pública do certificado",
                         "**Confere**" if s.math_ok else
                         ("**NÃO confere**" if s.math_ok is False else "não apurada")])
            rows.append([f"{tag} — messageDigest × conteúdo do intervalo assinado",
                         "**Confere**" if s.digest_ok else
                         ("**NÃO confere**" if s.digest_ok is False
                          else "não apurável")])
            ts = [t for t in s.timestamps if t.gen_time]
            rows.append([f"{tag} — carimbo de tempo",
                         self.dt(ts[0].gen_time) if ts else "ausente"])
            rows.append([f"{tag} — nº de série nas LCRs do arquivo",
                         "**consta como revogado**" if s.revocation.get("revoked")
                         else ("não consta" if s.revocation.get("checked")
                               else "não apurado — sem LCR do emissor")])
            rows.append([f"{tag} — nível PAdES", s.pades_level])
            if s.orphan:
                rows.append([f"{tag} — registrada em /AcroForm /Fields", "**Não**"])
        self.table(["Item", "Resultado"], rows)

        counts: Dict[str, int] = {}
        for f in self.all_findings():
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.table(["Categoria de constatação", "Quantidade"],
                   [[SEVERITY_LABEL[k], counts[k]]
                    for k in ("CRITICO", "ALERTA", "ATENCAO", "OK", "INFO")
                    if counts.get(k)])
        self.w("O conteúdo de cada constatação está na seção 7.")

    def document_section(self):
        d = self.doc
        self.h(2, "2. Estrutura do documento")
        self.table(["Campo", "Valor"], [
            ["Versão do PDF", d.pdf_version],
            ["Páginas", d.n_pages if d.n_pages is not None else "?"],
            ["Revisões (atualizações incrementais)", d.n_revisions],
            ["Cifrado", yn(d.encrypted)],
            ["Conformidade declarada", d.pdfa_claim or "nenhuma declaração PDF/A"],
            ["Nível de extensão", d.extension_level or "—"],
            ["/SigFlags do AcroForm", d.sig_flags if d.sig_flags is not None else "—"],
            ["/Perms", yn(d.has_perms)],
            ["Campos de assinatura sem /V",
             ", ".join(d.empty_sig_fields) if d.empty_sig_fields else "nenhum"],
            ["Producer", d.producer or "—"],
            ["Creator", d.creator or "—"],
            ["Título", d.title or "—"],
            ["Criação declarada", d.creation_date or "—"],
            ["Modificação declarada", d.mod_date or "—"],
        ])

    def signature_section(self, s: SigReport):
        kind = ("Carimbo de tempo de documento" if s.obj_type == "/DocTimeStamp"
                else "Assinatura")
        obj = f" (objeto {s.obj_idnum})" if s.obj_idnum is not None else ""
        self.h(2, f"3.{s.index} {kind} #{s.index}{obj} — campo `{s.field_name}`")
        if s.orphan:
            self.w("> " + s.orphan_reason + " O bloco foi localizado por "
                   "varredura direta dos objetos do arquivo.")
            self.w()

        self.h(3, f"3.{s.index}.1 Estrutura no PDF")
        rows = [
            ["/Filter", s.filt],
            ["/SubFilter", s.subfilter],
            ["Tipo", s.obj_type],
            ["Hora autodeclarada (/M)", s.declared_time or "—"],
            ["/Reason", s.reason or "—"],
            ["/Location", s.location or "—"],
            ["/ContactInfo", s.contact or "—"],
            ["/Name", s.name_entry or "—"],
            ["/ByteRange", str(s.byte_range)],
            ["Bytes assinados", f"{thousands(s.covered_bytes)} de "
                                f"{thousands(s.file_size)}"],
            ["Bytes após o trecho assinado", f"{thousands(s.tail_bytes)} "
                                             f"({human_bytes(s.tail_bytes)})"],
            ["Espaço reservado ao /Contents", f"{thousands(s.placeholder_bytes)} bytes "
                                              f"(CMS real: {thousands(s.cms_der_bytes)} bytes)"],
            ["Cobertura (pyHanko)", s.coverage_level],
            ["Revisão assinada", f"{s.signed_revision + 1} de {s.total_revisions}"],
        ]
        if s.obj_idnum is not None:
            rows.insert(0, ["Objeto /Sig", f"{s.obj_idnum} 0 obj"])
        if s.widget_idnum is not None:
            rows.insert(1, ["Widget /Annot que o referencia", f"{s.widget_idnum} 0 obj"])
        if s.alignment:
            al = s.alignment
            rows.append(["/ByteRange alinhado com a assinatura?",
                         yn(al.get("aligned"), "Sim", "**NÃO**")])
            if al.get("shift"):
                rows.append(["Deslocamento físico detectado",
                             f"{al['shift']:+d} bytes"])
            rows.append(["Trecho assinado termina em %%EOF?",
                         yn(al.get("ends_at_eof"))])
        self.table(["Campo", "Valor"], rows)

        self.h(3, f"3.{s.index}.2 Verificações criptográficas")
        if s.digest_ok is not None:
            self.w("```")
            self.w(f"{algo_label(s.digest_algo)} do ByteRange (recalculado): {s.digest_found}")
            self.w(f"messageDigest declarado no CMS:      {s.digest_expected}")
            self.w("→ " + ("idênticos" if s.digest_ok else "divergentes"))
            self.w("```")
        self.w(f"Assinatura do campo signedAttrs ({s.sig_algo}) verificada com a "
               f"chave pública do certificado: "
               f"**{'confere' if s.math_ok else 'não confere' if s.math_ok is False else 'não apurada'}**"
               + (f" ({s.math_note})" if s.math_note else "") + ".")
        self.w()
        self.w(f"CMS: {'destacado (detached)' if s.detached else 'com conteúdo embutido'}, "
               f"{s.n_certs_in_cms} certificado(s) embutido(s).")
        self.w()
        self.w("**Atributos assinados:** " + (", ".join(
            f"`{k}`" + (f" ×{v}" if v > 1 else "") for k, v in s.signed_attrs.items())
            or "nenhum"))
        self.w()
        self.w("**Atributos não assinados:** " + (", ".join(
            f"`{k}`" + (f" ×{v}" if v > 1 else "") for k, v in s.unsigned_attrs.items())
            or "nenhum"))
        self.w()

        if s.signer_cert is not None:
            self.cert_block(s, f"3.{s.index}.3")
        if s.chain_links:
            self.chain_block(s, f"3.{s.index}.4")
        self.revocation_block(s, f"3.{s.index}.5")
        if s.timestamps:
            self.timestamp_block(s, f"3.{s.index}.6")
        if s.path_results:
            self.h(3, f"3.{s.index}.7 Validação de caminho de certificação")
            self.table(["Cenário", "Resultado"],
                       [[k, v] for k, v in s.path_results.items()])

    def cert_block(self, s: SigReport, num: str):
        i = s.signer_info
        self.h(3, f"{num} Certificado do signatário")
        self.table(["Campo", "Valor"], [
            ["Titular (subject)", i["subject"]],
            ["Emissor (issuer)", i["issuer"]],
            ["Nº de série", f"{i['serial_hex']} ({i['serial_dec']})"],
            ["Validade", f"{self.dt(i['not_before'])} → {self.dt(i['not_after'])}"],
            ["Chave", i["key"]],
            ["Algoritmo de assinatura do certificado", i["sig_algo"]],
            ["SHA-256 fingerprint", f"`{i['sha256']}`"],
            ["SHA-1 fingerprint", f"`{i['sha1']}`"],
            ["keyUsage", ", ".join(i["key_usage"]) or "—"],
            ["extendedKeyUsage", ", ".join(i["eku"]) or "—"],
            ["Pontos de distribuição de LCR", "; ".join(i["crl_urls"]) or "—"],
            ["OCSP", "; ".join(i["ocsp_urls"]) or "**nenhum responder OCSP declarado**"],
            ["AIA", "; ".join(i["aia"]) or "—"],
        ])
        if i["policies"]:
            self.w("**Políticas de certificado:**")
            self.bullets([
                f"`{p['oid']}`" + (f" — {p['meaning']}" if p["meaning"] else "")
                + (f" (DPC: {p['cps']})" if p["cps"] else "")
                for p in i["policies"]])
        if i["san_icpbr"]:
            self.w("**Campos ICP-Brasil no subjectAltName:**")
            self.bullets([
                f"`{e['oid']}` — {e['label']}: {e['value']}"
                + ("  _(dígitos ocultados por privacidade; use `--no-redact` para "
                   "exibir)_" if e["sensitive"] and self.args.redact else "")
                for e in i["san_icpbr"]])
        if i["san_other"]:
            self.w("**Outros nomes alternativos:** " + "; ".join(i["san_other"]))
            self.w()

    def chain_block(self, s: SigReport, num: str):
        self.h(3, f"{num} Cadeia de certificação")
        self.w("```")
        for depth, c in enumerate(reversed(s.chain)):
            prefix = "" if depth == 0 else "  " * (depth - 1) + "  └─ "
            self.w(f"{prefix}{cn_of(c)}"
                   f"   [série 0x{c.serial_number:X}, {key_description(c)}]")
        self.w("```")
        rows = []
        for l in s.chain_links:
            rows.append([
                cn_of(l.child),
                cn_of(l.issuer) if l.issuer is not None else "— ausente no arquivo —",
                "verificado" if l.verified else ("NÃO CONFERE" if l.verified is False
                                                 else "não apurado"),
                l.note or "",
            ])
        self.table(["Certificado", "Emissor", "Vínculo criptográfico", "Observação"], rows)
        root = s.chain[-1] if s.chain else None
        if root is not None and root.self_signed in ("yes", "maybe"):
            self.w(f"A âncora encontrada é **{cn_of(root)}**, com SHA-256 "
                   f"`{fp(root)}`.")

            self.w()

    def revocation_block(self, s: SigReport, num: str):
        self.h(3, f"{num} Situação de revogação")
        r = s.revocation
        if not r.get("checked"):
            self.w("Não há LCR nem resposta OCSP, no arquivo ou no material fornecido, "
                   "cujo emissor coincida com o emissor do certificado do signatário. "
                   "**A situação de revogação não pôde ser aferida offline.**")
            self.w()
            return
        self.w(f"Instante de referência: **{self.dt(s.reference_time)}** "
               f"(origem: {s.reference_source}).")
        self.w()
        self.table(["LCR (emissor)", "thisUpdate", "nextUpdate", "Entradas revogadas",
                    "Vigente na referência", "Tamanho"],
                   [[c["issuer"], self.dt(c["this_update"]), self.dt(c["next_update"]),
                     thousands(c["entries"]), yn(c["fresh_at_moment"]),
                     human_bytes(c["size"])]
                    for c in r["matching_crls"]])
        if r["revoked"]:
            self.w(f"O certificado consta como revogado em "
                   f"{self.dt(r['revocation_date'])}"
                   f"{', motivo declarado: ' + str(r['reason']) if r.get('reason') else ''}.")
        else:
            self.w("O número de série do certificado **não consta** nas listas de "
                   "revogação examinadas.")
        self.w()

    def timestamp_block(self, s: SigReport, num: str):
        self.h(3, f"{num} Carimbo(s) de tempo")
        for k, t in enumerate(s.timestamps, 1):
            self.w(f"**Carimbo {k} — tipo `{t.kind}`**")
            self.w()
            self.table(["Campo", "Valor"], [
                ["Instante atestado (genTime)", self.dt(t.gen_time)],
                ["Política de carimbo", (f"`{t.policy}`" +
                                         (f" — {policy_meaning(t.policy)}"
                                          if t.policy and policy_meaning(t.policy) else ""))
                 if t.policy else "—"],
                ["Nº de série do carimbo", t.serial or "—"],
                ["Algoritmo do messageImprint", algo_label(t.imprint_algo)],
                ["Precisão declarada", t.accuracy or "não declarada"],
                ["Nonce", t.nonce or "ausente"],
                ["Nome da ACT no token", t.tsa_name or "—"],
                ["Alvo carimbado", t.imprint_target],
                ["O imprint confere com o alvo?",
                 yn(t.imprint_matches, "**Sim**", "**NÃO**")],
                ["Assinatura do token", yn(t.sig_ok, "**válida**", "**INVÁLIDA**")],
                ["EKU exclusivo de timeStamping", yn(t.eku_ok)],
            ])
            if t.tsa_cert is not None:
                self.w(f"Certificado da ACT: **{cn_of(t.tsa_cert)}** — "
                       f"emissor {cn_of(t.tsa_cert) if False else dn(t.tsa_cert.issuer)}, "
                       f"série 0x{t.tsa_cert.serial_number:X}, "
                       f"{key_description(t.tsa_cert)}, validade "
                       f"{self.dt(t.tsa_cert['tbs_certificate']['validity']['not_before'].native)} → "
                       f"{self.dt(t.tsa_cert['tbs_certificate']['validity']['not_after'].native)}, "
                       f"SHA-256 `{fp(t.tsa_cert)}`.")
                self.w()
            if t.chain_links:
                self.w("Cadeia da ACT: " + " ← ".join(
                    cn_of(c) for c in t.chain) + ".")
                bad = [l for l in t.chain_links if l.verified is False]
                missing = [l for l in t.chain_links if l.issuer is None]
                if bad:
                    self.w("⚠ Há vínculo que não confere nessa cadeia.")
                elif missing:
                    self.w("⚠ A cadeia da ACT está incompleta no arquivo.")
                else:
                    self.w("Todos os vínculos da cadeia da ACT foram verificados "
                           "matematicamente.")
                self.w()
            if t.path_results:
                self.table(["Cenário (caminho da ACT)", "Resultado"],
                           [[k2, v2] for k2, v2 in t.path_results.items()])
            for ext in t.extensions:
                self.w(f"**Extensão proprietária no TSTInfo:** `{ext['oid']}` "
                       f"({human_bytes(ext['size'])})"
                       + (f" — {ext['hint']}" if ext["hint"] else ""))
                d = ext.get("details") or {}
                if d:
                    if d.get("times"):
                        janela = " a ".join(self.dt(x) for x in d["times"][:2])
                        self.w(f"  Janela declarada: {janela}.")
                    if d.get("names"):
                        self.w("  Entidades citadas: " + "; ".join(d["names"][:6]) + ".")
                    if d.get("signed"):
                        self.w("  A estrutura é assinada (declaração de sincronismo "
                               "com assinatura própria), o que evidencia auditoria "
                               "externa do relógio da ACT.")
                self.w()

    def ltv_section(self):
        self.h(2, "4. Material de validação de longo prazo (DSS/VRI)")
        d = self.dss
        if not d.present:
            self.w("O documento não possui Document Security Store.")
            self.w()
            return
        self.table(["Item", "Quantidade"], [
            ["Certificados arquivados (/Certs)", d.n_certs],
            ["LCRs arquivadas (/CRLs)", d.n_crls],
            ["Respostas OCSP arquivadas (/OCSPs)", d.n_ocsps],
            ["Entradas /VRI", len(d.vri_keys)],
        ])
        for k, detail in d.vri_detail.items():
            desc = ", ".join(f"{kk}: {vv}" for kk, vv in detail.items()) or "vazia"
            self.w(f"- `/VRI/{k}` → {desc}")
        self.w()
        self.w("Cada chave `/VRI` é o SHA-1 do `/Contents` da assinatura "
               "correspondente (ISO 32000-2, 12.8.4.3).")
        self.w()
        if d.history:
            self.w("**Evolução do DSS ao longo das revisões:**")
            self.bullets(d.history)

    def revisions_section(self):
        self.h(2, "5. Revisões incrementais")

        rows = []
        signed_revs = {s.signed_revision + 1 for s in self.sigs}
        for r in self.revs:
            marca = "sim" if r.index in signed_revs else ""
            rows.append([r.index, thousands(r.n_objects),
                         r.startxref if r.startxref is not None else "—",
                         "; ".join(r.notes) or "objetos diversos", marca])
        self.table(["Rev.", "Objetos gravados", "startxref", "Objetos relevantes gravados", "Assinada"],
                   rows)
        for s in self.sigs:
            if s.tail_bytes:
                self.w(f"Assinatura #{s.index}: cobre até a revisão "
                       f"{s.signed_revision + 1}. Revisões posteriores: "
                       f"{s.total_revisions - s.signed_revision - 1}, somando "
                       f"{human_bytes(s.tail_bytes)}. "
                       f"Classificação automática das diferenças: "
                       f"**{s.modification_level or 'não avaliável automaticamente'}**"

                       + (f"; campos de formulário alterados: "
                          f"{', '.join(s.changed_fields)}" if s.changed_fields else
                          "; nenhum campo de formulário alterado") + ".")
                self.w()

    def material_section(self):
        self.h(2, "6. Material criptográfico presente no arquivo")
        self.w("Resultado da varredura de todos os objetos de todas as revisões, "
               "inclusive os não referenciados pelo catálogo.")
        self.w()
        rows = []
        for c in sorted(self.harvest.cert_list, key=lambda x: cn_of(x)):
            rows.append([cn_of(c), "CA" if c.ca else "folha",
                         f"0x{c.serial_number:X}",
                         self.harvest.cert_origin(c)])
        if rows:
            self.table(["Certificado (CN)", "Tipo", "Série", "Origem no arquivo"], rows)
        rows = []
        for c in self.harvest.crl_list:
            tbs = c["tbs_cert_list"]
            rows.append([dn(tbs["issuer"]), self.dt(tbs["this_update"].native),
                         self.dt(safe(lambda: tbs["next_update"].native)),
                         thousands(len(tbs["revoked_certificates"] or [])),
                         self.harvest.crl_origin(c)])
        if rows:
            self.w("**Listas de certificados revogados (LCR):**")
            self.w()
            self.table(["Emissor", "thisUpdate", "nextUpdate", "Entradas", "Origem"],
                       rows)
        if self.harvest.ocsps:
            self.w(f"**Respostas OCSP encontradas:** {len(self.harvest.ocsps)}.")
            self.w()
        orfaos = [c for c in self.harvest.cert_list
                  if "objeto" in self.harvest.cert_origin(c)
                  and "DSS" not in self.harvest.cert_origin(c)
                  and "CMS" not in self.harvest.cert_origin(c)]
        if orfaos and not self.dss.has_certs:
            self.w(f"{len(orfaos)} certificado(s) constam no arquivo como objetos "
                   f"não referenciados pelo DSS da revisão final.")
            self.w()

    def findings_section(self):
        self.h(2, "7. Constatações")
        fs = sorted(self.all_findings(),
                    key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.code))
        for sev in ("CRITICO", "ALERTA", "ATENCAO", "OK", "INFO"):
            group = [f for f in fs if f.severity == sev]
            if not group:
                continue
            self.h(3, f"7.{SEVERITY_ORDER[sev] + 1} {SEVERITY_LABEL[sev]} "
                      f"({len(group)})")
            for f in group:
                self.w(f"**{f.title}**  ")
                self.w(f"_Escopo: {f.scope} · código: `{f.code}`_")
                if f.detail:
                    self.w()
                    for para in textwrap.wrap(f.detail, 100):
                        self.w(para)
                self.w()

# ----------------------------------------------------------------------------
# Saída JSON
# ----------------------------------------------------------------------------

def to_jsonable(o):
    if isinstance(o, datetime.datetime):
        return o.astimezone(datetime.timezone.utc).isoformat()
    if isinstance(o, bytes):
        return o.hex()
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, x509.Certificate):
        return {"cn": cn_of(o), "serial": f"0x{o.serial_number:X}",
                "sha256": fp(o), "subject": dn(o.subject), "issuer": dn(o.issuer)}
    if isinstance(o, Finding):
        return o.as_dict()
    if hasattr(o, "__dataclass_fields__"):
        return {k: to_jsonable(getattr(o, k)) for k in o.__dataclass_fields__}
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return str(o)

def build_json(doc: DocReport, sigs: List[SigReport], dss: DSSReport,
               revs: List[RevisionReport], harvest: Harvest,
               extra: List[Finding]) -> dict:
    return to_jsonable({
        "ferramenta": f"pdfsig_forense.py v{VERSION}",
        "gerado_em": datetime.datetime.now(datetime.timezone.utc),
        "documento": doc,
        "assinaturas": sigs,
        "dss": dss,
        "revisoes": revs,
        "achados_gerais": extra,
        "material": {
            "certificados": [
                {"cn": cn_of(c), "sha256": fp(c), "serial": f"0x{c.serial_number:X}",
                 "origem": harvest.cert_origin(c), "ca": bool(c.ca)}
                for c in harvest.cert_list],
            "lcrs": [
                {"emissor": dn(c["tbs_cert_list"]["issuer"]),
                 "this_update": c["tbs_cert_list"]["this_update"].native,
                 "next_update": safe(lambda: c["tbs_cert_list"]["next_update"].native),
                 "entradas": len(c["tbs_cert_list"]["revoked_certificates"] or []),
                 "origem": harvest.crl_origin(c)}
                for c in harvest.crl_list],
            "ocsps": len(harvest.ocsps),
        },
    })

# ----------------------------------------------------------------------------
# Âncoras de confiança
# ----------------------------------------------------------------------------

def load_anchors(paths: Sequence[str]) -> List[x509.Certificate]:
    out: List[x509.Certificate] = []
    for p in paths:
        try:
            raw = open(p, "rb").read()
        except OSError as e:
            print(f"[aviso] não foi possível ler a âncora {p}: {e}", file=sys.stderr)
            continue
        if b"-----BEGIN" in raw:
            import base64
            for block in raw.split(b"-----BEGIN CERTIFICATE-----")[1:]:
                b64 = block.split(b"-----END CERTIFICATE-----")[0]
                try:
                    out.append(x509.Certificate.load(base64.b64decode(b64)))
                except Exception:
                    pass
        else:
            try:
                out.append(x509.Certificate.load(raw))
            except Exception:
                # talvez seja um p7b/PKCS#7 com vários certificados
                try:
                    ci = cms.ContentInfo.load(raw)
                    for c in ci["content"]["certificates"]:
                        if c.name == "certificate":
                            out.append(c.chosen)
                except Exception:
                    print(f"[aviso] formato não reconhecido em {p}", file=sys.stderr)
    return out

def self_signed_from_harvest(harvest: Harvest) -> List[x509.Certificate]:
    return [c for c in harvest.cert_list
            if c.self_signed in ("yes", "maybe")
            and c.subject.dump() == c.issuer.dump()]


# ----------------------------------------------------------------------------
# API de biblioteca (ForensicAuth)
# ----------------------------------------------------------------------------

@dataclass
class AnalysisOptions:
    trust_anchors: List[str] = dc_field(default_factory=list)
    fetch: bool = False
    redact: bool = True
    tz: Optional[float] = -3.0
    dump_material_dir: Optional[str] = None
    traceback: bool = False


@dataclass
class AnalysisResult:
    markdown: str
    payload: dict
    findings: List[Finding]
    has_critical: bool
    signed: bool
    signature_count: int
    anchors_from_file: bool
    anchor_mode_label: str
    harvest: Harvest
    doc: DocReport
    sigs: List[SigReport]
    dss: DSSReport


def analyze_pdf_file(pdf_path: str, options: Optional[AnalysisOptions] = None) -> AnalysisResult:
    """Executa a análise completa e devolve relatório Markdown + JSON estruturado.

    Inclui assinaturas registradas no AcroForm e assinaturas órfãs (dicionário
    /Sig ou /ByteRange+/Contents ainda no arquivo, mas fora de /Fields).
    """
    options = options or AnalysisOptions()
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(pdf_path)

    data = open(pdf_path, "rb").read()
    args = argparse.Namespace(
        pdf=pdf_path,
        redact=options.redact,
        fetch=options.fetch,
        tz=options.tz,
        trust_anchor=list(options.trust_anchors or []),
        dump_material=options.dump_material_dir,
        traceback=options.traceback,
        anchor_mode_label="",
    )

    with open(args.pdf, "rb") as fh, open(args.pdf, "rb") as fh_hist:
        reader = PdfFileReader(fh, strict=False)
        reader_hist = PdfFileReader(fh_hist, strict=False)

        doc = analyze_document(reader, data, args.pdf)
        harvest = harvest_from_pdf(reader_hist)
        # Certificados do CMS entram na colheita antes da escolha da âncora.
        # Sem isso, a raiz que só existe dentro da assinatura não vira âncora.
        with open(args.pdf, "rb") as fh_cms:
            reader_cms = PdfFileReader(fh_cms, strict=False)
            for i, sig in enumerate(
                list(safe(lambda: reader_cms.embedded_signatures, []) or []), 1
            ):
                try:
                    harvest_from_cms(sig.signed_data, harvest, f"CMS da assinatura #{i}")
                except Exception:
                    pass
        for idnum, _rev, sdict, _widget, _fname in find_all_signature_dicts(reader_hist):
            raw = safe(lambda sdict=sdict: bytes(sdict["/Contents"]))
            if not raw:
                continue
            try:
                harvest_from_cms(
                    cms.ContentInfo.load(raw)["content"],
                    harvest,
                    f"objeto {idnum}",
                )
            except Exception:
                continue
        dss = analyze_dss(reader, harvest)
        history = dss_history(reader_hist) if dss.present else []
        revs, rev_findings = analyze_revisions(reader_hist)

        anchors = load_anchors(args.trust_anchor)
        anchors_from_file = False
        if not anchors:
            anchors = self_signed_from_harvest(harvest)
            anchors_from_file = bool(anchors)
        if anchors_from_file:
            args.anchor_mode_label = (
                "raiz(es) autoassinada(s) extraída(s) do próprio arquivo "
                "(validação CIRCULAR; compare fingerprints com o ITI)"
            )
        elif anchors:
            args.anchor_mode_label = (
                f"{len(anchors)} raiz(es) externa(s) fornecida(s) "
                "(ex.: ICP-Brasil / ITI; preferível)"
            )
        else:
            args.anchor_mode_label = "nenhuma âncora disponível"

        # assinaturas vistas pelo caminho normal (AcroForm) ...
        embedded = list(safe(lambda: reader.embedded_signatures, []) or [])
        # ... e TODAS as que existem fisicamente no arquivo
        all_dicts = find_all_signature_dicts(reader_hist)
        embedded_contents = set()
        for esig in embedded:
            c = safe(lambda: bytes(esig.sig_object["/Contents"]))
            if c:
                embedded_contents.add(hashlib.sha256(c).digest())

        orphans = []
        for idnum, rev, sdict, widget, fname in all_dicts:
            c = safe(lambda: bytes(sdict["/Contents"]))
            if c and hashlib.sha256(c).digest() in embedded_contents:
                continue          # já coberta pela leitura normal
            orphans.append((idnum, rev, sdict, widget, fname))

        sigs: List[SigReport] = []
        targets: List[Tuple[Any, bool, str, Optional[int], Optional[int]]] = [
            (sig, False, "", None, None) for sig in embedded]
        for idnum, rev, sdict, widget, fname in orphans:
            name = fname or f"<sem campo · objeto {idnum}>"
            if widget is None:
                motivo = (f"O dicionário /Sig (objeto {idnum}) não é referenciado "
                          f"por nenhum campo de assinatura.")
            else:
                motivo = (f"O dicionário /Sig (objeto {idnum}) é referenciado pelo "
                          f"widget /Annot objeto {widget} (campo «{fname}»); esse "
                          f"campo não consta na lista /Fields do AcroForm.")
            targets.append((RawSignatureRef(sdict, idnum, rev, name, widget),
                            True, motivo, idnum, widget))

        for i, (sig, is_orphan, motivo, idnum, widget) in enumerate(targets, 1):
            try:
                rp = analyze_signature(reader, sig, i, data, harvest,
                                       anchors, dss, args)
                rp.orphan, rp.orphan_reason = is_orphan, motivo
                rp.obj_idnum, rp.widget_idnum = idnum, widget
                if is_orphan:
                    rp.findings.append(Finding(
                        "CRITICO", "ORPHAN_SIGNATURE",
                                        "Dicionário de assinatura não referenciado pelo "
                        "AcroForm",
                        motivo + " A enumeração de assinaturas do pyHanko, que "
                        "percorre o AcroForm, retorna zero assinaturas para este "
                        "arquivo."))
                sigs.append(rp)
            except Exception as e:
                if args.traceback:
                    traceback.print_exc()
                rep = SigReport(index=i, field_name=str(safe(lambda: sig.field_name, "?")),
                                obj_type=str(safe(lambda: sig.sig_object_type, "?")))
                rep.findings.append(Finding(
                    "CRITICO", "ANALYSIS_ERROR",
                    "Falha ao analisar esta assinatura",
                    f"{type(e).__name__}: {e}"))
                sigs.append(rep)

        has_dts = any(x.obj_type == "/DocTimeStamp" for x in sigs)
        for x in sigs:
            if x.obj_type != "/DocTimeStamp":
                x.pades_level, x.pades_note = pades_level(x, dss, harvest, has_dts)

        extra = list(rev_findings)
        extra.extend(check_acroform_coherence(
            reader, reader_hist, len(targets), len(orphans)))
        extra.extend(check_dss_history(dss, history, harvest))
        extra.extend(check_lta_seal(sigs, dss))
        for s in sigs:
            if s.obj_type != "/DocTimeStamp":
                extra.extend(find_info_and_metadata_changes(
                    reader_hist, s.signed_revision))
                break
        notas_conteudo, f_conteudo = detect_content_replacement(reader_hist)
        extra.extend(f_conteudo)
        vistos_govbr: set = set()
        for x in sigs:
            g = detect_govbr(x.signer_cert)
            if g and x.signer_cert is not None and \
                    x.signer_cert.sha256 not in vistos_govbr:
                vistos_govbr.add(x.signer_cert.sha256)
                g.scope = f"assinatura #{x.index} ({x.field_name})"
                extra.append(g)
        if not targets:
            extra.append(Finding(
                "ALERTA", "NO_SIGNATURE",
                "Nenhum dicionário de assinatura encontrado no arquivo",
                "A varredura de todos os objetos de todas as revisões não "
                "localizou /Sig nem /DocTimeStamp."))
        if anchors_from_file:
            extra.append(Finding(
                "ATENCAO", "ANCHOR_FROM_FILE",
                "Âncora de confiança extraída do próprio arquivo",
                "A validação de caminho foi executada tomando como âncora um "
                "certificado autoassinado extraído do próprio arquivo. Nenhuma "
                "âncora externa foi fornecida com --trust-anchor."))
        elif anchors:
            extra.append(Finding(
                "OK", "ANCHOR_EXTERNAL",
                f"Validação ancorada em {len(anchors)} raiz(es) fornecida(s) "
                f"externamente", ""))

        if args.dump_material:
            os.makedirs(args.dump_material, exist_ok=True)
            for c in harvest.cert_list:
                name = "".join(ch if ch.isalnum() else "_" for ch in cn_of(c))[:60]
                with open(os.path.join(args.dump_material,
                                       f"cert_{name}_{fp(c)[:12]}.der"), "wb") as f:
                    f.write(c.dump())
            for n, c in enumerate(harvest.crl_list, 1):
                with open(os.path.join(args.dump_material, f"crl_{n}.crl"), "wb") as f:
                    f.write(c.dump())

        writer = ReportWriter(doc, sigs, dss, revs, harvest, extra, args)
        writer.content_notes = notas_conteudo
        report = writer.build()

    findings = writer.all_findings()
    approvals = [s for s in sigs if s.obj_type != "/DocTimeStamp"]
    payload = build_json(doc, sigs, dss, revs, harvest, extra)
    payload["anchor_mode"] = args.anchor_mode_label
    payload["anchors_from_file"] = anchors_from_file
    return AnalysisResult(
        markdown=report,
        payload=payload,
        findings=findings,
        has_critical=any(f.severity == "CRITICO" for f in findings),
        signed=bool(approvals),
        signature_count=len(approvals),
        anchors_from_file=anchors_from_file,
        anchor_mode_label=args.anchor_mode_label or "",
        harvest=harvest,
        doc=doc,
        sigs=sigs,
        dss=dss,
    )


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdfsig_forense.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Análise forense de assinaturas digitais em PDF (PAdES/CAdES), "
                    "com relatório humanizado em Markdown.",
        epilog=textwrap.dedent("""
            Exemplos:
              %(prog)s doc.pdf
              %(prog)s doc.pdf -o relatorio.md --json dados.json
              %(prog)s doc.pdf --trust-anchor raiz-icpbrasil.crt --tz -3
              %(prog)s doc.pdf --no-redact --dump-material ./material
        """).strip())
    ap.add_argument("pdf", help="arquivo PDF a analisar")
    ap.add_argument("-o", "--out", help="grava o relatório Markdown neste arquivo")
    ap.add_argument("--json", dest="json_out", help="grava os dados brutos em JSON")
    ap.add_argument("--trust-anchor", action="append", default=[], metavar="ARQ",
                    help="certificado(s) raiz de confiança (PEM/DER/P7B); pode "
                         "repetir. Sem isso, o script usa as raízes autoassinadas "
                         "encontradas no próprio arquivo e avisa da circularidade")
    ap.add_argument("--fetch", action="store_true",
                    help="permite consultas de rede (AIA, LCR, OCSP) na validação")
    ap.add_argument("--no-redact", dest="redact", action="store_false",
                    help="exibe integralmente CPF/RG/NIS presentes no certificado")
    ap.add_argument("--tz", type=float, default=None, metavar="H",
                    help="fuso horário local para exibir junto do UTC (ex.: -3)")
    ap.add_argument("--dump-material", metavar="DIR",
                    help="extrai para DIR todos os certificados/LCRs encontrados")
    ap.add_argument("--quiet", action="store_true",
                    help="não imprime o relatório no terminal")
    ap.add_argument("--traceback", action="store_true",
                    help="mostra o traceback completo em caso de erro")
    ap.set_defaults(redact=True)
    args = ap.parse_args(argv)

    if not os.path.isfile(args.pdf):
        print(f"erro: arquivo não encontrado: {args.pdf}", file=sys.stderr)
        return 2

    data = open(args.pdf, "rb").read()
    if not data.startswith(b"%PDF"):
        print("aviso: o arquivo não começa com %PDF — pode não ser um PDF válido.",
              file=sys.stderr)

    try:
        result = analyze_pdf_file(
            args.pdf,
            AnalysisOptions(
                trust_anchors=list(args.trust_anchor or []),
                fetch=bool(args.fetch),
                redact=bool(args.redact),
                tz=args.tz,
                dump_material_dir=args.dump_material,
                traceback=bool(args.traceback),
            ),
        )
    except Exception as e:
        if args.traceback:
            traceback.print_exc()
        print(f"erro ao processar o PDF: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    if args.dump_material:
        print(f"[ok] material extraído em {args.dump_material}", file=sys.stderr)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result.markdown)
        print(f"[ok] relatório gravado em {args.out}", file=sys.stderr)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result.payload, f, ensure_ascii=False, indent=2)
        print(f"[ok] JSON gravado em {args.json_out}", file=sys.stderr)
    if not args.quiet and not args.out:
        print(result.markdown)

    if result.has_critical:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Testes de assinaturas digitais PDF (motor pdfsig_forense + pipeline)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from core.job_artifacts import ARTIFACT_MAPPINGS, stage_plugin_artifacts
from core.plugins.pdf_forensic_extract_plugin import PDFForensicExtractPlugin
from forensics.pdf.pdf_forensic_extract import run_pdf_forensic_extract
from forensics.pdf.pdf_signatures import analyze_pdf_signatures


def _write_unsigned_pdf(path: Path, text: str = "unsigned") -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _build_ca_and_leaf():
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subj = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VA Suite Test"),
            x509.NameAttribute(NameOID.COMMON_NAME, "VA Suite Test Root CA"),
        ]
    )
    leaf_subj = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VA Suite Test"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Perito Assinante"),
        ]
    )
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subj)
        .issuer_name(ca_subj)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(leaf_subj)
        .issuer_name(ca_subj)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return ca_cert, leaf, leaf_key


def _sign_pdf(unsigned: Path, signed: Path, tmp_path: Path) -> None:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata

    ca_cert, leaf, leaf_key = _build_ca_and_leaf()
    ca_pem = tmp_path / "ca.pem"
    leaf_pem = tmp_path / "leaf.pem"
    key_pem = tmp_path / "key.pem"
    ca_pem.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    leaf_pem.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_pem.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    signer = signers.SimpleSigner.load(
        str(key_pem),
        str(leaf_pem),
        ca_chain_files=(str(ca_pem),),
    )
    with open(unsigned, "rb") as inf:
        writer = IncrementalPdfFileWriter(inf)
        meta = PdfSignatureMetadata(
            field_name="SigForense",
            reason="Teste VA Suite",
            location="Lab Forense",
            contact_info="forense@example.test",
        )
        with open(signed, "wb") as outf:
            signers.sign_pdf(writer, meta, signer=signer, output=outf)


@pytest.fixture
def signed_pdf_ready(tmp_path: Path) -> Path:
    certs = tmp_path / "signing_material"
    certs.mkdir()
    unsigned = tmp_path / "unsigned.pdf"
    signed = tmp_path / "signed.pdf"
    _write_unsigned_pdf(unsigned, "documento assinado")
    _sign_pdf(unsigned, signed, certs)
    return signed


def test_unsigned_pdf_reports_no_signatures(tmp_path: Path):
    pdf = tmp_path / "plain.pdf"
    _write_unsigned_pdf(pdf)
    out = analyze_pdf_signatures(str(pdf), tmp_path / "sig_out")
    assert out["signed"] is False
    assert out["signature_count"] == 0
    assert out["status"] == "unsigned"
    assert (tmp_path / "sig_out" / "signatures.json").exists()
    report = (tmp_path / "sig_out" / "signatures_report.txt").read_text(encoding="utf-8")
    assert "Relatório técnico" in report or "Relatorio tecnico" in report or "assinatura" in report.lower()


def test_signed_pdf_human_relatorio_and_integrity(signed_pdf_ready: Path, tmp_path: Path, monkeypatch):
    from forensics.pdf import pdf_signatures as ps
    from forensics.pdf import pdfsig_forense as eng

    monkeypatch.setattr(
        ps,
        "_options_from_settings",
        lambda: eng.AnalysisOptions(
            trust_anchors=[],
            fetch=False,
            redact=True,
            tz=-3.0,
        ),
    )

    out_dir = tmp_path / "sig_out"
    out = analyze_pdf_signatures(str(signed_pdf_ready), out_dir)

    assert out["signed"] is True
    assert out["signature_count"] == 1
    assert out["status"] == "ok"
    assert out["engine"] == "pdfsig_forense"
    assert out.get("anchors_from_file") is True

    report = (out_dir / "signatures_report.txt").read_text(encoding="utf-8")
    assert "Relatório técnico" in report
    assert "Veredito resumido" in report or "veredito" in report.lower()
    assert "Perito Assinante" in report or "SigForense" in report
    assert "Íntegra" in report or "Integridade" in report or "integra" in report.lower()
    assert "PAdES" in report or "B-B" in report
    assert (
        "circular" in report.lower()
        or "ANCHOR_FROM_FILE" in report
        or "próprio arquivo" in report
        or "proprio arquivo" in report
    )

    sig = out["signatures"][0]
    assert sig["field_name"] == "SigForense"
    assert sig["digest_ok"] is True
    assert sig["sig_ok"] is True
    assert sig["human_verdict"]["headline"]
    assert (out_dir / "signatures.json").exists()
    pems = list((out_dir / "signatures" / "certs").glob("*.pem"))
    assert len(pems) >= 1


def test_run_extract_pipeline_includes_signatures(signed_pdf_ready: Path, tmp_path: Path):
    out = run_pdf_forensic_extract(str(signed_pdf_ready), tmp_path / "extract")
    assert out["pdf_signed"] is True
    assert out["signature_count"] == 1
    assert Path(out["signatures_json_path"]).exists()
    assert Path(out["signatures_report_path"]).exists()
    assert (tmp_path / "extract" / "signatures" / "certs").is_dir()


def test_plugin_analyze_signed_pdf_e2e(signed_pdf_ready: Path, tmp_path: Path):
    plugin = PDFForensicExtractPlugin()
    result = plugin.analyze(
        str(signed_pdf_ready),
        {"_job_staging_dir": str(tmp_path / "job_artifacts")},
    )
    assert result["success"] is True
    assert result["pdf_signed"] is True
    assert result["signature_count"] == 1
    assert result.get("signatures_json_path")
    assert Path(result["signatures_json_path"]).exists()
    assert Path(result["signatures_report_path"]).exists()
    assert result.get("signatures_headline")
    assert result.get("signatures_pades_level")

    result_dir = tmp_path / "result_dir"
    stage_plugin_artifacts(result, result_dir)
    assert (result_dir / "signatures.json").exists()
    assert (result_dir / "signatures_report.txt").exists()
    assert any(result_dir.rglob("*.pem"))


def test_artifact_mappings_include_signatures():
    keys = {k for k, _ in ARTIFACT_MAPPINGS}
    assert "signatures_json_path" in keys
    assert "signatures_report_path" in keys


def test_unsigned_still_succeeds_in_full_extract(tmp_path: Path):
    pdf = tmp_path / "plain.pdf"
    _write_unsigned_pdf(pdf)
    out = run_pdf_forensic_extract(str(pdf), tmp_path / "out")
    assert out["pdf_signed"] is False
    assert out["signature_count"] == 0
    assert Path(out["signatures_json_path"]).exists()

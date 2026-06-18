"""Relatorio narrativo da cadeia de custodia."""

from services.custody_narrative_report import CustodyNarrativeReportService
from services.custody_service import CustodyService


class TestCustodyNarrativeReport:
    def test_build_and_render(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        path = tmp_path / "ev.jpg"
        path.write_bytes(b"pixel-data")
        import hashlib

        sample_evidence.file_path = str(path)
        sample_evidence.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        db_session.commit()

        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            user_id=test_user.id,
            sha256_input=sample_evidence.sha256,
            details={
                "original_filename": sample_evidence.original_filename,
                "file_type": "imagem",
                "file_size": 10,
                "sha256": sample_evidence.sha256,
            },
        )

        svc = CustodyNarrativeReportService(db_session)
        report = svc.build(sample_case.id)
        assert report["case"]["protocol_number"] == sample_case.protocol_number
        assert len(report["events"]) >= 1
        assert "Evidencia recebida" in report["events"][0]["title"]
        assert any("registrou o recebimento" in p for p in report["events"][0]["paragraphs"])

        html = svc.render_html(report)
        assert "Linha do tempo" in html
        assert sample_case.protocol_number in html

        md = svc.render_markdown(report)
        assert sample_case.protocol_number in md
        assert "## Linha do tempo" in md

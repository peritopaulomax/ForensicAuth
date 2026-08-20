"""Tests for questioned evidence group labels."""

import io

from models.custody_record import CustodyRecord
from models.evidence import Evidence
from services.evidence_classification import (
    group_case_evidences_by_label,
    questioned_group_label,
)
from services.evidence_service import EvidenceService


class TestQuestionedGroupLabel:
    def test_default_sem_rotulo(self, db_session, sample_evidence):
        assert questioned_group_label(sample_evidence) == "Sem rotulo"

    def test_group_case_evidences_by_label(self, db_session, sample_case, test_user, tmp_path):
        service = EvidenceService(db_session)
        for label, name in [("Camera A", "a.jpg"), ("Camera B", "b.jpg"), ("Camera A", "c.jpg")]:
            path = tmp_path / name
            path.write_bytes(b"\xff\xd8\xff\xe0" + name.encode())
            with open(path, "rb") as f:
                service.upload_evidence(
                    case_id=sample_case.id,
                    filename=name,
                    mime_type="image/jpeg",
                    file_obj=f,
                    uploaded_by=test_user.id,
                    extra_metadata={"questioned_group_label": label},
                )

        evidences = (
            db_session.query(Evidence)
            .filter(Evidence.case_id == sample_case.id, Evidence.deleted_at.is_(None))
            .all()
        )
        groups = group_case_evidences_by_label(evidences)
        by_label = {g["group_label"]: len(g["files"]) for g in groups}
        assert by_label["Camera A"] == 2
        assert by_label["Camera B"] == 1

    def test_upload_endpoint_requires_group_label(
        self, client, sample_case, auth_headers
    ):
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        response = client.post(
            "/api/v1/evidences/upload",
            data={"case_id": str(sample_case.id)},
            files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_upload_endpoint_stores_label(self, client, sample_case, auth_headers):
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF labeled"
        response = client.post(
            "/api/v1/evidences/upload",
            data={"case_id": str(sample_case.id), "group_label": "Camera A"},
            files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
            headers=auth_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["group_label"] == "Camera A"
        assert body["extra_metadata"]["questioned_group_label"] == "Camera A"

    def test_patch_group_label_creates_custody(
        self, client, db_session, sample_case, auth_headers
    ):
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF patch"
        upload = client.post(
            "/api/v1/evidences/upload",
            data={"case_id": str(sample_case.id), "group_label": "Antigo"},
            files={"file": ("p.jpg", io.BytesIO(file_content), "image/jpeg")},
            headers=auth_headers,
        )
        assert upload.status_code == 201
        eid = upload.json()["id"]

        patched = client.patch(
            f"/api/v1/evidences/{eid}/group-label",
            json={"group_label": "Novo"},
            headers=auth_headers,
        )
        assert patched.status_code == 200
        assert patched.json()["group_label"] == "Novo"

        records = (
            db_session.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == sample_case.id,
                CustodyRecord.record_type == "evidence_group_label_changed",
            )
            .all()
        )
        assert len(records) == 1
        assert records[0].details["old_group_label"] == "Antigo"
        assert records[0].details["new_group_label"] == "Novo"

    def test_bulk_group_label(self, client, sample_case, auth_headers):
        ids = []
        for i in range(2):
            content = b"\xff\xd8\xff\xe0\x00\x10JFIF bulk" + bytes([i])
            upload = client.post(
                "/api/v1/evidences/upload",
                data={"case_id": str(sample_case.id), "group_label": "X"},
                files={"file": (f"b{i}.jpg", io.BytesIO(content), "image/jpeg")},
                headers=auth_headers,
            )
            assert upload.status_code == 201
            ids.append(upload.json()["id"])

        response = client.post(
            f"/api/v1/cases/{sample_case.id}/evidences/group-label",
            json={"evidence_ids": ids, "group_label": "Y"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert all(item["group_label"] == "Y" for item in response.json())

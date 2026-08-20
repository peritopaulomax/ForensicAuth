"""Resolucao de dependentes de derivacao para exclusao consciente."""

import io
import uuid

import pytest

from models.evidence import Evidence
from services.evidence_dependents import EvidenceDependentsResolver
from services.evidence_service import EvidenceService


def _upload(db_session, case, user, filename, payload) -> Evidence:
    return EvidenceService(db_session).upload_evidence(
        case_id=case.id,
        filename=filename,
        mime_type="image/jpeg",
        file_obj=io.BytesIO(payload),
        uploaded_by=user.id,
    )


def _derivative(db_session, case, user, filename, metadata) -> Evidence:
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        filename=filename,
        original_filename=filename,
        file_path=f"/tmp/{filename}",
        file_size=10,
        file_type="imagem",
        mime_type="image/png",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        uploaded_by=user.id,
        extra_metadata={"origin": "derived", **metadata},
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence


@pytest.fixture
def questioned(db_session, sample_case, test_user):
    return _upload(db_session, sample_case, test_user, "questionado.jpg", b"\xff\xd8\xff\xe0Q")


@pytest.fixture
def reference(db_session, sample_case, test_user):
    return _upload(db_session, sample_case, test_user, "referencia.jpg", b"\xff\xd8\xff\xe0R")


class TestDependentDerivatives:
    def test_parent_inputs_single_parent_is_exclusive(
        self, db_session, sample_case, test_user, questioned
    ):
        derivative = _derivative(
            db_session,
            sample_case,
            test_user,
            "ela.png",
            {
                "technique": "ela",
                "derivation_group_id": "job-1",
                "parent_inputs": [
                    {"evidence_id": str(questioned.id), "role": "questioned"},
                ],
            },
        )

        result = EvidenceDependentsResolver(db_session).dependent_derivatives(
            sample_case.id, [questioned.id]
        )

        assert [item["evidence_id"] for item in result] == [str(derivative.id)]
        assert result[0]["exclusive"] is True
        assert result[0]["retained_parents"] == []
        assert result[0]["derivation_group_id"] == "job-1"

    def test_shared_parents_are_not_exclusive(
        self, db_session, sample_case, test_user, questioned, reference
    ):
        _derivative(
            db_session,
            sample_case,
            test_user,
            "prnu_superficie.html",
            {
                "technique": "prnu",
                "artifact_role": "prnu_correlation_surface",
                "parent_inputs": [
                    {"evidence_id": str(questioned.id), "role": "questioned"},
                    {"evidence_id": str(reference.id), "role": "fingerprint"},
                ],
            },
        )

        result = EvidenceDependentsResolver(db_session).dependent_derivatives(
            sample_case.id, [questioned.id]
        )

        assert len(result) == 1
        assert result[0]["exclusive"] is False
        assert result[0]["retained_parents"] == ["referencia.jpg"]

    def test_shared_parents_become_exclusive_when_both_in_scope(
        self, db_session, sample_case, test_user, questioned, reference
    ):
        _derivative(
            db_session,
            sample_case,
            test_user,
            "prnu_superficie.html",
            {
                "parent_inputs": [
                    {"evidence_id": str(questioned.id), "role": "questioned"},
                    {"evidence_id": str(reference.id), "role": "fingerprint"},
                ],
            },
        )

        result = EvidenceDependentsResolver(db_session).dependent_derivatives(
            sample_case.id, [questioned.id, reference.id]
        )

        assert result[0]["exclusive"] is True

    def test_legacy_parent_evidence_ids_are_resolved(
        self, db_session, sample_case, test_user, questioned
    ):
        _derivative(
            db_session,
            sample_case,
            test_user,
            "legacy.png",
            {"parent_evidence_ids": [str(questioned.id)]},
        )

        result = EvidenceDependentsResolver(db_session).dependent_derivatives(
            sample_case.id, [questioned.id]
        )

        assert len(result) == 1
        assert result[0]["exclusive"] is True

    def test_legacy_single_parent_evidence_id_is_resolved(
        self, db_session, sample_case, test_user, questioned
    ):
        _derivative(
            db_session,
            sample_case,
            test_user,
            "legacy_single.png",
            {"parent_evidence_id": str(questioned.id)},
        )

        result = EvidenceDependentsResolver(db_session).dependent_derivatives(
            sample_case.id, [questioned.id]
        )

        assert len(result) == 1
        assert result[0]["exclusive"] is True

    def test_transitive_chain_is_included(
        self, db_session, sample_case, test_user, questioned
    ):
        first = _derivative(
            db_session,
            sample_case,
            test_user,
            "nivel1.png",
            {"parent_inputs": [{"evidence_id": str(questioned.id), "role": "questioned"}]},
        )
        second = _derivative(
            db_session,
            sample_case,
            test_user,
            "nivel2.png",
            {"parent_inputs": [{"evidence_id": str(first.id), "role": "input"}]},
        )

        result = EvidenceDependentsResolver(db_session).dependent_derivatives(
            sample_case.id, [questioned.id]
        )

        ids = {item["evidence_id"] for item in result}
        assert ids == {str(first.id), str(second.id)}
        assert all(item["exclusive"] for item in result)

    def test_unrelated_derivative_is_ignored(
        self, db_session, sample_case, test_user, questioned, reference
    ):
        _derivative(
            db_session,
            sample_case,
            test_user,
            "outro.png",
            {"parent_inputs": [{"evidence_id": str(reference.id), "role": "input"}]},
        )

        result = EvidenceDependentsResolver(db_session).dependent_derivatives(
            sample_case.id, [questioned.id]
        )

        assert result == []

    def test_preview_counts_packages_and_retained(
        self, db_session, sample_case, test_user, questioned, reference
    ):
        _derivative(
            db_session,
            sample_case,
            test_user,
            "ela_a.png",
            {
                "technique": "ela",
                "derivation_group_id": "job-1",
                "parent_inputs": [{"evidence_id": str(questioned.id), "role": "questioned"}],
            },
        )
        _derivative(
            db_session,
            sample_case,
            test_user,
            "ela_b.png",
            {
                "technique": "ela",
                "derivation_group_id": "job-1",
                "parent_inputs": [{"evidence_id": str(questioned.id), "role": "questioned"}],
            },
        )
        _derivative(
            db_session,
            sample_case,
            test_user,
            "prnu.html",
            {
                "technique": "prnu",
                "derivation_group_id": "job-2",
                "parent_inputs": [
                    {"evidence_id": str(questioned.id), "role": "questioned"},
                    {"evidence_id": str(reference.id), "role": "fingerprint"},
                ],
            },
        )

        preview = EvidenceDependentsResolver(db_session).preview(sample_case.id, [questioned])

        assert preview["dependent_count"] == 3
        assert preview["cascade_count"] == 2
        assert preview["retained_count"] == 1
        assert preview["package_count"] == 1

    def test_deletion_plan_without_cascade_has_no_ids(
        self, db_session, sample_case, test_user, questioned
    ):
        _derivative(
            db_session,
            sample_case,
            test_user,
            "ela.png",
            {"parent_inputs": [{"evidence_id": str(questioned.id), "role": "questioned"}]},
        )

        plan = EvidenceDependentsResolver(db_session).deletion_plan(
            sample_case.id, [questioned.id], include_dependent_derivatives=False
        )

        assert plan["cascade_ids"] == []
        assert len(plan["dependents"]) == 1

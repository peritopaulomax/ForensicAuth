"""Case close/reopen with bilateral signatures and forensic manifest."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from models.case import Case
from models.case_closure import CaseClosure, CaseClosureSignature
from models.case_share import CaseShare
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from models.user import User
from services.case_access import (
    assert_can_close_case,
    assert_can_reopen_case,
    get_accessible_case,
    get_required_closure_signer_ids,
    user_may_sign_closure,
)
from services.custody_service import CustodyService
from services.custody_signing_service import CustodySigningService


class ForensicManifestBuilder:
    """Build canonical manifest JSON and SHA-256 for case closure."""

    @staticmethod
    def canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def hash_manifest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            ForensicManifestBuilder.canonical_json(payload).encode("utf-8")
        ).hexdigest()

    def build(
        self,
        db: Session,
        case: Case,
        *,
        required_signer_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        evidences = (
            db.query(Evidence)
            .filter(Evidence.case_id == case.id, Evidence.deleted_at.is_(None))
            .order_by(Evidence.created_at.asc())
            .all()
        )
        max_seq = (
            db.query(func.max(CustodyRecord.chain_sequence))
            .filter(CustodyRecord.case_id == case.id)
            .scalar()
        ) or 0
        record_count = (
            db.query(func.count(CustodyRecord.id))
            .filter(CustodyRecord.case_id == case.id)
            .scalar()
        ) or 0

        signer_ids = required_signer_ids or get_required_closure_signer_ids(db, case)
        users = (
            db.query(User).filter(User.id.in_(signer_ids)).all() if signer_ids else []
        )
        user_by_id = {u.id: u for u in users}

        manifest = {
            "manifest_schema_version": "1",
            "case_id": str(case.id),
            "protocol_number": case.protocol_number,
            "title": case.title,
            "status_at_close": case.status,
            "closure_mode": "bilateral",
            "required_signers": [
                {
                    "user_id": str(uid),
                    "username": user_by_id[uid].username if uid in user_by_id else None,
                }
                for uid in signer_ids
            ],
            "evidences": [
                {
                    "evidence_id": str(e.id),
                    "original_filename": e.original_filename,
                    "sha256": e.sha256,
                    "file_type": e.file_type,
                    "origin": (e.extra_metadata or {}).get("origin", "upload"),
                }
                for e in evidences
            ],
            "custody": {
                "last_chain_sequence": int(max_seq),
                "record_count": int(record_count),
            },
        }
        manifest["manifest_sha256"] = self.hash_manifest(manifest)
        return manifest


class CaseLifecycleService:
    def __init__(self, db: Session):
        self.db = db
        self.signing = CustodySigningService()
        self.manifest_builder = ForensicManifestBuilder()

    def _next_closure_sequence(self, case_id: uuid.UUID) -> int:
        max_seq = (
            self.db.query(func.max(CaseClosure.closure_sequence))
            .filter(CaseClosure.case_id == case_id)
            .scalar()
        )
        return int(max_seq or 0) + 1

    def _latest_closure(self, case_id: uuid.UUID) -> CaseClosure | None:
        return (
            self.db.query(CaseClosure)
            .options(joinedload(CaseClosure.additional_signatures))
            .filter(CaseClosure.case_id == case_id)
            .order_by(CaseClosure.closure_sequence.desc())
            .first()
        )

    def _signed_user_ids(self, closure: CaseClosure) -> set[uuid.UUID]:
        """Usuarios que ja assinaram o manifesto (nao confundir com signed_by = iniciador)."""
        signed: set[uuid.UUID] = set()
        if closure.system_signature:
            signed.add(closure.signed_by)
        for sig in closure.additional_signatures or []:
            signed.add(sig.user_id)
        return signed

    def _signer_role_label(
        self, db: Session, case: Case, user_id: uuid.UUID
    ) -> str:
        if case.created_by == user_id:
            return "criador"
        if case.assigned_to == user_id:
            return "perito_atribuido"
        share = (
            db.query(CaseShare)
            .filter(
                CaseShare.case_id == case.id,
                CaseShare.shared_with_user_id == user_id,
                CaseShare.revoked_at.is_(None),
            )
            .first()
        )
        if share:
            return f"compartilhado_{share.role}"
        return "participante"

    def get_closure_status(
        self, case_id: uuid.UUID, current_user: User
    ) -> dict[str, Any]:
        case = get_accessible_case(self.db, case_id, current_user)
        required_ids = get_required_closure_signer_ids(self.db, case)
        users = self.db.query(User).filter(User.id.in_(required_ids)).all()
        user_by_id = {u.id: u for u in users}

        closure = self._latest_closure(case_id)
        signed_ids: set[uuid.UUID] = set()
        if closure and closure.accepts_additional_signatures == "true":
            signed_ids = self._signed_user_ids(closure)
        elif case.status == "fechado" and closure:
            signed_ids = self._signed_user_ids(closure)

        signers_out = []
        for uid in required_ids:
            u = user_by_id.get(uid)
            signers_out.append(
                {
                    "user_id": str(uid),
                    "username": u.username if u else None,
                    "role": self._signer_role_label(self.db, case, uid),
                    "signed": uid in signed_ids,
                    "is_current_user": uid == current_user.id,
                }
            )

        pending = [s for s in signers_out if not s["signed"]]
        current_must_sign = (
            case.status == "fechamento_pendente"
            and current_user.id in required_ids
            and current_user.id not in signed_ids
        )
        can_initiate = case.status == "aberto" and user_may_sign_closure(
            self.db, case, current_user
        )

        return {
            "case_status": case.status,
            "fully_closed": case.status == "fechado",
            "closure_pending": case.status == "fechamento_pendente",
            "active_closure_id": str(closure.id) if closure else None,
            "required_signers": signers_out,
            "pending_signers": pending,
            "pending_count": len(pending),
            "all_signed": len(pending) == 0 and len(signers_out) > 0,
            "current_user_must_sign": current_must_sign,
            "current_user_can_initiate": can_initiate,
            "message": self._status_message(case, signers_out, pending),
        }

    def _status_message(
        self,
        case: Case,
        signers: list[dict],
        pending: list[dict],
    ) -> str:
        if case.status == "fechado":
            return "Caso encerrado — todas as assinaturas obrigatorias foram registradas."
        if case.status != "fechamento_pendente":
            if len(signers) <= 1:
                return "O responsavel pelo caso pode iniciar o fechamento com assinatura do sistema."
            return (
                "Fechamento bilateral: cada participante com permissao de edicao deve "
                "iniciar ou assinar o fechamento. O caso so encerra apos todas as assinaturas."
            )
        if not pending:
            return "Todas as assinaturas recebidas."
        names = ", ".join(
            p["username"] or p["user_id"][:8] for p in pending
        )
        return (
            f"Fechamento iniciado — aguardando assinatura de: {names}. "
            "Uploads e derivados permanecem bloqueados ate o encerramento definitivo."
        )

    def _apply_user_signature(
        self,
        closure: CaseClosure,
        case_id: uuid.UUID,
        user: User,
        *,
        additional: bool,
    ) -> CaseClosureSignature | None:
        if user.id in self._signed_user_ids(closure):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Voce ja assinou este fechamento",
            )

        signed = self.signing.sign_digest_hex(closure.manifest_sha256)

        if additional:
            sig = CaseClosureSignature(
                id=uuid.uuid4(),
                closure_id=closure.id,
                user_id=user.id,
                system_signature=signed["signature_b64"],
            )
            self.db.add(sig)
        else:
            closure.system_signature = signed["signature_b64"]
            sig = None

        CustodyService(self.db).create_record(
            record_type="case_closure_signed",
            case_id=case_id,
            user_id=user.id,
            sha256_output=closure.manifest_sha256,
            details={
                "closure_id": str(closure.id),
                "closure_sequence": closure.closure_sequence,
                "signature_mode": "system",
                "signing_key_id": signed["signing_key_id"],
                "additional_signature": additional,
            },
            commit=False,
        )
        return sig

    def _finalize_if_all_signed(self, case: Case, closure: CaseClosure) -> bool:
        self.db.flush()
        self.db.refresh(closure)
        required = set(get_required_closure_signer_ids(self.db, case))
        manifest_signers = (closure.manifest_json or {}).get("required_signers") or []
        if manifest_signers:
            required = {uuid.UUID(s["user_id"]) for s in manifest_signers}
        signed = self._signed_user_ids(closure)
        if signed >= required:
            case.status = "fechado"
            closure.accepts_additional_signatures = "false"
            return True
        case.status = "fechamento_pendente"
        closure.accepts_additional_signatures = "true"
        return False

    def close_case(
        self,
        case_id: uuid.UUID,
        current_user: User,
        *,
        signature_mode: str = "system",
        note: Optional[str] = None,
    ) -> tuple[CaseClosure, dict[str, Any]]:
        if signature_mode == "icp_brasil":
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="icp_brasil_not_implemented",
            )
        if signature_mode != "system":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="signature_mode deve ser system",
            )

        case = get_accessible_case(self.db, case_id, current_user)
        assert_can_close_case(self.db, case, current_user)

        if case.status == "fechado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Caso ja esta fechado",
            )

        if case.status == "fechamento_pendente":
            closure = self._latest_closure(case_id)
            if not closure or closure.accepts_additional_signatures != "true":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Nenhum fechamento pendente ativo",
                )
            self._apply_user_signature(closure, case_id, current_user, additional=True)
            fully = self._finalize_if_all_signed(case, closure)
            self.db.commit()
            self.db.refresh(closure)
            status_payload = self.get_closure_status(case_id, current_user)
            status_payload["signed_now"] = True
            status_payload["fully_closed"] = fully
            return closure, status_payload

        required_ids = get_required_closure_signer_ids(self.db, case)
        manifest = self.manifest_builder.build(
            self.db, case, required_signer_ids=required_ids
        )
        manifest_hash = manifest["manifest_sha256"]

        closure = CaseClosure(
            id=uuid.uuid4(),
            case_id=case_id,
            closure_sequence=self._next_closure_sequence(case_id),
            manifest_sha256=manifest_hash,
            manifest_json=manifest,
            signature_mode="system",
            system_signature=None,
            signed_by=current_user.id,
            accepts_additional_signatures="true",
        )
        self.db.add(closure)
        self.db.flush()

        custody = CustodyService(self.db)
        pending_usernames = [
            self.db.query(User).filter(User.id == uid).first()
            for uid in required_ids
            if uid != current_user.id
        ]
        custody.create_record(
            record_type="case_closed",
            case_id=case_id,
            user_id=current_user.id,
            sha256_output=manifest_hash,
            details={
                "closure_id": str(closure.id),
                "closure_sequence": closure.closure_sequence,
                "note": note,
                "closure_mode": "bilateral",
                "required_signer_count": len(required_ids),
                "pending_signers": [
                    u.username
                    for u in pending_usernames
                    if u is not None
                ],
            },
            commit=False,
        )

        self._apply_user_signature(closure, case_id, current_user, additional=False)
        signed_rec = (
            self.db.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == case_id,
                CustodyRecord.record_type == "case_closure_signed",
            )
            .order_by(CustodyRecord.timestamp.desc())
            .first()
        )
        if signed_rec:
            closure.custody_record_id = signed_rec.id

        fully = self._finalize_if_all_signed(case, closure)
        self.db.commit()
        self.db.refresh(closure)
        status_payload = self.get_closure_status(case_id, current_user)
        status_payload["signed_now"] = True
        status_payload["fully_closed"] = fully
        return closure, status_payload

    def add_closure_signature(
        self,
        case_id: uuid.UUID,
        current_user: User,
    ) -> CaseClosureSignature:
        """Alias para assinar fechamento pendente (mesmo fluxo de POST /close)."""
        self.close_case(case_id, current_user)
        closure = self._latest_closure(case_id)
        if not closure:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nenhum fechamento encontrado",
            )
        sig = (
            self.db.query(CaseClosureSignature)
            .filter(
                CaseClosureSignature.closure_id == closure.id,
                CaseClosureSignature.user_id == current_user.id,
            )
            .order_by(CaseClosureSignature.signed_at.desc())
            .first()
        )
        if sig:
            return sig
        if closure.signed_by == current_user.id:
            return CaseClosureSignature(
                id=uuid.uuid4(),
                closure_id=closure.id,
                user_id=current_user.id,
                system_signature=closure.system_signature or "",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assinatura nao registrada",
        )

    def reopen_case(self, case_id: uuid.UUID, current_user: User) -> Case:
        case = get_accessible_case(self.db, case_id, current_user)
        assert_can_reopen_case(self.db, case, current_user)

        if case.status not in ("fechado", "fechamento_pendente"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Caso nao esta em fechamento nem encerrado",
            )

        closure = self._latest_closure(case_id)
        if closure:
            closure.accepts_additional_signatures = "false"

        CustodyService(self.db).create_record(
            record_type="case_reopened",
            case_id=case_id,
            user_id=current_user.id,
            details={
                "closure_sequence": closure.closure_sequence if closure else None,
                "closure_id": str(closure.id) if closure else None,
                "reopened_from": case.status,
            },
            commit=False,
        )
        case.status = "aberto"
        self.db.commit()
        self.db.refresh(case)
        return case

    def list_closures(self, case_id: uuid.UUID, current_user: User) -> List[CaseClosure]:
        get_accessible_case(self.db, case_id, current_user)
        return (
            self.db.query(CaseClosure)
            .filter(CaseClosure.case_id == case_id)
            .order_by(CaseClosure.closure_sequence.asc())
            .all()
        )

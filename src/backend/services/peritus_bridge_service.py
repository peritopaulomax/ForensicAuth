"""Import/export of Peritus case ZIP archives with bit-identical round-trip."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from models.case import Case
from models.user import User
from services.case_access import assert_can_create_case, get_accessible_case
from services.custody_service import CustodyService
from services.peritus_file_meta import (
    build_xml_path_index,
    folder_sort_key,
    guess_mime,
    infer_file_type,
    peritus_folder_label,
)
from services.peritus_custody_import import register_peritus_files_in_custody
from services.peritus_va_materializer import materialize_peritus_file
from services.peritus_export_builder import build_peritus_zip_from_case
from services.peritus_xml import (
    PERITUS_XML_NAME,
    list_zip_member_paths,
    parse_peritus_manifest,
    sha256_hex_of_bytes,
    validate_peritus_zip_members,
)
ORIGINAL_ZIP_NAME = "original_import.zip"
WORKSPACE_DIRNAME = "workspace"
BINDING_FILENAME = "binding.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _case_storage_root(settings: Settings, case_id: uuid.UUID) -> Path:
    root = Path(settings.PERITUS_CASES_DIR) / str(case_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _binding_path(settings: Settings, case_id: uuid.UUID) -> Path:
    return _case_storage_root(settings, case_id) / BINDING_FILENAME


def _workspace_path(settings: Settings, case_id: uuid.UUID) -> Path:
    return _case_storage_root(settings, case_id) / WORKSPACE_DIRNAME


def _original_zip_path(settings: Settings, case_id: uuid.UUID) -> Path:
    return _case_storage_root(settings, case_id) / ORIGINAL_ZIP_NAME


def load_binding(settings: Settings, case_id: uuid.UUID) -> dict[str, Any] | None:
    path = _binding_path(settings, case_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_binding(settings: Settings, case_id: uuid.UUID, data: dict[str, Any]) -> None:
    path = _binding_path(settings, case_id)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def is_peritus_case(case: Case) -> bool:
    return getattr(case, "storage_mode", "va") == "peritus"


class PeritusBridgeService:
    """Validate, import and export native Peritus case ZIP packages."""

    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def detect_peritus_zip(self, zip_path: Path) -> bool:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                return PERITUS_XML_NAME in zf.namelist()
        except zipfile.BadZipFile:
            return False

    def validate_package(self, zip_path: Path, db: Session | None = None) -> dict[str, Any]:
        issues: list[str] = []
        if not zip_path.is_file():
            return {"valid": False, "issues": ["Arquivo nao encontrado"]}

        try:
            zf = zipfile.ZipFile(zip_path, "r")
        except zipfile.BadZipFile:
            return {"valid": False, "issues": ["Arquivo ZIP invalido"]}

        with zf:
            names = zf.namelist()
            if PERITUS_XML_NAME not in names:
                return {
                    "valid": False,
                    "issues": [f"ZIP nao contem {PERITUS_XML_NAME} na raiz"],
                }

            xml_bytes = zf.read(PERITUS_XML_NAME)

            def reader(path: str) -> bytes:
                candidates = [path, path.replace("/", "\\")]
                for cand in candidates:
                    if cand in names:
                        return zf.read(cand)
                raise KeyError(path)

            validation = validate_peritus_zip_members(
                names,
                xml_bytes,
                lambda p: reader(p),
            )
            issues.extend(validation["issues"])

            manifest = validation["manifest"]
            package = {
                "protocol_number": manifest.case_info.protocol_number,
                "title": manifest.case_info.title,
                "evidence_count": validation["evidence_count"],
                "derived_count": validation["derived_count"],
                "calculation_count": validation["calculation_count"],
                "files_checked": validation["files_checked"],
                "zip_sha256": _sha256_file(zip_path),
            }

            conflicts: dict[str, Any] = {"ok": True, "conflicts": []}
            if db is not None:
                protocol = manifest.case_info.protocol_number
                existing = (
                    db.query(Case)
                    .filter(Case.protocol_number == protocol, Case.deleted_at.is_(None))
                    .first()
                )
                if existing:
                    conflicts = {
                        "ok": False,
                        "conflicts": [
                            {
                                "type": "protocol_exists",
                                "protocol_number": protocol,
                                "case_id": str(existing.id),
                            }
                        ],
                    }
                    issues.append(
                        f"Protocolo '{protocol}' ja existe na instancia (caso {existing.id})"
                    )

        return {
            "valid": not issues,
            "issues": issues,
            "package": package,
            "files": {
                "checked": validation["files_checked"],
                "missing_in_zip": validation["missing_in_zip"],
                "orphan_in_zip": validation["orphan_in_zip"],
                "orphan_count": validation.get("orphan_count", 0),
                "hash_mismatch": validation["hash_mismatch"],
            },
            "conflicts": conflicts,
        }

    def import_case(
        self,
        zip_path: Path,
        current_user: User,
        *,
        skip_conflict_check: bool = False,
    ) -> dict[str, Any]:
        assert_can_create_case(current_user)
        report = self.validate_package(
            zip_path, db=None if skip_conflict_check else self.db
        )
        if not report["valid"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Pacote Peritus falhou na validacao",
                    "report": report,
                },
            )

        with zipfile.ZipFile(zip_path, "r") as zf:
            xml_bytes = zf.read(PERITUS_XML_NAME)
            manifest = parse_peritus_manifest(xml_bytes)

        case_id = uuid.uuid4()
        storage_root = _case_storage_root(self.settings, case_id)
        original_path = _original_zip_path(self.settings, case_id)
        shutil.copy2(zip_path, original_path)
        zip_sha256 = _sha256_file(original_path)

        workspace = _workspace_path(self.settings, case_id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)

        with zipfile.ZipFile(original_path, "r") as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                target = workspace / member.replace("\\", "/")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        info = manifest.case_info
        case = Case(
            id=case_id,
            protocol_number=info.protocol_number,
            inquiry_number=info.inquiry_number,
            process_number=info.process_number,
            title=info.title,
            description=info.description,
            created_by=current_user.id,
            assigned_to=current_user.id,
            status="aberto",
            storage_mode="peritus",
        )
        self.db.add(case)

        binding = {
            "format": "peritus-bridge-1",
            "case_id": str(case_id),
            "imported_at": _utc_now().isoformat(),
            "imported_by": str(current_user.id),
            "original_zip_sha256": zip_sha256,
            "original_xml_sha256": sha256_hex_of_bytes(xml_bytes),
            "modified": False,
            "peritus_fields": info.raw_fields,
            "file_count": sum(1 for n in zipfile.ZipFile(original_path).namelist() if not n.endswith("/")),
            "evidence_count": manifest.evidence_count,
            "derived_count": manifest.derived_count,
            "calculation_count": manifest.calculation_count,
        }
        save_binding(self.settings, case_id, binding)

        xml_sha256 = sha256_hex_of_bytes(xml_bytes)
        custody = CustodyService(self.db)
        custody.create_record(
            record_type="case_imported_peritus",
            case_id=case_id,
            user_id=current_user.id,
            sha256_input=zip_sha256,
            sha256_output=xml_sha256,
            details={
                "source": "peritus",
                "peritus_chain_anchor": xml_sha256,
                "original_zip_sha256": zip_sha256,
                "original_xml_sha256": xml_sha256,
                "protocol_number": info.protocol_number,
                "evidence_count": manifest.evidence_count,
                "derived_count": manifest.derived_count,
                "calculation_count": manifest.calculation_count,
                "note": (
                    "Ancora forense Peritus: SHA-256 do peritusCase.xml importado "
                    "(manifesto do pacote; assinatura ICP verificavel no Peritus). "
                    "ZIP original preservado byte-a-byte para export identico."
                ),
            },
            commit=False,
        )

        files_custody = register_peritus_files_in_custody(
            self.db,
            case_id=case_id,
            workspace=workspace,
            xml_bytes=xml_bytes,
            xml_sha256=xml_sha256,
            zip_sha256=zip_sha256,
            imported_by=current_user,
            custody=custody,
        )
        binding["custody_files_registered"] = files_custody["files_registered"]
        save_binding(self.settings, case_id, binding)

        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            if storage_root.exists():
                shutil.rmtree(storage_root, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": f"Falha ao gravar caso Peritus: {exc}"},
            ) from exc

        return {
            "case_id": str(case_id),
            "protocol_number": info.protocol_number,
            "storage_mode": "peritus",
            "evidence_count": manifest.evidence_count,
            "derived_count": manifest.derived_count,
            "calculation_count": manifest.calculation_count,
            "files_checked": report["files"]["checked"],
            "original_zip_sha256": zip_sha256,
            "original_xml_sha256": xml_sha256,
            "custody_files_registered": files_custody["files_registered"],
        }

    def get_case_meta(self, case_id: uuid.UUID, current_user: User) -> dict[str, Any]:
        case = get_accessible_case(self.db, case_id, current_user)
        if not is_peritus_case(case):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Metadados Peritus nao disponiveis para este caso"},
            )
        binding = load_binding(self.settings, case_id) or {}
        xml_sha = binding.get("original_xml_sha256")
        zip_sha = binding.get("original_zip_sha256")
        return {
            "case_id": str(case_id),
            "storage_mode": "peritus",
            "imported_at": binding.get("imported_at"),
            "modified": bool(binding.get("modified")),
            "original_zip_sha256": zip_sha,
            "original_xml_sha256": xml_sha,
            "peritus_chain_anchor": xml_sha,
            "protocol_number": (binding.get("peritus_fields") or {}).get("protocol_number"),
            "file_count": binding.get("file_count"),
            "evidence_count": binding.get("evidence_count"),
            "derived_count": binding.get("derived_count"),
            "calculation_count": binding.get("calculation_count"),
            "custody_files_registered": binding.get("custody_files_registered"),
        }

    def ensure_peritus_files_custody(
        self, case_id: uuid.UUID, current_user: User
    ) -> dict[str, Any]:
        """Registra arquivos Peritus na cadeia se ainda nao foram (casos importados antes da regra)."""
        from models.custody_record import CustodyRecord

        case = get_accessible_case(self.db, case_id, current_user)
        if not is_peritus_case(case):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Apenas casos Peritus"},
            )

        existing = (
            self.db.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == case_id,
                CustodyRecord.record_type == "peritus_file_imported",
            )
            .count()
        )
        if existing > 0:
            return {"already_registered": True, "files_registered": existing}

        workspace = _workspace_path(self.settings, case_id)
        xml_path = workspace / PERITUS_XML_NAME
        if not workspace.is_dir() or not xml_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Workspace Peritus indisponivel"},
            )

        binding = load_binding(self.settings, case_id) or {}
        xml_bytes = xml_path.read_bytes()
        xml_sha = binding.get("original_xml_sha256") or sha256_hex_of_bytes(xml_bytes)
        zip_sha = binding.get("original_zip_sha256") or ""

        custody = CustodyService(self.db)
        if not (
            self.db.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == case_id,
                CustodyRecord.record_type == "case_imported_peritus",
            )
            .first()
        ):
            custody.create_record(
                record_type="case_imported_peritus",
                case_id=case_id,
                user_id=current_user.id,
                sha256_input=zip_sha or None,
                sha256_output=xml_sha,
                details={
                    "source": "peritus",
                    "peritus_chain_anchor": xml_sha,
                    "original_zip_sha256": zip_sha,
                    "original_xml_sha256": xml_sha,
                    "note": "Registro de importacao recriado na regularizacao da cadeia.",
                },
                commit=False,
            )

        files_custody = register_peritus_files_in_custody(
            self.db,
            case_id=case_id,
            workspace=workspace,
            xml_bytes=xml_bytes,
            xml_sha256=xml_sha,
            zip_sha256=zip_sha,
            imported_by=current_user,
            custody=custody,
        )
        binding["custody_files_registered"] = files_custody["files_registered"]
        save_binding(self.settings, case_id, binding)
        self.db.commit()
        return {"already_registered": False, **files_custody}

    def resolve_file_for_analysis(
        self, case_id: uuid.UUID, current_user: User, relative_path: str
    ) -> dict[str, Any]:
        case = get_accessible_case(self.db, case_id, current_user)
        if not is_peritus_case(case):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Resolucao Peritus apenas para casos importados"},
            )
        workspace = _workspace_path(self.settings, case_id)
        if not workspace.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Workspace Peritus nao encontrado"},
            )
        xml_path = workspace / PERITUS_XML_NAME
        if not xml_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "peritusCase.xml nao encontrado"},
            )

        binding = load_binding(self.settings, case_id) or {}
        path_map = binding.get("path_to_evidence_id") or {}
        clean = relative_path.replace("\\", "/").lstrip("/")
        if clean in path_map:
            return {
                "evidence_id": path_map[clean],
                "path": clean,
                "created": False,
            }

        result = materialize_peritus_file(
            self.db,
            case_id=case_id,
            workspace=workspace,
            xml_bytes=xml_path.read_bytes(),
            relative_path=clean,
            imported_by=current_user,
            record_custody=False,
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Arquivo Peritus nao encontrado ou tipo nao suportado para analise"},
            )

        path_map[clean] = result["evidence_id"]
        binding["path_to_evidence_id"] = path_map
        save_binding(self.settings, case_id, binding)
        self.db.commit()
        return result

    def export_case(
        self,
        case_id: uuid.UUID,
        current_user: User,
        output_path: Path,
    ) -> Path:
        case = get_accessible_case(self.db, case_id, current_user)
        binding = load_binding(self.settings, case_id)
        original = _original_zip_path(self.settings, case_id)
        workspace = _workspace_path(self.settings, case_id)

        if (
            is_peritus_case(case)
            and binding
            and not binding.get("modified")
            and original.is_file()
        ):
            shutil.copy2(original, output_path)
            CustodyService(self.db).create_record(
                record_type="case_exported_peritus",
                case_id=case_id,
                user_id=current_user.id,
                sha256_output=_sha256_file(output_path),
                details={
                    "export_mode": "bit_identical",
                    "original_zip_sha256": binding.get("original_zip_sha256"),
                },
            )
            return output_path

        build_peritus_zip_from_case(
            self.db,
            case,
            output_path,
            workspace=workspace if workspace.is_dir() else None,
        )
        CustodyService(self.db).create_record(
            record_type="case_exported_peritus",
            case_id=case_id,
            user_id=current_user.id,
            sha256_output=_sha256_file(output_path),
            details={
                "export_mode": "forensic_auth_generated",
                "unsigned": True,
                "note": "Requer assinatura ICP no Peritus para validade forense plena",
            },
        )
        return output_path

    def list_files(self, case_id: uuid.UUID, current_user: User) -> dict[str, Any]:
        case = get_accessible_case(self.db, case_id, current_user)
        workspace = _workspace_path(self.settings, case_id)
        if not workspace.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Workspace Peritus nao disponivel para este caso"},
            )

        binding = load_binding(self.settings, case_id)
        xml_path = workspace / PERITUS_XML_NAME
        xml_index = (
            build_xml_path_index(xml_path.read_bytes())
            if xml_path.is_file()
            else {}
        )
        entries: list[dict[str, Any]] = []
        folders: set[str] = set()

        for path in sorted(workspace.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace).as_posix()
            stat = path.stat()
            meta = xml_index.get(rel, {})
            filename = path.name
            mime = meta.get("mime_type") or guess_mime(filename)
            file_type = infer_file_type(filename, mime)
            folder = peritus_folder_label(rel)
            folders.add(folder)
            entries.append(
                {
                    "path": rel,
                    "filename": filename,
                    "folder": folder,
                    "size": stat.st_size,
                    "file_type": file_type,
                    "mime_type": mime,
                    "sha256": meta.get("sha256"),
                    "peritus_uuid": meta.get("peritus_uuid"),
                    "is_derived": rel.startswith("derived-files/")
                    or meta.get("kind") == "derived",
                    "is_xml": rel == PERITUS_XML_NAME,
                    "evidence_id": (binding or {}).get("path_to_evidence_id", {}).get(rel),
                }
            )

        folder_list = sorted(folders, key=folder_sort_key)

        return {
            "case_id": str(case_id),
            "storage_mode": getattr(case, "storage_mode", "va"),
            "modified": bool(binding.get("modified")) if binding else False,
            "original_zip_sha256": binding.get("original_zip_sha256") if binding else None,
            "folders": folder_list,
            "files": entries,
            "file_count": len(entries),
        }

    def resolve_file_path(
        self, case_id: uuid.UUID, current_user: User, relative_path: str
    ) -> Path:
        get_accessible_case(self.db, case_id, current_user)
        workspace = _workspace_path(self.settings, case_id)
        clean = relative_path.replace("\\", "/").lstrip("/")
        if ".." in clean.split("/"):
            raise HTTPException(status_code=400, detail="Path invalido")

        target = (workspace / clean).resolve()
        if not str(target).startswith(str(workspace.resolve())):
            raise HTTPException(status_code=400, detail="Path invalido")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
        return target

    def remove_case_storage(self, case_id: uuid.UUID) -> None:
        root = Path(self.settings.PERITUS_CASES_DIR) / str(case_id)
        if root.is_dir():
            shutil.rmtree(root, ignore_errors=True)

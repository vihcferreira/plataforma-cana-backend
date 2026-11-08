"""
Serviço centralizado de Preferências e Configurações Multitenant (`Tenant_Settings`).
Elimina a duplicação de caches em memória e lógica de upsert entre Alertas e Telemetria,
além de fornecer consulta em lote para eliminar N+1 queries no loop de telemetria.
"""

from typing import Dict, Iterable, Optional
from sqlalchemy.orm import Session

from database import TenantSettingsModel

DEFAULT_UNIT = "vale-verde-norte"
DEFAULT_FREQUENCY_MINUTES = 15
DEFAULT_TIMEZONE = "America/Sao_Paulo"

# Cache/fallback unificado em memória por tenant_id
_settings_cache: Dict[str, dict] = {}


def clear_settings_cache() -> None:
    """Limpa o cache em memória (útil em suítes de testes automatizados)."""
    _settings_cache.clear()


def _default_entry(default_email: str = "") -> dict:
    return {
        "unit": DEFAULT_UNIT,
        "frequency_minutes": DEFAULT_FREQUENCY_MINUTES,
        "timezone": DEFAULT_TIMEZONE,
        "email_alerts": True,
        "push_alerts": True,
        "user_email": default_email or "",
        "telemetry_active": True,
    }


def _row_to_entry(row: TenantSettingsModel, default_email: str = "") -> dict:
    return {
        "unit": row.unit_select or DEFAULT_UNIT,
        "frequency_minutes": int(row.frequency_minutes or DEFAULT_FREQUENCY_MINUTES),
        "timezone": row.timezone or DEFAULT_TIMEZONE,
        "email_alerts": bool(row.email_alerts),
        "push_alerts": bool(row.push_alerts),
        "user_email": row.user_email or default_email or "",
        "telemetry_active": bool(row.telemetry_active),
    }


def _get_or_load_entry(tenant_id: str, db: Optional[Session] = None, default_email: str = "") -> dict:
    if db is not None:
        try:
            row = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
            if row is not None:
                entry = _row_to_entry(row, default_email=default_email)
                _settings_cache[tenant_id] = entry
                return entry
        except Exception:
            pass

    cached = _settings_cache.get(tenant_id)
    if cached is not None:
        if default_email and not cached.get("user_email"):
            cached = {**cached, "user_email": default_email}
        return cached

    return _default_entry(default_email=default_email)


def _upsert_tenant_settings(tenant_id: str, updates: dict, db: Optional[Session] = None) -> dict:
    current = dict(_get_or_load_entry(tenant_id, db=db))
    current.update(updates)
    _settings_cache[tenant_id] = current

    if db is not None:
        try:
            row = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
            if not row:
                row = TenantSettingsModel(tenant_id=tenant_id)
                db.add(row)

            row.unit_select = current["unit"]
            row.frequency_minutes = int(current["frequency_minutes"])
            row.timezone = current["timezone"]
            row.email_alerts = 1 if current["email_alerts"] else 0
            row.push_alerts = 1 if current["push_alerts"] else 0
            row.user_email = current["user_email"]
            row.telemetry_active = 1 if current["telemetry_active"] else 0
            db.commit()
        except Exception:
            db.rollback()

    return current


def get_notification_settings(tenant_id: str, db: Optional[Session] = None, default_email: str = "") -> dict:
    entry = _get_or_load_entry(tenant_id, db=db, default_email=default_email)
    return {
        "email_alerts": bool(entry["email_alerts"]),
        "push_alerts": bool(entry["push_alerts"]),
        "user_email": entry["user_email"] or default_email or "",
    }


def update_notification_settings(
    tenant_id: str,
    email_alerts: Optional[bool] = None,
    push_alerts: Optional[bool] = None,
    user_email: Optional[str] = None,
    default_email: str = "",
    db: Optional[Session] = None,
) -> dict:
    current = _get_or_load_entry(tenant_id, db=db, default_email=default_email)
    updated = _upsert_tenant_settings(
        tenant_id=tenant_id,
        updates={
            "email_alerts": bool(email_alerts) if email_alerts is not None else current["email_alerts"],
            "push_alerts": bool(push_alerts) if push_alerts is not None else current["push_alerts"],
            "user_email": str(user_email or default_email or current.get("user_email") or ""),
        },
        db=db,
    )
    return {
        "email_alerts": updated["email_alerts"],
        "push_alerts": updated["push_alerts"],
        "user_email": updated["user_email"],
    }


def get_general_settings(tenant_id: str, db: Optional[Session] = None) -> dict:
    entry = _get_or_load_entry(tenant_id, db=db)
    return {
        "unit": entry["unit"],
        "frequency": str(entry["frequency_minutes"]),
        "timezone": entry["timezone"],
    }


def update_general_settings(
    tenant_id: str,
    unit: Optional[str] = None,
    frequency: Optional[str | int] = None,
    timezone_name: Optional[str] = None,
    db: Optional[Session] = None,
) -> dict:
    try:
        freq_int = int(frequency) if frequency is not None else DEFAULT_FREQUENCY_MINUTES
    except (TypeError, ValueError):
        freq_int = DEFAULT_FREQUENCY_MINUTES

    updated = _upsert_tenant_settings(
        tenant_id=tenant_id,
        updates={
            "unit": str(unit or DEFAULT_UNIT),
            "frequency_minutes": max(1, freq_int),
            "timezone": str(timezone_name or DEFAULT_TIMEZONE),
        },
        db=db,
    )
    return {
        "unit": updated["unit"],
        "frequency": str(updated["frequency_minutes"]),
        "timezone": updated["timezone"],
    }


def get_telemetry_active(tenant_id: str, db: Optional[Session] = None) -> bool:
    return bool(_get_or_load_entry(tenant_id, db=db)["telemetry_active"])


def set_telemetry_active(tenant_id: str, active: bool, db: Optional[Session] = None) -> bool:
    updated = _upsert_tenant_settings(
        tenant_id=tenant_id,
        updates={"telemetry_active": bool(active)},
        db=db,
    )
    return bool(updated["telemetry_active"])


def load_tenant_settings_batch(db: Session, tenant_ids: Iterable[str]) -> Dict[str, dict]:
    """Carrega configurações de múltiplos tenants em uma única query SQL (`WHERE tenant_id IN (...)`)."""
    ids_list = [tid for tid in set(tenant_ids) if tid]
    if not ids_list:
        return {}

    result: Dict[str, dict] = {}
    try:
        rows = (
            db.query(TenantSettingsModel)
            .filter(TenantSettingsModel.tenant_id.in_(ids_list))
            .all()
        )
        for row in rows:
            entry = _row_to_entry(row)
            _settings_cache[row.tenant_id] = entry
            result[row.tenant_id] = entry
    except Exception:
        pass

    for tid in ids_list:
        if tid not in result:
            result[tid] = _settings_cache.get(tid, _default_entry())

    return result


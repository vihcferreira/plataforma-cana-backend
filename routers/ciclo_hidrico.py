"""
Router do Ciclo Hídrico, Laudos Laboratoriais e Licenciamento Ambiental — Plataforma Cana / AquaGuard
Integra e orquestra de ponta a ponta as 9 tabelas operacionais e regulatórias do banco de dados
(Property, Water_Seller, Environmental_Regulator, Measurement, Water_Batch, Area_Of_Disposal,
Water_Admission, Water_Storage e Water_Disposal) com isolamento Multitenancy (tenant_id),
classificação automática via modelo ML (modelo_qualidade_agua.pkl) e auditoria em Alert/Occurrence/History_Event.
"""

from datetime import datetime
import json
import logging
import random
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_tenant import get_current_tenant, get_current_tenant_context, TenantContext
from database import (
    get_db,
    WaterSellerModel,
    PropertyModel,
    EnvironmentalRegulatorModel,
    MeasurementModel,
    WaterBatchModel,
    AreaOfDisposalModel,
    WaterAdmissionModel,
    WaterStorageModel,
    WaterDisposalModel,
    OccurrenceModel,
    AlertModel,
    HistoryEventModel,
    AppUserModel,
)
from routers.ia import modelo_ia
from schemas import (
    WaterSellerCriar,
    WaterSellerResposta,
    PropertyCriar,
    PropertyResposta,
    EnvironmentalRegulatorCriar,
    EnvironmentalRegulatorResposta,
    MeasurementCriar,
    MeasurementResposta,
    WaterBatchCriar,
    WaterBatchResposta,
    AreaOfDisposalCriar,
    AreaOfDisposalAtualizar,
    AreaOfDisposalResposta,
    WaterAdmissionCriar,
    WaterAdmissionResposta,
    WaterStorageCriar,
    WaterStorageResposta,
    WaterDisposalCriar,
    WaterDisposalResposta,
    WaterCycleSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Ciclo Hídrico e Licenciamento"])


# ==========================================
# UTILITÁRIOS DE AVALIAÇÃO ML / CONAMA E SERIALIZAÇÃO
# ==========================================
def avaliar_qualidade_medicao(m: MeasurementModel) -> tuple[str, bool]:
    """
    Combina o classificador de Machine Learning (modelo_qualidade_agua.pkl) com os limites
    físico-químicos CONAMA 430 / fertirrigação agroindustrial.
    """
    ph = float(m.ph_measurement if m.ph_measurement is not None else 7.0)
    od = float(m.o2_dissolved_measurement if m.o2_dissolved_measurement is not None else 6.0)
    turb = float(m.turbidity_measurement if m.turbidity_measurement is not None else 20.0)
    dbo = float(m.bod_measurement if m.bod_measurement is not None else 15.0)
    dqo = float(m.cod_measurement if m.cod_measurement is not None else 45.0)

    conama_ok = (
        6.0 <= ph <= 9.0
        and od >= 4.0
        and turb <= 40.0
        and dbo <= 60.0
        and dqo <= 150.0
    )

    ml_status = "Própria" if conama_ok else "Poluída (Risco de Efluentes)"
    if modelo_ia is not None:
        try:
            df_in = pd.DataFrame(
                [
                    {
                        "pH": ph,
                        "Temperatura_C": 25.0,
                        "DBO_mgL": dbo,
                        "Turbidez_NTU": turb,
                    }
                ]
            )
            pred = modelo_ia.predict(df_in)
            if int(pred[0]) == 1 and conama_ok:
                ml_status = "Própria"
            else:
                ml_status = "Poluída (Risco de Efluentes)"
        except Exception as exc:
            logger.debug(f"[CicloHidrico] Fallback na avaliação ML da medição: {exc}")

    return ml_status, conama_ok


def serialize_measurement(m: Optional[MeasurementModel]) -> Optional[dict]:
    if not m:
        return None
    ml_status, conama_ok = avaliar_qualidade_medicao(m)
    return {
        "id_measurement": m.id_measurement,
        "datetime_measurement": m.datetime_measurement,
        "ph_measurement": m.ph_measurement,
        "o2_dissolved_measurement": m.o2_dissolved_measurement,
        "turbidity_measurement": m.turbidity_measurement,
        "conductivity_measurement": m.conductivity_measurement,
        "bod_measurement": m.bod_measurement,
        "cod_measurement": m.cod_measurement,
        "nitrogen_phosphorus_measurement": m.nitrogen_phosphorus_measurement,
        "ml_status": ml_status,
        "conama_compliant": conama_ok,
    }


def format_property_label(prop: Optional[PropertyModel]) -> str:
    if not prop:
        return "Unidade não informada"
    return f"{prop.property_address} ({prop.property_city})"


def _resolver_ou_criar_medicao(
    db: Session,
    tenant_id: str,
    id_measurement: Optional[int],
    measurement_in: Optional[MeasurementCriar],
) -> MeasurementModel:
    if id_measurement is not None:
        existente = (
            db.query(MeasurementModel)
            .filter(
                MeasurementModel.id_measurement == id_measurement,
                MeasurementModel.tenant_id == tenant_id,
            )
            .first()
        )
        if not existente:
            raise HTTPException(
                status_code=404,
                detail="Laudo laboratorial (Measurement) não encontrado nesta conta.",
            )
        return existente

    dados_m = measurement_in or MeasurementCriar()
    nova_m = MeasurementModel(
        tenant_id=tenant_id,
        datetime_measurement=dados_m.datetime_measurement or datetime.utcnow(),
        ph_measurement=dados_m.ph_measurement,
        o2_dissolved_measurement=dados_m.o2_dissolved_measurement,
        turbidity_measurement=dados_m.turbidity_measurement,
        conductivity_measurement=dados_m.conductivity_measurement,
        bod_measurement=dados_m.bod_measurement,
        cod_measurement=dados_m.cod_measurement,
        nitrogen_phosphorus_measurement=dados_m.nitrogen_phosphorus_measurement,
    )
    db.add(nova_m)
    db.flush()
    return nova_m


def _obter_responsavel_padrao(db: Session, tenant_id: str, fallback: str = "Gestor Ambiental") -> str:
    usuario = (
        db.query(AppUserModel)
        .filter(
            AppUserModel.tenant_id == tenant_id,
            AppUserModel.status_user == "active",
        )
        .first()
    )
    if usuario and usuario.name_user:
        return usuario.name_user
    return fallback


def _gerar_codigos_unicos(db: Session, tenant_id: str) -> tuple[str, str]:
    ocr_code = f"OCR-{random.randint(1000, 9999)}"
    for _ in range(15):
        cand = f"OCR-{random.randint(1000, 9999)}"
        if not (
            db.query(OccurrenceModel)
            .filter(OccurrenceModel.tenant_id == tenant_id, OccurrenceModel.code_occurrence == cand)
            .first()
        ):
            ocr_code = cand
            break

    al_code = f"AL-{random.randint(100, 999)}"
    for _ in range(15):
        cand = f"AL-{random.randint(100, 999)}"
        if not (
            db.query(AlertModel)
            .filter(AlertModel.tenant_id == tenant_id, AlertModel.code_alert == cand)
            .first()
        ):
            al_code = cand
            break

    return ocr_code, al_code


# ==========================================
# 1. RESUMO DO BALANÇO HÍDRICO E CONFORMIDADE
# ==========================================
def calcular_resumo_ciclo_hidrico(db: Session, tenant_id: str) -> dict:
    props = db.query(PropertyModel).filter(PropertyModel.tenant_id == tenant_id).all()
    sellers = db.query(WaterSellerModel).filter(WaterSellerModel.tenant_id == tenant_id).all()
    regs = (
        db.query(EnvironmentalRegulatorModel)
        .filter(EnvironmentalRegulatorModel.tenant_id == tenant_id)
        .all()
    )
    batches = db.query(WaterBatchModel).filter(WaterBatchModel.tenant_id == tenant_id).all()
    areas = db.query(AreaOfDisposalModel).filter(AreaOfDisposalModel.tenant_id == tenant_id).all()
    measurements = db.query(MeasurementModel).filter(MeasurementModel.tenant_id == tenant_id).all()
    admissions = db.query(WaterAdmissionModel).filter(WaterAdmissionModel.tenant_id == tenant_id).all()
    storages = db.query(WaterStorageModel).filter(WaterStorageModel.tenant_id == tenant_id).all()
    disposals = db.query(WaterDisposalModel).filter(WaterDisposalModel.tenant_id == tenant_id).all()

    total_adm = round(sum(float(a.volume_admitted or 0.0) for a in admissions), 2)
    total_sto = round(sum(float(s.volume_stored or 0.0) for s in storages), 2)
    total_dis = round(sum(float(d.volume_disposed or 0.0) for d in disposals), 2)
    net_bal = round(total_adm - total_dis, 2)

    validated_areas = sum(1 for a in areas if bool(a.is_validated_for_disposal))

    def _avg(vals: list[float]) -> Optional[float]:
        return round(sum(vals) / len(vals), 2) if vals else None

    compliant_count = 0
    for m in measurements:
        _, ok = avaliar_qualidade_medicao(m)
        if ok:
            compliant_count += 1

    compliance_pct = (
        round((compliant_count / len(measurements)) * 100.0, 1) if measurements else None
    )

    return {
        "total_admitted_m3": total_adm,
        "total_stored_m3": total_sto,
        "total_disposed_m3": total_dis,
        "net_balance_m3": net_bal,
        "properties_count": len(props),
        "sellers_count": len(sellers),
        "regulators_count": len(regs),
        "batches_count": len(batches),
        "areas_count": len(areas),
        "validated_areas_count": validated_areas,
        "measurements_count": len(measurements),
        "admissions_count": len(admissions),
        "storages_count": len(storages),
        "disposals_count": len(disposals),
        "conama_compliance_pct": compliance_pct,
        "avg_ph": _avg([float(m.ph_measurement) for m in measurements if m.ph_measurement is not None]),
        "avg_od": _avg([float(m.o2_dissolved_measurement) for m in measurements if m.o2_dissolved_measurement is not None]),
        "avg_turbidity": _avg([float(m.turbidity_measurement) for m in measurements if m.turbidity_measurement is not None]),
        "avg_conductivity": _avg([float(m.conductivity_measurement) for m in measurements if m.conductivity_measurement is not None]),
        "avg_bod": _avg([float(m.bod_measurement) for m in measurements if m.bod_measurement is not None]),
        "avg_cod": _avg([float(m.cod_measurement) for m in measurements if m.cod_measurement is not None]),
        "avg_npk": _avg([float(m.nitrogen_phosphorus_measurement) for m in measurements if m.nitrogen_phosphorus_measurement is not None]),
    }


@router.get("/resumo", response_model=WaterCycleSummaryResponse, summary="Resumo consolidado do Ciclo Hídrico e Laudos")
def obter_resumo_ciclo(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return calcular_resumo_ciclo_hidrico(db=db, tenant_id=tenant_id)


# ==========================================
# 2. PROPRIEDADES / UNIDADES AGROINDUSTRIAIS (Property)
# ==========================================
@router.get("/propriedades", response_model=List[PropertyResposta])
def listar_propriedades(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(PropertyModel)
        .filter(PropertyModel.tenant_id == tenant_id)
        .order_by(PropertyModel.id_property.desc())
        .all()
    )


@router.post("/propriedades", response_model=PropertyResposta, status_code=status.HTTP_201_CREATED)
def criar_propriedade(
    dados: PropertyCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    nova = PropertyModel(
        tenant_id=tenant_id,
        property_address=dados.property_address.strip(),
        property_city=dados.property_city.strip(),
    )
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova


@router.delete("/propriedades/{id_property}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_propriedade(
    id_property: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    prop = (
        db.query(PropertyModel)
        .filter(PropertyModel.id_property == id_property, PropertyModel.tenant_id == tenant_id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Propriedade não encontrada.")

    em_uso = (
        db.query(WaterBatchModel).filter(WaterBatchModel.id_property == id_property, WaterBatchModel.tenant_id == tenant_id).first()
        or db.query(AreaOfDisposalModel).filter(AreaOfDisposalModel.id_property == id_property, AreaOfDisposalModel.tenant_id == tenant_id).first()
        or db.query(WaterStorageModel).filter(WaterStorageModel.id_property == id_property, WaterStorageModel.tenant_id == tenant_id).first()
    )
    if em_uso:
        raise HTTPException(
            status_code=400,
            detail="Esta propriedade possui lotes, armazenamentos ou áreas de descarte vinculados.",
        )

    db.delete(prop)
    db.commit()
    return None


# ==========================================
# 3. FORNECEDORES / ORIGEM HÍDRICA (Water_Seller)
# ==========================================
@router.get("/fornecedores", response_model=List[WaterSellerResposta])
def listar_fornecedores(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(WaterSellerModel)
        .filter(WaterSellerModel.tenant_id == tenant_id)
        .order_by(WaterSellerModel.id_seller.desc())
        .all()
    )


@router.post("/fornecedores", response_model=WaterSellerResposta, status_code=status.HTTP_201_CREATED)
def criar_fornecedor(
    dados: WaterSellerCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    novo = WaterSellerModel(
        tenant_id=tenant_id,
        cnpj_seller=(dados.cnpj_seller or "").strip() or None,
        name_seller=dados.name_seller.strip(),
        license_number_seller=(dados.license_number_seller or "").strip() or None,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.delete("/fornecedores/{id_seller}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_fornecedor(
    id_seller: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    fornecedor = (
        db.query(WaterSellerModel)
        .filter(WaterSellerModel.id_seller == id_seller, WaterSellerModel.tenant_id == tenant_id)
        .first()
    )
    if not fornecedor:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")

    em_uso = (
        db.query(WaterBatchModel)
        .filter(WaterBatchModel.id_seller == id_seller, WaterBatchModel.tenant_id == tenant_id)
        .first()
    )
    if em_uso:
        raise HTTPException(
            status_code=400,
            detail="Fornecedor vinculado a lotes hídricos existentes.",
        )

    db.delete(fornecedor)
    db.commit()
    return None


# ==========================================
# 4. ÓRGÃOS REGULADORES AMBIENTAIS (Environmental_Regulator)
# ==========================================
@router.get("/reguladores", response_model=List[EnvironmentalRegulatorResposta])
def listar_reguladores(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(EnvironmentalRegulatorModel)
        .filter(EnvironmentalRegulatorModel.tenant_id == tenant_id)
        .order_by(EnvironmentalRegulatorModel.id_regulator.desc())
        .all()
    )


@router.post("/reguladores", response_model=EnvironmentalRegulatorResposta, status_code=status.HTTP_201_CREATED)
def criar_regulador(
    dados: EnvironmentalRegulatorCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    novo = EnvironmentalRegulatorModel(
        tenant_id=tenant_id,
        name_regulator=dados.name_regulator.strip(),
        jurisdiction_regulator=dados.jurisdiction_regulator.strip(),
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.delete("/reguladores/{id_regulator}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_regulador(
    id_regulator: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    reg = (
        db.query(EnvironmentalRegulatorModel)
        .filter(
            EnvironmentalRegulatorModel.id_regulator == id_regulator,
            EnvironmentalRegulatorModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not reg:
        raise HTTPException(status_code=404, detail="Órgão regulador não encontrado.")

    em_uso = (
        db.query(AreaOfDisposalModel)
        .filter(
            AreaOfDisposalModel.id_regulator == id_regulator,
            AreaOfDisposalModel.tenant_id == tenant_id,
        )
        .first()
    )
    if em_uso:
        raise HTTPException(
            status_code=400,
            detail="Órgão regulador vinculado a áreas de descarte cadastradas.",
        )

    db.delete(reg)
    db.commit()
    return None


# ==========================================
# 5. ÁREAS DE DESCARTE E FERTIRRIGAÇÃO (Area_Of_Disposal)
# ==========================================
def _montar_area_resposta(
    area: AreaOfDisposalModel,
    props_map: dict[int, PropertyModel],
    regs_map: dict[int, EnvironmentalRegulatorModel],
) -> dict:
    prop = props_map.get(area.id_property) if area.id_property else None
    reg = regs_map.get(area.id_regulator) if area.id_regulator else None
    return {
        "id_disposal_area": area.id_disposal_area,
        "id_property": area.id_property,
        "property_label": format_property_label(prop) if prop else None,
        "x_coordinate": float(area.x_coordinate or 50.0),
        "y_coordinate": float(area.y_coordinate or 50.0),
        "is_validated_for_disposal": bool(area.is_validated_for_disposal),
        "license_number_disposal": area.license_number_disposal,
        "id_regulator": area.id_regulator,
        "regulator_name": reg.name_regulator if reg else None,
        "regulator_jurisdiction": reg.jurisdiction_regulator if reg else None,
    }


@router.get("/areas-descarte", response_model=List[AreaOfDisposalResposta])
def listar_areas_descarte(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    areas = (
        db.query(AreaOfDisposalModel)
        .filter(AreaOfDisposalModel.tenant_id == tenant_id)
        .order_by(AreaOfDisposalModel.id_disposal_area.desc())
        .all()
    )
    props_map = {
        p.id_property: p
        for p in db.query(PropertyModel).filter(PropertyModel.tenant_id == tenant_id).all()
    }
    regs_map = {
        r.id_regulator: r
        for r in db.query(EnvironmentalRegulatorModel)
        .filter(EnvironmentalRegulatorModel.tenant_id == tenant_id)
        .all()
    }
    return [_montar_area_resposta(a, props_map, regs_map) for a in areas]


@router.post("/areas-descarte", response_model=AreaOfDisposalResposta, status_code=status.HTTP_201_CREATED)
def criar_area_descarte(
    dados: AreaOfDisposalCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    prop = (
        db.query(PropertyModel)
        .filter(PropertyModel.id_property == dados.id_property, PropertyModel.tenant_id == tenant_id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Propriedade informada não pertence a esta conta.")

    reg = (
        db.query(EnvironmentalRegulatorModel)
        .filter(
            EnvironmentalRegulatorModel.id_regulator == dados.id_regulator,
            EnvironmentalRegulatorModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not reg:
        raise HTTPException(status_code=404, detail="Órgão regulador informado não pertence a esta conta.")

    nova_area = AreaOfDisposalModel(
        tenant_id=tenant_id,
        id_property=prop.id_property,
        x_coordinate=max(2.0, min(98.0, float(dados.x_coordinate))),
        y_coordinate=max(2.0, min(98.0, float(dados.y_coordinate))),
        is_validated_for_disposal=bool(dados.is_validated_for_disposal),
        license_number_disposal=(dados.license_number_disposal or "").strip() or None,
        id_regulator=reg.id_regulator,
    )
    db.add(nova_area)
    db.commit()
    db.refresh(nova_area)
    return _montar_area_resposta(
        nova_area,
        {prop.id_property: prop},
        {reg.id_regulator: reg},
    )


@router.put("/areas-descarte/{id_disposal_area}", response_model=AreaOfDisposalResposta)
def atualizar_area_descarte(
    id_disposal_area: int,
    dados: AreaOfDisposalAtualizar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    area = (
        db.query(AreaOfDisposalModel)
        .filter(
            AreaOfDisposalModel.id_disposal_area == id_disposal_area,
            AreaOfDisposalModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not area:
        raise HTTPException(status_code=404, detail="Área de descarte não encontrada.")

    payload = dados.model_dump(exclude_unset=True)
    if "id_property" in payload and payload["id_property"] is not None:
        prop = (
            db.query(PropertyModel)
            .filter(
                PropertyModel.id_property == payload["id_property"],
                PropertyModel.tenant_id == tenant_id,
            )
            .first()
        )
        if not prop:
            raise HTTPException(status_code=404, detail="Propriedade não encontrada.")

    if "id_regulator" in payload and payload["id_regulator"] is not None:
        reg = (
            db.query(EnvironmentalRegulatorModel)
            .filter(
                EnvironmentalRegulatorModel.id_regulator == payload["id_regulator"],
                EnvironmentalRegulatorModel.tenant_id == tenant_id,
            )
            .first()
        )
        if not reg:
            raise HTTPException(status_code=404, detail="Órgão regulador não encontrado.")

    for campo, valor in payload.items():
        setattr(area, campo, valor)

    db.commit()
    db.refresh(area)

    props_map = {
        p.id_property: p
        for p in db.query(PropertyModel).filter(PropertyModel.tenant_id == tenant_id).all()
    }
    regs_map = {
        r.id_regulator: r
        for r in db.query(EnvironmentalRegulatorModel)
        .filter(EnvironmentalRegulatorModel.tenant_id == tenant_id)
        .all()
    }
    return _montar_area_resposta(area, props_map, regs_map)


@router.delete("/areas-descarte/{id_disposal_area}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_area_descarte(
    id_disposal_area: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    area = (
        db.query(AreaOfDisposalModel)
        .filter(
            AreaOfDisposalModel.id_disposal_area == id_disposal_area,
            AreaOfDisposalModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not area:
        raise HTTPException(status_code=404, detail="Área de descarte não encontrada.")

    em_uso = (
        db.query(WaterDisposalModel)
        .filter(
            WaterDisposalModel.id_disposal_area == id_disposal_area,
            WaterDisposalModel.tenant_id == tenant_id,
        )
        .first()
    )
    if em_uso:
        raise HTTPException(
            status_code=400,
            detail="Esta área possui registros históricos de descarte vinculados.",
        )

    db.delete(area)
    db.commit()
    return None


# ==========================================
# 6. LAUDOS LABORATORIAIS (Measurement) + IA (.pkl)
# ==========================================
@router.get("/medicoes-laboratoriais", response_model=List[MeasurementResposta])
def listar_medicoes_laboratoriais(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    medicoes = (
        db.query(MeasurementModel)
        .filter(MeasurementModel.tenant_id == tenant_id)
        .order_by(MeasurementModel.id_measurement.desc())
        .all()
    )
    return [serialize_measurement(m) for m in medicoes]


@router.post("/medicoes-laboratoriais", response_model=MeasurementResposta, status_code=status.HTTP_201_CREATED)
def criar_medicao_laboratorial(
    dados: MeasurementCriar,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    nova = _resolver_ou_criar_medicao(db, tenant_id, None, dados)
    ml_status, conama_ok = avaliar_qualidade_medicao(nova)

    severidade_hist = "normal" if conama_ok else "critico"
    evento = HistoryEventModel(
        tenant_id=tenant_id,
        event_type="medicao",
        event_label="Laudo Físico-Químico Laboratorial",
        event_point=f"Amostra Lab #{nova.id_measurement}",
        event_description=(
            f"Laudo registrado: pH {nova.ph_measurement:.1f}, OD {nova.o2_dissolved_measurement:.1f} mg/L, "
            f"DBO {nova.bod_measurement:.1f} mg/L, DQO {nova.cod_measurement:.1f} mg/L, "
            f"NPK {nova.nitrogen_phosphorus_measurement:.1f} mg/L — Classificação IA: {ml_status}."
        ),
        event_severity=severidade_hist,
        id_reference=nova.id_measurement,
        reference_type="measurement",
        created_by=ctx.name or ctx.email or "Laboratório",
    )
    db.add(evento)
    db.commit()
    db.refresh(nova)
    return serialize_measurement(nova)


# ==========================================
# 7. LOTES HÍDRICOS (Water_Batch)
# ==========================================
@router.get("/lotes", response_model=List[WaterBatchResposta])
def listar_lotes(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    lotes = (
        db.query(WaterBatchModel)
        .filter(WaterBatchModel.tenant_id == tenant_id)
        .order_by(WaterBatchModel.id_batch.desc())
        .all()
    )
    sellers_map = {
        s.id_seller: s
        for s in db.query(WaterSellerModel).filter(WaterSellerModel.tenant_id == tenant_id).all()
    }
    props_map = {
        p.id_property: p
        for p in db.query(PropertyModel).filter(PropertyModel.tenant_id == tenant_id).all()
    }

    saida = []
    for lt in lotes:
        sel = sellers_map.get(lt.id_seller) if lt.id_seller else None
        prop = props_map.get(lt.id_property) if lt.id_property else None
        saida.append(
            {
                "id_batch": lt.id_batch,
                "id_seller": lt.id_seller,
                "id_property": lt.id_property,
                "seller_name": sel.name_seller if sel else None,
                "seller_license": sel.license_number_seller if sel else None,
                "property_label": format_property_label(prop) if prop else None,
                "datetime_batch_creation": lt.datetime_batch_creation,
            }
        )
    return saida


@router.post("/lotes", response_model=WaterBatchResposta, status_code=status.HTTP_201_CREATED)
def criar_lote(
    dados: WaterBatchCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    sel = (
        db.query(WaterSellerModel)
        .filter(WaterSellerModel.id_seller == dados.id_seller, WaterSellerModel.tenant_id == tenant_id)
        .first()
    )
    if not sel:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado nesta conta.")

    prop = (
        db.query(PropertyModel)
        .filter(PropertyModel.id_property == dados.id_property, PropertyModel.tenant_id == tenant_id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Propriedade não encontrada nesta conta.")

    novo = WaterBatchModel(
        tenant_id=tenant_id,
        id_seller=sel.id_seller,
        id_property=prop.id_property,
        datetime_batch_creation=dados.datetime_batch_creation or datetime.utcnow(),
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return {
        "id_batch": novo.id_batch,
        "id_seller": novo.id_seller,
        "id_property": novo.id_property,
        "seller_name": sel.name_seller,
        "seller_license": sel.license_number_seller,
        "property_label": format_property_label(prop),
        "datetime_batch_creation": novo.datetime_batch_creation,
    }


@router.delete("/lotes/{id_batch}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_lote(
    id_batch: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    lote = (
        db.query(WaterBatchModel)
        .filter(WaterBatchModel.id_batch == id_batch, WaterBatchModel.tenant_id == tenant_id)
        .first()
    )
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")

    em_uso = (
        db.query(WaterAdmissionModel)
        .filter(WaterAdmissionModel.id_batch == id_batch, WaterAdmissionModel.tenant_id == tenant_id)
        .first()
    )
    if em_uso:
        raise HTTPException(status_code=400, detail="Lote já possui registros de admissão hídrica.")

    db.delete(lote)
    db.commit()
    return None


# ==========================================
# 8. OPERAÇÃO 1: ADMISSÃO DE ÁGUA/EFLUENTE (Water_Admission)
# ==========================================
@router.get("/admissoes", response_model=List[WaterAdmissionResposta])
def listar_admissoes(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    admissoes = (
        db.query(WaterAdmissionModel)
        .filter(WaterAdmissionModel.tenant_id == tenant_id)
        .order_by(WaterAdmissionModel.id_admission.desc())
        .all()
    )
    batches_map = {
        b.id_batch: b
        for b in db.query(WaterBatchModel).filter(WaterBatchModel.tenant_id == tenant_id).all()
    }
    sellers_map = {
        s.id_seller: s
        for s in db.query(WaterSellerModel).filter(WaterSellerModel.tenant_id == tenant_id).all()
    }
    props_map = {
        p.id_property: p
        for p in db.query(PropertyModel).filter(PropertyModel.tenant_id == tenant_id).all()
    }
    meas_map = {
        m.id_measurement: m
        for m in db.query(MeasurementModel).filter(MeasurementModel.tenant_id == tenant_id).all()
    }

    saida = []
    for adm in admissoes:
        bt = batches_map.get(adm.id_batch) if adm.id_batch else None
        sel = sellers_map.get(bt.id_seller) if (bt and bt.id_seller) else None
        prop = props_map.get(bt.id_property) if (bt and bt.id_property) else None
        batch_lbl = (
            f"Lote #{bt.id_batch} · {sel.name_seller if sel else 'Origem'} → {prop.property_address if prop else 'Unidade'}"
            if bt
            else f"Lote #{adm.id_batch}"
        )
        m_obj = meas_map.get(adm.id_measurement) if adm.id_measurement else None
        saida.append(
            {
                "id_admission": adm.id_admission,
                "id_batch": adm.id_batch,
                "batch_label": batch_lbl,
                "volume_admitted": float(adm.volume_admitted or 0.0),
                "id_measurement": adm.id_measurement,
                "measurement": serialize_measurement(m_obj),
            }
        )
    return saida


@router.post("/admissoes", response_model=WaterAdmissionResposta, status_code=status.HTTP_201_CREATED)
def criar_admissao(
    dados: WaterAdmissionCriar,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    lote = (
        db.query(WaterBatchModel)
        .filter(WaterBatchModel.id_batch == dados.id_batch, WaterBatchModel.tenant_id == tenant_id)
        .first()
    )
    if not lote:
        raise HTTPException(status_code=404, detail="Lote hídrico não encontrado nesta conta.")

    medicao = _resolver_ou_criar_medicao(db, tenant_id, dados.id_measurement, dados.measurement)
    ml_status, conama_ok = avaliar_qualidade_medicao(medicao)

    nova_adm = WaterAdmissionModel(
        tenant_id=tenant_id,
        id_batch=lote.id_batch,
        volume_admitted=float(dados.volume_admitted),
        id_measurement=medicao.id_measurement,
    )
    db.add(nova_adm)
    db.flush()

    sel = (
        db.query(WaterSellerModel)
        .filter(WaterSellerModel.id_seller == lote.id_seller, WaterSellerModel.tenant_id == tenant_id)
        .first()
    )
    prop = (
        db.query(PropertyModel)
        .filter(PropertyModel.id_property == lote.id_property, PropertyModel.tenant_id == tenant_id)
        .first()
    )
    batch_lbl = f"Lote #{lote.id_batch} · {sel.name_seller if sel else 'Origem'} → {prop.property_address if prop else 'Unidade'}"

    evento = HistoryEventModel(
        tenant_id=tenant_id,
        event_type="medicao",
        event_label="Admissão de Lote Hídrico",
        event_point=prop.property_address if prop else f"Lote #{lote.id_batch}",
        event_description=(
            f"Entrada de {nova_adm.volume_admitted:.0f} m³ ({batch_lbl}). "
            f"Laudo #{medicao.id_measurement}: pH {medicao.ph_measurement:.1f}, DBO {medicao.bod_measurement:.1f} mg/L ({ml_status})."
        ),
        event_severity="normal" if conama_ok else "medio",
        id_reference=nova_adm.id_admission,
        reference_type="water_admission",
        created_by=ctx.name or ctx.email or "Operação Hídrica",
    )
    db.add(evento)
    db.commit()
    db.refresh(nova_adm)

    return {
        "id_admission": nova_adm.id_admission,
        "id_batch": nova_adm.id_batch,
        "batch_label": batch_lbl,
        "volume_admitted": float(nova_adm.volume_admitted),
        "id_measurement": medicao.id_measurement,
        "measurement": serialize_measurement(medicao),
    }


@router.delete("/admissoes/{id_admission}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_admissao(
    id_admission: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    adm = (
        db.query(WaterAdmissionModel)
        .filter(
            WaterAdmissionModel.id_admission == id_admission,
            WaterAdmissionModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not adm:
        raise HTTPException(status_code=404, detail="Registro de admissão não encontrado.")
    db.delete(adm)
    db.commit()
    return None


# ==========================================
# 9. OPERAÇÃO 2: ARMAZENAMENTO HÍDRICO (Water_Storage)
# ==========================================
@router.get("/armazenamentos", response_model=List[WaterStorageResposta])
def listar_armazenamentos(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    registros = (
        db.query(WaterStorageModel)
        .filter(WaterStorageModel.tenant_id == tenant_id)
        .order_by(WaterStorageModel.id_storage.desc())
        .all()
    )
    props_map = {
        p.id_property: p
        for p in db.query(PropertyModel).filter(PropertyModel.tenant_id == tenant_id).all()
    }
    meas_map = {
        m.id_measurement: m
        for m in db.query(MeasurementModel).filter(MeasurementModel.tenant_id == tenant_id).all()
    }

    return [
        {
            "id_storage": st.id_storage,
            "id_property": st.id_property,
            "property_label": format_property_label(props_map.get(st.id_property)) if st.id_property else None,
            "volume_stored": float(st.volume_stored or 0.0),
            "id_measurement": st.id_measurement,
            "measurement": serialize_measurement(meas_map.get(st.id_measurement)) if st.id_measurement else None,
        }
        for st in registros
    ]


@router.post("/armazenamentos", response_model=WaterStorageResposta, status_code=status.HTTP_201_CREATED)
def criar_armazenamento(
    dados: WaterStorageCriar,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    prop = (
        db.query(PropertyModel)
        .filter(PropertyModel.id_property == dados.id_property, PropertyModel.tenant_id == tenant_id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Propriedade não encontrada nesta conta.")

    medicao = _resolver_ou_criar_medicao(db, tenant_id, dados.id_measurement, dados.measurement)
    ml_status, conama_ok = avaliar_qualidade_medicao(medicao)

    novo_st = WaterStorageModel(
        tenant_id=tenant_id,
        id_property=prop.id_property,
        volume_stored=float(dados.volume_stored),
        id_measurement=medicao.id_measurement,
    )
    db.add(novo_st)
    db.flush()

    evento = HistoryEventModel(
        tenant_id=tenant_id,
        event_type="providencia",
        event_label="Controle de Armazenamento Hídrico",
        event_point=format_property_label(prop),
        event_description=(
            f"Volume estocado de {novo_st.volume_stored:.0f} m³ registrado na unidade. "
            f"Laudo #{medicao.id_measurement}: OD {medicao.o2_dissolved_measurement:.1f} mg/L, "
            f"Condutividade {medicao.conductivity_measurement:.0f} µS/cm ({ml_status})."
        ),
        event_severity="normal" if conama_ok else "medio",
        id_reference=novo_st.id_storage,
        reference_type="water_storage",
        created_by=ctx.name or ctx.email or "Operação Hídrica",
    )
    db.add(evento)
    db.commit()
    db.refresh(novo_st)

    return {
        "id_storage": novo_st.id_storage,
        "id_property": novo_st.id_property,
        "property_label": format_property_label(prop),
        "volume_stored": float(novo_st.volume_stored),
        "id_measurement": medicao.id_measurement,
        "measurement": serialize_measurement(medicao),
    }


@router.delete("/armazenamentos/{id_storage}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_armazenamento(
    id_storage: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    st = (
        db.query(WaterStorageModel)
        .filter(WaterStorageModel.id_storage == id_storage, WaterStorageModel.tenant_id == tenant_id)
        .first()
    )
    if not st:
        raise HTTPException(status_code=404, detail="Registro de armazenamento não encontrado.")
    db.delete(st)
    db.commit()
    return None


# ==========================================
# 10. OPERAÇÃO 3: DESCARTE / FERTIRRIGAÇÃO (Water_Disposal)
# ==========================================
@router.get("/descartes", response_model=List[WaterDisposalResposta])
def listar_descartes(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    registros = (
        db.query(WaterDisposalModel)
        .filter(WaterDisposalModel.tenant_id == tenant_id)
        .order_by(WaterDisposalModel.id_disposal.desc())
        .all()
    )
    areas_map = {
        a.id_disposal_area: a
        for a in db.query(AreaOfDisposalModel).filter(AreaOfDisposalModel.tenant_id == tenant_id).all()
    }
    props_map = {
        p.id_property: p
        for p in db.query(PropertyModel).filter(PropertyModel.tenant_id == tenant_id).all()
    }
    meas_map = {
        m.id_measurement: m
        for m in db.query(MeasurementModel).filter(MeasurementModel.tenant_id == tenant_id).all()
    }

    saida = []
    for d in registros:
        area = areas_map.get(d.id_disposal_area) if d.id_disposal_area else None
        prop = props_map.get(area.id_property) if (area and area.id_property) else None
        lic = area.license_number_disposal or f"Zona #{d.id_disposal_area}" if area else f"Zona #{d.id_disposal_area}"
        lbl = f"{lic} — {prop.property_address}" if prop else lic
        saida.append(
            {
                "id_disposal": d.id_disposal,
                "id_disposal_area": d.id_disposal_area,
                "disposal_area_label": lbl,
                "is_area_validated": bool(area.is_validated_for_disposal) if area else False,
                "volume_disposed": float(d.volume_disposed or 0.0),
                "id_measurement": d.id_measurement,
                "measurement": serialize_measurement(meas_map.get(d.id_measurement)) if d.id_measurement else None,
                "generated_alert_code": None,
                "generated_occurrence_code": None,
            }
        )
    return saida


@router.post("/descartes", response_model=WaterDisposalResposta, status_code=status.HTTP_201_CREATED)
def criar_descarte(
    dados: WaterDisposalCriar,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    area = (
        db.query(AreaOfDisposalModel)
        .filter(
            AreaOfDisposalModel.id_disposal_area == dados.id_disposal_area,
            AreaOfDisposalModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not area:
        raise HTTPException(status_code=404, detail="Área de descarte não encontrada nesta conta.")

    prop = (
        db.query(PropertyModel)
        .filter(PropertyModel.id_property == area.id_property, PropertyModel.tenant_id == tenant_id)
        .first()
    )
    reg = (
        db.query(EnvironmentalRegulatorModel)
        .filter(
            EnvironmentalRegulatorModel.id_regulator == area.id_regulator,
            EnvironmentalRegulatorModel.tenant_id == tenant_id,
        )
        .first()
    )

    medicao = _resolver_ou_criar_medicao(db, tenant_id, dados.id_measurement, dados.measurement)
    ml_status, conama_ok = avaliar_qualidade_medicao(medicao)

    novo_desc = WaterDisposalModel(
        tenant_id=tenant_id,
        id_disposal_area=area.id_disposal_area,
        volume_disposed=float(dados.volume_disposed),
        id_measurement=medicao.id_measurement,
    )
    db.add(novo_desc)
    db.flush()

    lic_str = area.license_number_disposal or f"Zona #{area.id_disposal_area}"
    area_lbl = f"{lic_str} — {prop.property_address}" if prop else lic_str

    generated_alert_code = None
    generated_occ_code = None

    # Fiscalização automática: área sem homologação ambiental OU laudo reprovado pela IA / CONAMA
    irregularidades = []
    if not bool(area.is_validated_for_disposal):
        irregularidades.append(
            f"Área de descarte ({lic_str}) não homologada pelo órgão {reg.name_regulator if reg else 'ambiental'}"
        )
    if not conama_ok or "Poluída" in ml_status:
        irregularidades.append(
            f"Laudo #{medicao.id_measurement} fora dos padrões ambientais ({ml_status}: "
            f"pH {medicao.ph_measurement:.1f}, DBO {medicao.bod_measurement:.1f} mg/L, OD {medicao.o2_dissolved_measurement:.1f} mg/L)"
        )

    if irregularidades:
        ocr_code, al_code = _gerar_codigos_unicos(db, tenant_id)
        responsavel = _obter_responsavel_padrao(db, tenant_id, fallback=ctx.name or "Gestor Ambiental")
        metricas_ocr = (
            f"VOL: {novo_desc.volume_disposed:.0f} m³ | "
            f"PH: {medicao.ph_measurement:.1f} | "
            f"DBO: {medicao.bod_measurement:.1f} mg/L | "
            f"DQO: {medicao.cod_measurement:.1f} mg/L"
        )

        nova_ocr = OccurrenceModel(
            tenant_id=tenant_id,
            code_occurrence=ocr_code,
            title_occurrence=f"Descarte Irregular / Não Conforme — {lic_str}",
            location_occurrence=area_lbl,
            responsible_occurrence=responsavel,
            metrics_occurrence=metricas_ocr,
            status_occurrence="analise",
            risk_occurrence="critico",
        )
        db.add(nova_ocr)
        db.flush()

        params_chips = [
            f"Volume: {novo_desc.volume_disposed:.0f} m³",
            f"pH: {medicao.ph_measurement:.1f}",
            f"DBO: {medicao.bod_measurement:.1f} mg/L",
            f"OD: {medicao.o2_dissolved_measurement:.1f} mg/L",
            f"Licença: {'Validada' if area.is_validated_for_disposal else 'Pendente'}",
        ]

        novo_alerta = AlertModel(
            tenant_id=tenant_id,
            code_alert=al_code,
            point_name=area_lbl,
            severity="critical",
            status="active",
            message=" | ".join(irregularidades),
            params_json=json.dumps(params_chips, ensure_ascii=False),
            recommendation=(
                "Suspender fertirrigação/descarte imediatamente no talhão, redirecionar o lote para bacia de "
                "estabilização (Water_Storage) e regularizar outorga/neutralização antes de nova aplicação."
            ),
            responsible=responsavel,
            id_occurrence=nova_ocr.id_occurrence,
            code_occurrence=ocr_code,
            is_viewed=0,
        )
        db.add(novo_alerta)

        evento_crit = HistoryEventModel(
            tenant_id=tenant_id,
            event_type="alerta",
            event_label="Não Conformidade em Descarte Hídrico",
            event_point=area_lbl,
            event_description=(
                f"Descarte de {novo_desc.volume_disposed:.0f} m³ acionou fiscalização automática: "
                f"{'; '.join(irregularidades)}. Gerados Alerta #{al_code} e Ocorrência #{ocr_code}."
            ),
            event_severity="critico",
            id_reference=novo_desc.id_disposal,
            reference_type="water_disposal",
            created_by=ctx.name or ctx.email or "Fiscalização Automática",
        )
        db.add(evento_crit)

        generated_alert_code = al_code
        generated_occ_code = ocr_code
    else:
        evento_ok = HistoryEventModel(
            tenant_id=tenant_id,
            event_type="providencia",
            event_label="Descarte / Fertirrigação Homologada",
            event_point=area_lbl,
            event_description=(
                f"Aplicação controlada de {novo_desc.volume_disposed:.0f} m³ em área licenciada "
                f"({reg.name_regulator if reg else 'Órgão Ambiental'}). Laudo #{medicao.id_measurement} aprovado ({ml_status})."
            ),
            event_severity="normal",
            id_reference=novo_desc.id_disposal,
            reference_type="water_disposal",
            created_by=ctx.name or ctx.email or "Operação Hídrica",
        )
        db.add(evento_ok)

    db.commit()
    db.refresh(novo_desc)

    return {
        "id_disposal": novo_desc.id_disposal,
        "id_disposal_area": novo_desc.id_disposal_area,
        "disposal_area_label": area_lbl,
        "is_area_validated": bool(area.is_validated_for_disposal),
        "volume_disposed": float(novo_desc.volume_disposed),
        "id_measurement": medicao.id_measurement,
        "measurement": serialize_measurement(medicao),
        "generated_alert_code": generated_alert_code,
        "generated_occurrence_code": generated_occ_code,
    }


@router.delete("/descartes/{id_disposal}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_descarte(
    id_disposal: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    d = (
        db.query(WaterDisposalModel)
        .filter(
            WaterDisposalModel.id_disposal == id_disposal,
            WaterDisposalModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not d:
        raise HTTPException(status_code=404, detail="Registro de descarte não encontrado.")
    db.delete(d)
    db.commit()
    return None


# ==========================================
# 11. CARGA INICIAL DE DEMONSTRAÇÃO AGROINDUSTRIAL (OPCIONAL POR BOTÃO)
# ==========================================
@router.post("/seed-exemplo", summary="Popular registros iniciais de demonstração nas 9 tabelas do Ciclo Hídrico")
def popular_dados_exemplo(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id

    # Cria registros realistas do setor sucroenergético exclusivamente para este tenant
    p_norte = PropertyModel(
        tenant_id=tenant_id,
        property_address="Cooperativa Vale Verde — Unidade Norte (Fazenda Santa Elisa)",
        property_city="Ribeirão Preto - SP",
    )
    p_sul = PropertyModel(
        tenant_id=tenant_id,
        property_address="Cooperativa Vale Verde — Unidade Sul (Talhão Boa Vista)",
        property_city="Piracicaba - SP",
    )
    db.add_all([p_norte, p_sul])

    s1 = WaterSellerModel(
        tenant_id=tenant_id,
        cnpj_seller="14.285.910/0001-62",
        name_seller="Usina BioEnergia São Martinho S/A",
        license_number_seller="OUT-ANA-2026/8841",
    )
    s2 = WaterSellerModel(
        tenant_id=tenant_id,
        cnpj_seller="29.401.773/0001-19",
        name_seller="Estação de Reúso Agroindustrial Mogiana",
        license_number_seller="LIC-CETESB-44920",
    )
    db.add_all([s1, s2])

    r_cetesb = EnvironmentalRegulatorModel(
        tenant_id=tenant_id,
        name_regulator="CETESB",
        jurisdiction_regulator="Estadual — São Paulo (P4.231 Vinhaça)",
    )
    r_ana = EnvironmentalRegulatorModel(
        tenant_id=tenant_id,
        name_regulator="ANA — Agência Nacional de Águas",
        jurisdiction_regulator="Federal — Bacia do Rio Pardo / Piracicaba",
    )
    db.add_all([r_cetesb, r_ana])
    db.flush()

    area_ok = AreaOfDisposalModel(
        tenant_id=tenant_id,
        id_property=p_norte.id_property,
        x_coordinate=34.0,
        y_coordinate=62.0,
        is_validated_for_disposal=True,
        license_number_disposal="FERT-CETESB-1092",
        id_regulator=r_cetesb.id_regulator,
    )
    area_pendente = AreaOfDisposalModel(
        tenant_id=tenant_id,
        id_property=p_sul.id_property,
        x_coordinate=72.0,
        y_coordinate=38.0,
        is_validated_for_disposal=False,
        license_number_disposal="EM-ANALISE-ANA-304",
        id_regulator=r_ana.id_regulator,
    )
    db.add_all([area_ok, area_pendente])

    lote_1 = WaterBatchModel(
        tenant_id=tenant_id,
        id_seller=s1.id_seller,
        id_property=p_norte.id_property,
        datetime_batch_creation=datetime.utcnow(),
    )
    lote_2 = WaterBatchModel(
        tenant_id=tenant_id,
        id_seller=s2.id_seller,
        id_property=p_sul.id_property,
        datetime_batch_creation=datetime.utcnow(),
    )
    db.add_all([lote_1, lote_2])

    m_adm = MeasurementModel(
        tenant_id=tenant_id,
        ph_measurement=7.1,
        o2_dissolved_measurement=6.4,
        turbidity_measurement=18.0,
        conductivity_measurement=410.0,
        bod_measurement=22.0,
        cod_measurement=68.0,
        nitrogen_phosphorus_measurement=14.5,
    )
    m_sto = MeasurementModel(
        tenant_id=tenant_id,
        ph_measurement=7.3,
        o2_dissolved_measurement=6.8,
        turbidity_measurement=15.0,
        conductivity_measurement=390.0,
        bod_measurement=18.0,
        cod_measurement=54.0,
        nitrogen_phosphorus_measurement=12.0,
    )
    m_dis = MeasurementModel(
        tenant_id=tenant_id,
        ph_measurement=6.9,
        o2_dissolved_measurement=5.9,
        turbidity_measurement=21.0,
        conductivity_measurement=430.0,
        bod_measurement=26.0,
        cod_measurement=79.0,
        nitrogen_phosphorus_measurement=16.2,
    )
    db.add_all([m_adm, m_sto, m_dis])
    db.flush()

    adm = WaterAdmissionModel(
        tenant_id=tenant_id,
        id_batch=lote_1.id_batch,
        volume_admitted=3200.0,
        id_measurement=m_adm.id_measurement,
    )
    sto = WaterStorageModel(
        tenant_id=tenant_id,
        id_property=p_norte.id_property,
        volume_stored=1850.0,
        id_measurement=m_sto.id_measurement,
    )
    dis = WaterDisposalModel(
        tenant_id=tenant_id,
        id_disposal_area=area_ok.id_disposal_area,
        volume_disposed=1350.0,
        id_measurement=m_dis.id_measurement,
    )
    db.add_all([adm, sto, dis])

    ev = HistoryEventModel(
        tenant_id=tenant_id,
        event_type="providencia",
        event_label="Ciclo Hídrico Inicializado",
        event_point="Cooperativa Vale Verde",
        event_description=(
            "Cadastros operacionais de Propriedades, Fornecedores, Órgãos Reguladores, Lotes, "
            "Laudos Físico-Químicos e Operações de Admissão, Armazenamento e Fertirrigação registrados."
        ),
        event_severity="normal",
        created_by=ctx.name or ctx.email or "Sistema",
    )
    db.add(ev)
    db.commit()

    return {
        "success": True,
        "summary": calcular_resumo_ciclo_hidrico(db=db, tenant_id=tenant_id),
    }

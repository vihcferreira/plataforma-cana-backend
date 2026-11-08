from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_tenant import get_current_tenant
from database import MapMeasurementHistoryModel, MapPointModel, get_db
from schemas import (
    MapAtualizar,
    MapCriar,
    MapMeasurementHistoryResposta,
    MapResposta,
    TelemetriaToggleRequest,
)
from services import telemetry_service
from services.incident_service import registrar_snapshot_medicao_mapa
from services.water_quality_service import calculate_point_risk, utcnow

router = APIRouter(tags=["Mapa"])

MAX_HISTORY_RECORDS = 2000


@router.get("/", response_model=List[MapResposta], summary="Listar todos os pontos do mapa do usuário")
def listar_mapa(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(MapPointModel)
        .filter(MapPointModel.tenant_id == tenant_id)
        .order_by(MapPointModel.id_map_point.asc())
        .all()
    )


@router.get(
    "/historico-medicoes",
    response_model=List[MapMeasurementHistoryResposta],
    summary="Buscar histórico de medições do usuário para gráficos",
)
def listar_historico_medicoes(
    dias: Optional[int] = None,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    query = db.query(MapMeasurementHistoryModel).filter(
        MapMeasurementHistoryModel.tenant_id == tenant_id
    )
    if dias and dias > 0:
        limite = utcnow() - timedelta(days=dias)
        query = query.filter(MapMeasurementHistoryModel.recorded_at >= limite)

    # Busca as medições mais recentes com limite defensivo e reordena cronologicamente para os gráficos
    ultimos = (
        query.order_by(MapMeasurementHistoryModel.recorded_at.desc())
        .limit(MAX_HISTORY_RECORDS)
        .all()
    )
    if ultimos:
        ultimos.reverse()
        return ultimos

    pontos = (
        db.query(MapPointModel)
        .filter(MapPointModel.tenant_id == tenant_id)
        .all()
    )
    if not pontos:
        return []

    snapshots: List[MapMeasurementHistoryModel] = []
    for p in pontos:
        snap = registrar_snapshot_medicao_mapa(
            db=db,
            tenant_id=tenant_id,
            ponto=p,
            recorded_at=p.datetime_map_point_update or p.datetime_map_point_creation or utcnow(),
        )
        snapshots.append(snap)
    db.commit()
    for snap in snapshots:
        db.refresh(snap)

    if dias and dias > 0:
        limite = utcnow() - timedelta(days=dias)
        snapshots = [s for s in snapshots if s.recorded_at and s.recorded_at >= limite]

    snapshots.sort(key=lambda item: item.recorded_at or utcnow())
    return snapshots


@router.get("/telemetria/status", summary="Obter status do serviço de telemetria autônoma do usuário")
def obter_status_telemetria_endpoint(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return telemetry_service.obter_status_telemetria(tenant_id=tenant_id, db=db)


@router.post("/telemetria/toggle", summary="Ativar ou desativar o serviço de telemetria autônoma do usuário")
def toggle_telemetria_endpoint(
    dados: TelemetriaToggleRequest,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return telemetry_service.definir_status_telemetria(
        ativo=dados.active,
        tenant_id=tenant_id,
        db=db,
    )


@router.post("/", response_model=MapResposta, status_code=status.HTTP_201_CREATED, summary="Criar novo ponto do mapa")
def criar_mapa(
    dados: MapCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ponto_existente = (
        db.query(MapPointModel.id_map_point)
        .filter(
            MapPointModel.tenant_id == tenant_id,
            MapPointModel.code_map_point == dados.code_map_point,
        )
        .first()
    )
    if ponto_existente:
        raise HTTPException(status_code=400, detail=f"Já existe um ponto com o código '{dados.code_map_point}'.")

    campos_definidos = dados.model_fields_set
    risco_calculado = calculate_point_risk(
        ph=dados.ph_map_point,
        turbidity=dados.turbidity_map_point,
        volume=dados.volume_map_point,
        contaminant=dados.contaminant_map_point,
    )
    risco_final = dados.risk_map_point if "risk_map_point" in campos_definidos else risco_calculado

    agora = utcnow()
    novo_point_map = MapPointModel(
        tenant_id=tenant_id,
        code_map_point=dados.code_map_point,
        name_map_point=dados.name_map_point,
        grid_coordinate_map_point=dados.grid_coordinate_map_point,
        geo_coordinate_map_point=dados.geo_coordinate_map_point,
        pos_x_map_point=dados.pos_x_map_point,
        pos_y_map_point=dados.pos_y_map_point,
        ph_map_point=dados.ph_map_point,
        turbidity_map_point=dados.turbidity_map_point,
        contaminant_map_point=dados.contaminant_map_point,
        volume_map_point=dados.volume_map_point,
        risk_map_point=risco_final,
        datetime_map_point_creation=agora,
        datetime_map_point_update=agora,
    )

    db.add(novo_point_map)
    db.flush()
    registrar_snapshot_medicao_mapa(db=db, tenant_id=tenant_id, ponto=novo_point_map, recorded_at=agora)
    db.commit()
    db.refresh(novo_point_map)
    return novo_point_map


@router.put("/{id_map}", response_model=MapResposta, summary="Atualizar ponto do mapa")
def atualizar_mapa(
    id_map: int,
    dados: MapAtualizar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    mapa = (
        db.query(MapPointModel)
        .filter(
            MapPointModel.id_map_point == id_map,
            MapPointModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not mapa:
        raise HTTPException(status_code=404, detail="Ponto do mapa não encontrado.")

    campos_atualizacao = dados.model_dump(exclude_unset=True)
    novo_codigo = campos_atualizacao.get("code_map_point")
    if novo_codigo and novo_codigo != mapa.code_map_point:
        conflito = (
            db.query(MapPointModel.id_map_point)
            .filter(
                MapPointModel.tenant_id == tenant_id,
                MapPointModel.code_map_point == novo_codigo,
            )
            .first()
        )
        if conflito:
            raise HTTPException(status_code=400, detail=f"Já existe um ponto com o código '{novo_codigo}'.")

    for campo, valor in campos_atualizacao.items():
        setattr(mapa, campo, valor)

    metricas_alteradas = any(
        k in campos_atualizacao
        for k in ("ph_map_point", "turbidity_map_point", "volume_map_point", "contaminant_map_point")
    )
    if metricas_alteradas and "risk_map_point" not in campos_atualizacao:
        mapa.risk_map_point = calculate_point_risk(
            ph=mapa.ph_map_point,
            turbidity=mapa.turbidity_map_point,
            volume=mapa.volume_map_point,
            contaminant=mapa.contaminant_map_point,
        )

    agora = utcnow()
    mapa.datetime_map_point_update = agora
    registrar_snapshot_medicao_mapa(db=db, tenant_id=tenant_id, ponto=mapa, recorded_at=agora)
    db.commit()
    db.refresh(mapa)
    return mapa


@router.delete("/{id_map}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir ponto do mapa")
def excluir_mapa(
    id_map: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    mapa = (
        db.query(MapPointModel)
        .filter(
            MapPointModel.id_map_point == id_map,
            MapPointModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not mapa:
        raise HTTPException(status_code=404, detail="Ponto do mapa não encontrado.")

    db.delete(mapa)
    db.commit()
    return None

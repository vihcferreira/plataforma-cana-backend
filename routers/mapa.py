from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from auth_tenant import get_current_tenant
from database import get_db, MapPointModel, MapMeasurementHistoryModel
from schemas import MapCriar, MapAtualizar, MapResposta, MapMeasurementHistoryResposta
from services import telemetry_service

router = APIRouter(tags=["Mapa"])


class TelemetriaToggleRequest(BaseModel):
    active: bool


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
    """
    Retorna os registros históricos de medições coletados ao longo do tempo para o tenant autenticado.
    Mesmo que um ponto seja deletado do mapa, os dados preservados aqui alimentam
    os gráficos de evolução temporal exclusivamente deste usuário.
    """
    query = db.query(MapMeasurementHistoryModel).filter(
        MapMeasurementHistoryModel.tenant_id == tenant_id
    )
    if dias and dias > 0:
        limite = datetime.utcnow() - timedelta(days=dias)
        query = query.filter(MapMeasurementHistoryModel.recorded_at >= limite)

    registros = query.order_by(MapMeasurementHistoryModel.recorded_at.asc()).all()

    # Se a tabela de histórico do tenant ainda estiver vazia mas existirem pontos no mapa dele, sincroniza-os
    if not registros:
        pontos = (
            db.query(MapPointModel)
            .filter(MapPointModel.tenant_id == tenant_id)
            .all()
        )
        if pontos:
            for p in pontos:
                hist = MapMeasurementHistoryModel(
                    tenant_id=tenant_id,
                    code_map_point=p.code_map_point,
                    name_map_point=p.name_map_point,
                    ph=p.ph_map_point,
                    turbidity=p.turbidity_map_point,
                    contaminant=p.contaminant_map_point,
                    volume=getattr(p, "volume_map_point", 4000.0) or 4000.0,
                    risk=p.risk_map_point,
                    recorded_at=p.datetime_map_point_update
                    or p.datetime_map_point_creation
                    or datetime.utcnow(),
                )
                db.add(hist)
            db.commit()

            sync_query = db.query(MapMeasurementHistoryModel).filter(
                MapMeasurementHistoryModel.tenant_id == tenant_id
            )
            if dias and dias > 0:
                limite = datetime.utcnow() - timedelta(days=dias)
                sync_query = sync_query.filter(MapMeasurementHistoryModel.recorded_at >= limite)
            registros = sync_query.order_by(MapMeasurementHistoryModel.recorded_at.asc()).all()

    return registros


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


@router.get("/{id_map}", response_model=MapResposta, summary="Buscar ponto do mapa por ID")
def buscar_mapa(
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
    return mapa


@router.post("/", response_model=MapResposta, status_code=status.HTTP_201_CREATED, summary="Criar novo ponto do mapa")
def criar_mapa(
    dados: MapCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    # Verifica se já existe um ponto com o mesmo código dentro do escopo deste usuário
    ponto_existente = (
        db.query(MapPointModel)
        .filter(
            MapPointModel.tenant_id == tenant_id,
            MapPointModel.code_map_point == dados.code_map_point,
        )
        .first()
    )
    if ponto_existente:
        raise HTTPException(status_code=400, detail=f"Já existe um ponto com o código '{dados.code_map_point}'.")

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
        risk_map_point=dados.risk_map_point,
    )

    db.add(novo_point_map)
    db.commit()
    db.refresh(novo_point_map)

    # Grava no histórico permanente de medições do tenant para preservação nos gráficos
    historico_medicao = MapMeasurementHistoryModel(
        tenant_id=tenant_id,
        code_map_point=novo_point_map.code_map_point,
        name_map_point=novo_point_map.name_map_point,
        ph=novo_point_map.ph_map_point,
        turbidity=novo_point_map.turbidity_map_point,
        contaminant=novo_point_map.contaminant_map_point,
        volume=novo_point_map.volume_map_point,
        risk=novo_point_map.risk_map_point,
        recorded_at=novo_point_map.datetime_map_point_creation or datetime.utcnow(),
    )
    db.add(historico_medicao)
    db.commit()

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
            db.query(MapPointModel)
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

    db.commit()
    db.refresh(mapa)

    # Grava o snapshot atualizado no histórico permanente de medições deste tenant
    historico_medicao = MapMeasurementHistoryModel(
        tenant_id=tenant_id,
        code_map_point=mapa.code_map_point,
        name_map_point=mapa.name_map_point,
        ph=mapa.ph_map_point,
        turbidity=mapa.turbidity_map_point,
        contaminant=mapa.contaminant_map_point,
        volume=mapa.volume_map_point,
        risk=mapa.risk_map_point,
        recorded_at=datetime.utcnow(),
    )
    db.add(historico_medicao)
    db.commit()

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

    # A exclusão remove o ponto da visão ativa do mapa, mas o histórico permanece em Map_Measurement_History do tenant
    db.delete(mapa)
    db.commit()
    return None

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from database import get_db, MapPointModel, MapMeasurementHistoryModel
from schemas import MapCriar, MapAtualizar, MapResposta, MapMeasurementHistoryResposta

router = APIRouter(tags=["Mapa"])

@router.get("/", response_model=List[MapResposta], summary="Listar todos os pontos do mapa")
def listar_mapa(db: Session = Depends(get_db)):
    return db.query(MapPointModel).order_by(MapPointModel.id_map_point.asc()).all()

@router.get("/historico-medicoes", response_model=List[MapMeasurementHistoryResposta], summary="Buscar histórico de medições para gráficos")
def listar_historico_medicoes(dias: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Retorna os registros históricos de medições coletados ao longo do tempo.
    Mesmo que um ponto seja deletado do mapa, os dados preservados aqui alimentam
    os gráficos de evolução temporal.
    """
    query = db.query(MapMeasurementHistoryModel)
    if dias and dias > 0:
        limite = datetime.utcnow() - timedelta(days=dias)
        query = query.filter(MapMeasurementHistoryModel.recorded_at >= limite)
    
    registros = query.order_by(MapMeasurementHistoryModel.recorded_at.asc()).all()

    # Se a tabela de histórico ainda estiver vazia mas existirem pontos no mapa, sincroniza-os
    if not registros:
        pontos = db.query(MapPointModel).all()
        for p in pontos:
            hist = MapMeasurementHistoryModel(
                code_map_point=p.code_map_point,
                name_map_point=p.name_map_point,
                ph=p.ph_map_point,
                turbidity=p.turbidity_map_point,
                contaminant=p.contaminant_map_point,
                volume=getattr(p, "volume_map_point", 4000.0) or 4000.0,
                risk=p.risk_map_point,
                recorded_at=p.datetime_map_point_update or p.datetime_map_point_creation or datetime.utcnow()
            )
            db.add(hist)
        db.commit()
        registros = db.query(MapMeasurementHistoryModel).order_by(MapMeasurementHistoryModel.recorded_at.asc()).all()

    return registros

from pydantic import BaseModel

class TelemetriaToggleRequest(BaseModel):
    active: bool

from services import telemetry_service

@router.get("/telemetria/status", summary="Obter status do serviço de telemetria autônoma")
def obter_status_telemetria_endpoint():
    return telemetry_service.obter_status_telemetria()

@router.post("/telemetria/toggle", summary="Ativar ou desativar o serviço de telemetria autônoma")
def toggle_telemetria_endpoint(dados: TelemetriaToggleRequest):
    return telemetry_service.definir_status_telemetria(dados.active)

@router.get("/{id_map}", response_model=MapResposta, summary="Buscar ponto do mapa por ID")
def buscar_mapa(id_map: int, db: Session = Depends(get_db)):
    mapa = db.query(MapPointModel).filter(MapPointModel.id_map_point == id_map).first()
    if not mapa:
        raise HTTPException(status_code=404, detail="Ponto do mapa não encontrado.")
    return mapa

@router.post("/", response_model=MapResposta, status_code=status.HTTP_201_CREATED, summary="Criar novo ponto do mapa")
def criar_mapa(dados: MapCriar, db: Session = Depends(get_db)):
    # Verifica se já existe um ponto com o mesmo código
    ponto_existente = db.query(MapPointModel).filter(MapPointModel.code_map_point == dados.code_map_point).first()
    if ponto_existente:
        raise HTTPException(status_code=400, detail=f"Já existe um ponto com o código '{dados.code_map_point}'.")

    novo_point_map = MapPointModel(
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
        risk_map_point=dados.risk_map_point
    )
    
    db.add(novo_point_map)
    db.commit()
    db.refresh(novo_point_map)

    # Grava no histórico permanente de medições para preservação nos gráficos
    historico_medicao = MapMeasurementHistoryModel(
        code_map_point=novo_point_map.code_map_point,
        name_map_point=novo_point_map.name_map_point,
        ph=novo_point_map.ph_map_point,
        turbidity=novo_point_map.turbidity_map_point,
        contaminant=novo_point_map.contaminant_map_point,
        volume=novo_point_map.volume_map_point,
        risk=novo_point_map.risk_map_point,
        recorded_at=novo_point_map.datetime_map_point_creation or datetime.utcnow()
    )
    db.add(historico_medicao)
    db.commit()

    return novo_point_map

@router.put("/{id_map}", response_model=MapResposta, summary="Atualizar ponto do mapa")
def atualizar_mapa(id_map: int, dados: MapAtualizar, db: Session = Depends(get_db)):
    mapa = db.query(MapPointModel).filter(MapPointModel.id_map_point == id_map).first()
    if not mapa:
        raise HTTPException(status_code=404, detail="Ponto do mapa não encontrado.")
    
    for campo, valor in dados.dict(exclude_unset=True).items():
        setattr(mapa, campo, valor)
        
    db.commit()
    db.refresh(mapa)

    # Grava o snapshot atualizado no histórico permanente de medições
    historico_medicao = MapMeasurementHistoryModel(
        code_map_point=mapa.code_map_point,
        name_map_point=mapa.name_map_point,
        ph=mapa.ph_map_point,
        turbidity=mapa.turbidity_map_point,
        contaminant=mapa.contaminant_map_point,
        volume=mapa.volume_map_point,
        risk=mapa.risk_map_point,
        recorded_at=datetime.utcnow()
    )
    db.add(historico_medicao)
    db.commit()

    return mapa

@router.delete("/{id_map}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir ponto do mapa")
def excluir_mapa(id_map: int, db: Session = Depends(get_db)):
    mapa = db.query(MapPointModel).filter(MapPointModel.id_map_point == id_map).first()
    if not mapa:
        raise HTTPException(status_code=404, detail="Ponto do mapa não encontrado.")
        
    # A exclusão remove o ponto da visão ativa do mapa, mas o histórico permanece em Map_Measurement_History
    db.delete(mapa)
    db.commit()
    return None

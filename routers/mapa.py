from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db, MapPointModel
from schemas import MapCriar, MapAtualizar, MapResposta

router = APIRouter(tags=["Mapa"])

@router.get("/", response_model=List[MapResposta], summary="Listar todos os pontos do mapa")
def listar_mapa(db: Session = Depends(get_db)):
    return db.query(MapPointModel).order_by(MapPointModel.id_map_point.asc()).all()

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
        risk_map_point=dados.risk_map_point
    )
    
    db.add(novo_point_map)
    db.commit()
    db.refresh(novo_point_map)
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
    return mapa

@router.delete("/{id_map}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir ponto do mapa")
def excluir_mapa(id_map: int, db: Session = Depends(get_db)):
    mapa = db.query(MapPointModel).filter(MapPointModel.id_map_point == id_map).first()
    if not mapa:
        raise HTTPException(status_code=404, detail="Ponto do mapa não encontrado.")
        
    db.delete(mapa)
    db.commit()
    return None
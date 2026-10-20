from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm  import Session
from typing import List
import random

from database import get_db, AppUserModel
from schemas import UserCriar, UserAtualizar, UserResposta

router = APIRouter(tags = ["Usuários"])

@router.get("/", response_model=List[UserResposta], summary="Listar todos os usuários")
def listar_usuarios(db: Session = Depends(get_db)):
    return db.query(AppUserModel).order_by(AppUserModel.id_user.desc()).all()
    
@router.get("/{id_user}", response_model=UserResposta, summary="Buscar usuário por ID")
def buscar_usuario(id_user: int, db: Session = Depends(get_db)):
    usuario = db.query(AppUserModel).filter(AppUserModel.id_user == id_user).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return usuario

@router.post("/", response_model=UserResposta, status_code=status.HTTP_201_CREATED, summary="Criar novo usuário")
def criar_usuario(dados: UserCriar, db: Session = Depends(get_db)):
    usuario_existente = db.query(AppUserModel).filter(AppUserModel.email_user == dados.email_user).first()
    if usuario_existente:
        raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")

    novo_usuario = AppUserModel(
        name_user=dados.name_user,
        email_user=dados.email_user,
        role_user=dados.role_user,
        responsible_point_user=dados.responsible_point_user,
        status_user=dados.status_user
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario


@router.put("/{id_user}", response_model=UserResposta, summary="Atualizar usuário")
def atualizar_usuario(id_user: int, dados: UserAtualizar, db: Session = Depends(get_db)):
    usuario = db.query(AppUserModel).filter(AppUserModel.id_user == id_user).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    for campo, valor in dados.dict(exclude_unset=True).items():
        setattr(usuario, campo, valor)
        
    db.commit()
    db.refresh(usuario)
    return usuario

@router.delete("/{id_user}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir usuário")
def excluir_usuario(id_user: int, db: Session = Depends(get_db)):
    usuario = db.query(AppUserModel).filter(AppUserModel.id_user == id_user).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    db.delete(usuario)
    db.commit()
    return None
    
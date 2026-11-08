from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_tenant import TenantContext, get_current_tenant, get_current_tenant_context
from database import (
    AIDailyAnalysisModel,
    AlertModel,
    AppUserModel,
    AreaOfDisposalModel,
    EnvironmentalRegulatorModel,
    HistoryEventModel,
    MapMeasurementHistoryModel,
    MapPointModel,
    MeasurementModel,
    OccurrenceModel,
    PropertyModel,
    TenantSettingsModel,
    WaterAdmissionModel,
    WaterBatchModel,
    WaterDisposalModel,
    WaterSellerModel,
    WaterStorageModel,
    get_db,
)
from schemas import UserAtualizar, UserCriar, UserResposta
from services.incident_service import registrar_evento_historico

router = APIRouter(tags=["Usuários"])


def _actor_label(ctx: TenantContext) -> str:
    return ctx.email or f"uid:{ctx.tenant_id[:8]}"


@router.get("/", response_model=List[UserResposta], summary="Listar todos os usuários cadastrados na conta")
def listar_usuarios(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(AppUserModel)
        .filter(AppUserModel.tenant_id == tenant_id)
        .order_by(AppUserModel.id_user.desc())
        .all()
    )


@router.post("/", response_model=UserResposta, status_code=status.HTTP_201_CREATED, summary="Criar novo usuário")
def criar_usuario(
    dados: UserCriar,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    usuario_existente = (
        db.query(AppUserModel.id_user)
        .filter(
            AppUserModel.tenant_id == tenant_id,
            AppUserModel.email_user == dados.email_user,
        )
        .first()
    )
    if usuario_existente:
        raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")

    novo_usuario = AppUserModel(
        tenant_id=tenant_id,
        name_user=dados.name_user,
        email_user=dados.email_user,
        role_user=dados.role_user,
        responsible_point_user=dados.responsible_point_user,
        status_user=dados.status_user,
    )
    db.add(novo_usuario)
    db.flush()

    registrar_evento_historico(
        db=db,
        tenant_id=tenant_id,
        event_type="providencia",
        event_label="Auditoria LGPD — Criação de Usuário",
        event_point=dados.responsible_point_user,
        event_description=(
            f"Cadastro de colaborador ID #{novo_usuario.id_user} (perfil: {novo_usuario.role_user}) "
            f"realizado por {_actor_label(ctx)}."
        ),
        event_severity="normal",
        id_reference=novo_usuario.id_user,
        reference_type="app_user",
        created_by=_actor_label(ctx),
    )

    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario


@router.put("/{id_user}", response_model=UserResposta, summary="Atualizar usuário")
def atualizar_usuario(
    id_user: int,
    dados: UserAtualizar,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    usuario = (
        db.query(AppUserModel)
        .filter(
            AppUserModel.id_user == id_user,
            AppUserModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    campos_atualizacao = dados.model_dump(exclude_unset=True)
    novo_email = campos_atualizacao.get("email_user")
    if novo_email and novo_email != usuario.email_user:
        conflito_email = (
            db.query(AppUserModel.id_user)
            .filter(
                AppUserModel.tenant_id == tenant_id,
                AppUserModel.email_user == novo_email,
            )
            .first()
        )
        if conflito_email:
            raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")

    for campo, valor in campos_atualizacao.items():
        setattr(usuario, campo, valor)

    registrar_evento_historico(
        db=db,
        tenant_id=tenant_id,
        event_type="providencia",
        event_label="Auditoria LGPD — Atualização de Usuário",
        event_point=usuario.responsible_point_user,
        event_description=(
            f"Dados/permissões do usuário ID #{usuario.id_user} (perfil: {usuario.role_user}, "
            f"status: {usuario.status_user}) atualizados por {_actor_label(ctx)}."
        ),
        event_severity="normal",
        id_reference=usuario.id_user,
        reference_type="app_user",
        created_by=_actor_label(ctx),
    )

    db.commit()
    db.refresh(usuario)
    return usuario


@router.delete("/{id_user}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir usuário e anonimizar referências (LGPD)")
def excluir_usuario(
    id_user: int,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    usuario = (
        db.query(AppUserModel)
        .filter(
            AppUserModel.id_user == id_user,
            AppUserModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    anon_label = f"Colaborador Anonimizado #{id_user}"
    for pii_value in filter(None, [usuario.name_user, usuario.email_user]):
        db.query(OccurrenceModel).filter(
            OccurrenceModel.tenant_id == tenant_id,
            OccurrenceModel.responsible_occurrence == pii_value,
        ).update({"responsible_occurrence": anon_label}, synchronize_session=False)

        db.query(AlertModel).filter(
            AlertModel.tenant_id == tenant_id,
            AlertModel.responsible == pii_value,
        ).update({"responsible": anon_label}, synchronize_session=False)

        db.query(HistoryEventModel).filter(
            HistoryEventModel.tenant_id == tenant_id,
            HistoryEventModel.created_by == pii_value,
        ).update({"created_by": anon_label}, synchronize_session=False)

    registrar_evento_historico(
        db=db,
        tenant_id=tenant_id,
        event_type="providencia",
        event_label="Auditoria LGPD — Exclusão e Anonimização",
        event_point=usuario.responsible_point_user or "Geral",
        event_description=(
            f"Cadastro do colaborador ID #{id_user} excluído e referências históricas anonimizadas "
            f"por {_actor_label(ctx)} (LGPD Art. 18, VI)."
        ),
        event_severity="normal",
        id_reference=id_user,
        reference_type="app_user",
        created_by=_actor_label(ctx),
    )

    db.delete(usuario)
    db.commit()
    return None


@router.get("/me/export-data", summary="Exportar dados do titular (Portabilidade LGPD Art. 18, V)")
def exportar_dados_titular(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    usuarios = db.query(AppUserModel).filter(AppUserModel.tenant_id == tenant_id).all()
    preferencias = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
    ocorrencias = db.query(OccurrenceModel).filter(OccurrenceModel.tenant_id == tenant_id).all()
    pontos = db.query(MapPointModel).filter(MapPointModel.tenant_id == tenant_id).all()

    return {
        "lgpd_right": "Art. 18, II e V — Acesso e Portabilidade de Dados",
        "account": {
            "tenant_id": tenant_id,
            "email": ctx.email,
            "email_verified": ctx.email_verified,
        },
        "preferences": {
            "unit_select": preferencias.unit_select if preferencias else None,
            "frequency_minutes": preferencias.frequency_minutes if preferencias else None,
            "timezone": preferencias.timezone if preferencias else None,
            "email_alerts": bool(preferencias.email_alerts) if preferencias else False,
            "push_alerts": bool(preferencias.push_alerts) if preferencias else False,
            "user_email": preferencias.user_email if preferencias else ctx.email,
        },
        "team_users": [
            {
                "id_user": u.id_user,
                "name_user": u.name_user,
                "email_user": u.email_user,
                "role_user": u.role_user,
                "responsible_point_user": u.responsible_point_user,
                "status_user": u.status_user,
            }
            for u in usuarios
        ],
        "monitoring_points_count": len(pontos),
        "occurrences_count": len(ocorrencias),
    }


@router.delete("/me/account", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir conta e todos os dados do titular (LGPD Art. 18, VI)")
def excluir_conta_titular(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    models_to_purge = [
        WaterAdmissionModel,
        WaterStorageModel,
        WaterDisposalModel,
        AreaOfDisposalModel,
        WaterBatchModel,
        MeasurementModel,
        EnvironmentalRegulatorModel,
        PropertyModel,
        WaterSellerModel,
        AlertModel,
        OccurrenceModel,
        MapMeasurementHistoryModel,
        MapPointModel,
        AIDailyAnalysisModel,
        HistoryEventModel,
        AppUserModel,
        TenantSettingsModel,
    ]
    for model_cls in models_to_purge:
        db.query(model_cls).filter(model_cls.tenant_id == tenant_id).delete(synchronize_session=False)

    db.commit()
    return None

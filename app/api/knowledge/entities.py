from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from app.database.session import get_db
from app.models.knowledge.entity import Entity, EntityAlias, EntityAttribute
from app.models.tenancy import User
from app.auth.dependencies import get_current_user
from app.schemas.entity import (
    EntityCreate,
    EntityListItem,
    EntityListResponse,
    EntityRead,
    EntityRelationRead,
    EntityUpdate,
)

router = APIRouter(prefix="/entities", tags=["Entities"])


def _ensure_tenant(current_user: User, tenant_id: UUID) -> None:
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")


def _query_entities(db: Session, current_user: User):
    return (
        db.query(Entity)
        .options(
            selectinload(Entity.aliases),
            selectinload(Entity.attributes),
            selectinload(Entity.outgoing_relations),
        )
        .filter(Entity.tenant_id == current_user.tenant_id)
    )


def _get_entity_or_404(db: Session, current_user: User, entity_id: UUID) -> Entity:
    entity = _query_entities(db, current_user).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


def _aliases(entity: Entity) -> list[str]:
    return [alias.alias for alias in sorted(entity.aliases or [], key=lambda item: item.alias.lower())]


def _attributes(entity: Entity) -> dict[str, Any]:
    return {attribute.key: attribute.value for attribute in entity.attributes or []}


def _list_item(entity: Entity) -> EntityListItem:
    return EntityListItem(id=entity.id, name=entity.name, type=entity.entity_type, aliases=_aliases(entity))


def _read_entity(entity: Entity) -> EntityRead:
    return EntityRead(
        id=entity.id,
        name=entity.name,
        type=entity.entity_type,
        aliases=_aliases(entity),
        attributes=_attributes(entity),
        relations=[
            EntityRelationRead(to_entity_id=relation.target_entity_id, relation=relation.relation_type)
            for relation in entity.outgoing_relations or []
        ],
        tenant_id=entity.tenant_id,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _replace_aliases(db: Session, entity: Entity, aliases: list[str]) -> None:
    unique_aliases = list(dict.fromkeys(alias.strip() for alias in aliases if alias.strip()))
    db.query(EntityAlias).filter(EntityAlias.entity_id == entity.id).delete(synchronize_session=False)
    db.flush()
    for alias in unique_aliases:
        db.add(EntityAlias(tenant_id=entity.tenant_id, entity_id=entity.id, alias=alias))


def _replace_attributes(db: Session, entity: Entity, attributes: dict[str, Any]) -> None:
    db.query(EntityAttribute).filter(EntityAttribute.entity_id == entity.id).delete(synchronize_session=False)
    db.flush()
    for key, value in attributes.items():
        db.add(EntityAttribute(tenant_id=entity.tenant_id, entity_id=entity.id, key=key, value=value))


@router.post("", response_model=EntityRead, status_code=status.HTTP_201_CREATED)
def create_entity(
    payload: EntityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EntityRead:
    _ensure_tenant(current_user, payload.tenant_id)
    existing = (
        db.query(Entity)
        .filter(Entity.tenant_id == current_user.tenant_id, Entity.entity_type == payload.type, Entity.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Entity already exists")

    entity = Entity(tenant_id=current_user.tenant_id, name=payload.name, entity_type=payload.type, metadata_={})
    db.add(entity)
    db.flush()
    _replace_aliases(db, entity, payload.aliases)
    _replace_attributes(db, entity, payload.attributes)
    db.commit()
    db.refresh(entity)
    entity = _get_entity_or_404(db, current_user, entity.id)
    return _read_entity(entity)


@router.get("", response_model=EntityListResponse)
def list_entities(
    tenant_id: Optional[UUID] = None,
    entity_type: Optional[str] = Query(default=None, alias="type"),
    page: int = 1,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EntityListResponse:
    if tenant_id is not None:
        _ensure_tenant(current_user, tenant_id)

    page = max(page, 1)
    query = _query_entities(db, current_user)
    if entity_type:
        query = query.filter(Entity.entity_type == entity_type)

    entities = query.order_by(Entity.created_at.desc()).offset((page - 1) * 20).limit(20).all()
    return EntityListResponse(items=[_list_item(entity) for entity in entities])


@router.get("/{entity_id}", response_model=EntityRead)
def get_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EntityRead:
    return _read_entity(_get_entity_or_404(db, current_user, entity_id))


@router.patch("/{entity_id}", response_model=EntityRead)
def update_entity(
    entity_id: UUID,
    payload: EntityUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EntityRead:
    entity = _get_entity_or_404(db, current_user, entity_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data:
        entity.name = update_data["name"]
    if "type" in update_data:
        entity.entity_type = update_data["type"]
    if "aliases" in update_data:
        _replace_aliases(db, entity, update_data["aliases"] or [])
    if "attributes" in update_data:
        _replace_attributes(db, entity, update_data["attributes"] or {})

    db.commit()
    db.refresh(entity)
    return _read_entity(_get_entity_or_404(db, current_user, entity.id))


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    entity = _get_entity_or_404(db, current_user, entity_id)
    db.delete(entity)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

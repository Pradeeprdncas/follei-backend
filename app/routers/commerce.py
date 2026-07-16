from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.domain import Competitor, CompetitorFeature, PricingModel, PricingRule, Product, Service
from app.models.tenancy import User
from app.routers.auth import get_current_user

products_router = APIRouter(prefix="/products", tags=["Products & Pricing"])
services_router = APIRouter(prefix="/services", tags=["Products & Pricing"])
pricing_router = APIRouter(prefix="/pricing-models", tags=["Products & Pricing"])
competitors_router = APIRouter(prefix="/competitors", tags=["Products & Pricing"])


class ProductIn(BaseModel):
    name: str
    description: Optional[str] = None
    tenant_id: UUID
    status: str = "active"
    features: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    features: Optional[list[dict[str, Any]]] = None
    metadata: Optional[dict[str, Any]] = None


class ServiceIn(BaseModel):
    name: str
    description: Optional[str] = None
    tenant_id: UUID
    pricing_type: Optional[str] = None
    base_price: Optional[float] = None


class PricingModelIn(BaseModel):
    product_id: Optional[UUID] = None
    name: str
    billing_period: str
    currency: str = "USD"
    base_price: float = 0
    tiers: list[dict[str, Any]] = Field(default_factory=list)
    addons: list[dict[str, Any]] = Field(default_factory=list)


class PricingRuleIn(BaseModel):
    name: str
    condition: str
    discount_percent: Optional[float] = None
    active: bool = True


class CompetitorIn(BaseModel):
    name: str
    website: Optional[str] = None
    tenant_id: UUID
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class CompetitorFeatureIn(BaseModel):
    feature_name: str
    our_status: str
    competitor_status: str
    notes: Optional[str] = None


def _ensure_tenant(user: User, tenant_id: UUID) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")


def _product_payload(product: Product, detail: bool = False) -> dict[str, Any]:
    metadata = product.metadata_ or {}
    data = {"id": product.id, "name": product.name, "description": product.description, "status": "active" if product.is_active else "inactive", "features": metadata.get("features", [])}
    if detail:
        data["pricing_models"] = metadata.get("pricing_models", [])
        data["created_at"] = product.created_at
        data["metadata"] = {key: value for key, value in metadata.items() if key != "features"}
    return data


@products_router.post("", status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    metadata = dict(payload.metadata)
    metadata["features"] = payload.features
    product = Product(tenant_id=user.tenant_id, name=payload.name, description=payload.description, is_active=payload.status == "active", metadata_=metadata)
    db.add(product)
    db.commit()
    db.refresh(product)
    return _product_payload(product, detail=True)


@products_router.get("")
def list_products(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Product).filter(Product.tenant_id == user.tenant_id).order_by(Product.created_at.desc()).all()
    return {"items": [_product_payload(item) for item in items]}


@products_router.get("/{product_id}")
def get_product(product_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.tenant_id == user.tenant_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    pricing = db.query(PricingModel).filter(PricingModel.tenant_id == user.tenant_id, PricingModel.metadata_["product_id"].as_string() == str(product.id)).all()
    data = _product_payload(product, detail=True)
    data["pricing_models"] = [{"id": item.id, "name": item.name, "price": (item.metadata_ or {}).get("base_price")} for item in pricing]
    return data


@products_router.patch("/{product_id}")
def update_product(product_id: UUID, payload: ProductUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.tenant_id == user.tenant_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        product.name = data["name"]
    if "description" in data:
        product.description = data["description"]
    if "status" in data:
        product.is_active = data["status"] == "active"
    metadata = dict(product.metadata_ or {})
    if "metadata" in data:
        metadata.update(data["metadata"] or {})
    if "features" in data:
        metadata["features"] = data["features"] or []
    product.metadata_ = metadata
    db.commit()
    db.refresh(product)
    return _product_payload(product, detail=True)


@products_router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.tenant_id == user.tenant_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@services_router.post("", status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    service = Service(tenant_id=user.tenant_id, name=payload.name, description=payload.description, metadata_={"pricing_type": payload.pricing_type, "base_price": payload.base_price})
    db.add(service)
    db.commit()
    db.refresh(service)
    return {"id": service.id, "name": service.name, "description": service.description, "pricing_type": service.metadata_.get("pricing_type"), "base_price": service.metadata_.get("base_price")}


@services_router.get("")
def list_services(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Service).filter(Service.tenant_id == user.tenant_id).order_by(Service.created_at.desc()).all()
    return {"items": [{"id": item.id, "name": item.name, "base_price": (item.metadata_ or {}).get("base_price")} for item in items]}


@pricing_router.post("", status_code=status.HTTP_201_CREATED)
def create_pricing_model(payload: PricingModelIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    model = PricingModel(tenant_id=user.tenant_id, name=payload.name, model_type=payload.billing_period, tiers=payload.tiers, metadata_={"product_id": str(payload.product_id) if payload.product_id else None, "currency": payload.currency, "base_price": payload.base_price, "addons": payload.addons})
    db.add(model)
    db.commit()
    db.refresh(model)
    return {"id": model.id, "name": model.name, "billing_period": model.model_type, "currency": model.metadata_.get("currency"), "base_price": model.metadata_.get("base_price"), "tiers": model.tiers, "addons": model.metadata_.get("addons", [])}


@pricing_router.get("")
def list_pricing_models(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(PricingModel).filter(PricingModel.tenant_id == user.tenant_id).order_by(PricingModel.created_at.desc()).all()
    return {"items": [{"id": item.id, "name": item.name, "base_price": (item.metadata_ or {}).get("base_price"), "tiers": item.tiers} for item in items]}


@pricing_router.post("/{model_id}/rules", status_code=status.HTTP_201_CREATED)
def add_pricing_rule(model_id: UUID, payload: PricingRuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    model = db.query(PricingModel).filter(PricingModel.id == model_id, PricingModel.tenant_id == user.tenant_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Pricing model not found")
    rule = PricingRule(tenant_id=user.tenant_id, pricing_model_id=model.id, name=payload.name, conditions={"expression": payload.condition}, actions={"discount_percent": payload.discount_percent}, is_active=payload.active)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"id": rule.id, "name": rule.name, "condition": rule.conditions.get("expression"), "discount_percent": rule.actions.get("discount_percent"), "active": rule.is_active}


@competitors_router.post("", status_code=status.HTTP_201_CREATED)
def create_competitor(payload: CompetitorIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    competitor = Competitor(tenant_id=user.tenant_id, name=payload.name, website=payload.website, metadata_={"strengths": payload.strengths, "weaknesses": payload.weaknesses})
    db.add(competitor)
    db.commit()
    db.refresh(competitor)
    return {"id": competitor.id, "name": competitor.name, "website": competitor.website, "strengths": competitor.metadata_.get("strengths", []), "weaknesses": competitor.metadata_.get("weaknesses", [])}


@competitors_router.get("")
def list_competitors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Competitor).filter(Competitor.tenant_id == user.tenant_id).order_by(Competitor.created_at.desc()).all()
    return {"items": [{"id": item.id, "name": item.name, "strengths": (item.metadata_ or {}).get("strengths", []), "weaknesses": (item.metadata_ or {}).get("weaknesses", [])} for item in items]}


@competitors_router.post("/{competitor_id}/features", status_code=status.HTTP_201_CREATED)
def add_competitor_feature(competitor_id: UUID, payload: CompetitorFeatureIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    competitor = db.query(Competitor).filter(Competitor.id == competitor_id, Competitor.tenant_id == user.tenant_id).first()
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    feature = CompetitorFeature(tenant_id=user.tenant_id, competitor_id=competitor.id, feature_name=payload.feature_name, comparison=payload.notes, metadata_={"our_status": payload.our_status, "competitor_status": payload.competitor_status})
    db.add(feature)
    db.commit()
    db.refresh(feature)
    return {"id": feature.id, "feature_name": feature.feature_name, "our_status": feature.metadata_.get("our_status"), "competitor_status": feature.metadata_.get("competitor_status"), "notes": feature.comparison}

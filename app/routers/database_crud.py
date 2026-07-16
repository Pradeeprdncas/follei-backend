from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import Boolean, Date, DateTime, Integer, Numeric, String, Text

from app.database.session import engine, get_db


router = APIRouter(prefix="/database", tags=["Database CRUD"])


class RecordPayload(BaseModel):
    data: dict[str, Any] = Field(
        ...,
        examples=[
            {
                "tenant_id": "00000000-0000-0000-0000-000000000000",
                "name": "Example",
                "metadata": {},
            }
        ],
    )


def _table_names() -> set[str]:
    return set(inspect(engine).get_table_names(schema="public"))


def _get_table(table_name: str) -> Table:
    if table_name not in _table_names():
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    metadata = MetaData()
    return Table(table_name, metadata, autoload_with=engine)


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def _serialize_row(row: Any) -> dict[str, Any]:
    return {key: _serialize(value) for key, value in row._mapping.items()}


def _coerce_value(value: Any, column: Any) -> Any:
    if value is None:
        return None

    column_type = column.type
    if isinstance(column_type, String | Text):
        return str(value)
    if isinstance(column_type, Integer):
        return int(value)
    if isinstance(column_type, Numeric):
        return Decimal(str(value))
    if isinstance(column_type, Boolean):
        return bool(value)
    if isinstance(column_type, DateTime):
        return datetime.fromisoformat(value) if isinstance(value, str) else value
    if isinstance(column_type, Date):
        return date.fromisoformat(value) if isinstance(value, str) else value
    if isinstance(column_type, ARRAY):
        return value

    if column_type.__class__.__name__ == "UUID":
        return UUID(value) if isinstance(value, str) else value

    return value


def _clean_payload(table: Table, payload: dict[str, Any]) -> dict[str, Any]:
    columns = {column.name: column for column in table.columns}
    invalid = sorted(set(payload) - set(columns))
    if invalid:
        raise HTTPException(status_code=400, detail={"invalid_columns": invalid})

    return {
        key: _coerce_value(value, columns[key])
        for key, value in payload.items()
        if key in columns
    }


def _id_column(table: Table) -> Any:
    if "id" not in table.c:
        raise HTTPException(
            status_code=400,
            detail=f"Table '{table.name}' does not have a single 'id' column endpoint",
        )
    return table.c.id


@router.get("/tables")
def list_tables() -> dict[str, Any]:
    tables = sorted(_table_names())
    return {"count": len(tables), "tables": tables}


@router.get("/{table_name}/schema")
def get_table_schema(table_name: str) -> dict[str, Any]:
    table = _get_table(table_name)
    columns = [
        {
            "name": column.name,
            "type": str(column.type),
            "nullable": column.nullable,
            "primary_key": column.primary_key,
            "default": str(column.default.arg) if column.default is not None else None,
        }
        for column in table.columns
    ]
    return {"table": table_name, "columns": columns}


@router.get("/{table_name}/records")
def list_records(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    table = _get_table(table_name)
    rows = db.execute(select(table).limit(limit).offset(offset)).all()
    return {
        "table": table_name,
        "limit": limit,
        "offset": offset,
        "records": [_serialize_row(row) for row in rows],
    }


@router.post("/{table_name}/records", status_code=status.HTTP_201_CREATED)
def create_record(
    table_name: str,
    payload: RecordPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    table = _get_table(table_name)
    values = _clean_payload(table, payload.data)
    result = db.execute(table.insert().values(**values).returning(table))
    db.commit()
    return {"table": table_name, "record": _serialize_row(result.one())}


@router.get("/{table_name}/records/{record_id}")
def get_record(
    table_name: str,
    record_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    table = _get_table(table_name)
    row = db.execute(select(table).where(_id_column(table) == record_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"table": table_name, "record": _serialize_row(row)}


@router.patch("/{table_name}/records/{record_id}")
def update_record(
    table_name: str,
    record_id: UUID,
    payload: RecordPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    table = _get_table(table_name)
    values = _clean_payload(table, payload.data)
    if not values:
        raise HTTPException(status_code=400, detail="No values provided")

    result = db.execute(
        table.update()
        .where(_id_column(table) == record_id)
        .values(**values)
        .returning(table)
    ).first()
    if result is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Record not found")

    db.commit()
    return {"table": table_name, "record": _serialize_row(result)}


@router.delete("/{table_name}/records/{record_id}")
def delete_record(
    table_name: str,
    record_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    table = _get_table(table_name)
    result = db.execute(
        table.delete()
        .where(_id_column(table) == record_id)
        .returning(_id_column(table))
    ).first()
    if result is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Record not found")

    db.commit()
    return {"table": table_name, "deleted_id": str(result[0])}

"""Platform service — generic database CRUD (admin use only)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import MetaData, Table, inspect, select, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import Boolean, Date, DateTime, Integer, Numeric, String, Text

from app.database.session import engine


class PlatformService:
    def __init__(self, db: Session):
        self.db = db

    def _table_names(self) -> set[str]:
        return set(inspect(engine).get_table_names(schema="public"))

    def _get_table(self, table_name: str):
        from fastapi import HTTPException
        if table_name not in self._table_names():
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        metadata = MetaData()
        return Table(table_name, metadata, autoload_with=engine)

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UUID):
            return str(value)
        return value

    def _serialize_row(self, row: Any) -> dict[str, Any]:
        return {key: self._serialize(value) for key, value in row._mapping.items()}

    def _coerce_value(self, value: Any, column: Any) -> Any:
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

    def _clean_payload(self, table: Table, payload: dict[str, Any]) -> dict[str, Any]:
        from fastapi import HTTPException
        columns = {column.name: column for column in table.columns}
        invalid = sorted(set(payload) - set(columns))
        if invalid:
            raise HTTPException(status_code=400, detail={"invalid_columns": invalid})
        return {key: self._coerce_value(value, columns[key]) for key, value in payload.items() if key in columns}

    def _id_column(self, table: Table):
        from fastapi import HTTPException
        if "id" not in table.c:
            raise HTTPException(status_code=400, detail=f"Table '{table.name}' does not have an 'id' column")
        return table.c.id

    def list_tables(self) -> dict:
        tables = sorted(self._table_names())
        return {"count": len(tables), "tables": tables}

    def get_table_schema(self, table_name: str) -> dict:
        table = self._get_table(table_name)
        columns = [
            {
                "name": column.name, "type": str(column.type),
                "nullable": column.nullable, "primary_key": column.primary_key,
                "default": str(column.default.arg) if column.default is not None else None,
            }
            for column in table.columns
        ]
        return {"table": table_name, "columns": columns}

    def list_records(self, table_name: str, limit: int = 50, offset: int = 0) -> dict:
        table = self._get_table(table_name)
        rows = self.db.execute(select(table).limit(limit).offset(offset)).all()
        return {
            "table": table_name, "limit": limit, "offset": offset,
            "records": [self._serialize_row(row) for row in rows],
        }

    def create_record(self, table_name: str, data: dict) -> dict:
        table = self._get_table(table_name)
        values = self._clean_payload(table, data)
        result = self.db.execute(table.insert().values(**values).returning(table))
        self.db.commit()
        return {"table": table_name, "record": self._serialize_row(result.one())}

    def get_record(self, table_name: str, record_id: UUID) -> dict:
        from fastapi import HTTPException
        table = self._get_table(table_name)
        row = self.db.execute(select(table).where(self._id_column(table) == record_id)).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Record not found")
        return {"table": table_name, "record": self._serialize_row(row)}

    def update_record(self, table_name: str, record_id: UUID, data: dict) -> dict:
        from fastapi import HTTPException
        table = self._get_table(table_name)
        values = self._clean_payload(table, data)
        if not values:
            raise HTTPException(status_code=400, detail="No values provided")
        result = self.db.execute(
            table.update().where(self._id_column(table) == record_id).values(**values).returning(table)
        ).first()
        if result is None:
            self.db.rollback()
            raise HTTPException(status_code=404, detail="Record not found")
        self.db.commit()
        return {"table": table_name, "record": self._serialize_row(result)}

    def delete_record(self, table_name: str, record_id: UUID) -> dict:
        from fastapi import HTTPException
        table = self._get_table(table_name)
        result = self.db.execute(
            table.delete().where(self._id_column(table) == record_id).returning(self._id_column(table))
        ).first()
        if result is None:
            self.db.rollback()
            raise HTTPException(status_code=404, detail="Record not found")
        self.db.commit()
        return {"table": table_name, "deleted_id": str(result[0])}

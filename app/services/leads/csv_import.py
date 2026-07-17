"""CSV Import Service - Import leads from CSV/XLSX files."""
from typing import Dict, Any, List, Optional
from pathlib import Path
from loguru import logger
import csv
import io
from datetime import datetime

from app.database.session import get_db
from app.models.leads.lead import Lead
from app.models.campaigns import LeadScore


class CSVImportService:
    """Service for importing leads from CSV/XLSX files.
    
    Features:
    - Auto-detect columns
    - Map columns to lead fields
    - Duplicate detection
    - Email/phone validation
    - Import reporting
    """
    
    # Column mapping patterns
    COLUMN_PATTERNS = {
        "email": ["email", "e-mail", "mail", "email address"],
        "full_name": ["name", "full name", "fullname", "contact name", "contact"],
        "first_name": ["first name", "firstname", "fname", "given name"],
        "last_name": ["last name", "lastname", "lname", "surname", "family name"],
        "phone": ["phone", "mobile", "contact", "telephone", "cell", "phone number"],
        "company": ["company", "organization", "org", "business", "firm"],
        "source": ["source", "lead source", "origin", "channel"],
        "status": ["status", "lead status"],
        "priority": ["priority"],
    }
    
    def __init__(self):
        """Initialize CSV import service."""
        self.import_report = {
            "total_rows": 0,
            "imported": 0,
            "duplicates": 0,
            "failed": 0,
            "errors": [],
        }
    
    async def import_csv(
        self,
        file_content: bytes,
        tenant_id: str,
        column_mapping: Optional[Dict[str, str]] = None,
        default_source: str = "csv_import",
    ) -> Dict[str, Any]:
        """Import leads from CSV file.
        
        Args:
            file_content: CSV file content as bytes
            tenant_id: Tenant UUID
            column_mapping: Optional custom column mapping
            default_source: Default source for imported leads
            
        Returns:
            Import report
        """
        self.import_report = {
            "total_rows": 0,
            "imported": 0,
            "duplicates": 0,
            "failed": 0,
            "errors": [],
        }
        
        try:
            # Parse CSV
            content = file_content.decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            
            # Auto-detect columns if no mapping provided
            if not column_mapping:
                column_mapping = self._detect_columns(reader.fieldnames or [])
            
            # Process rows
            db = next(get_db())
            
            try:
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                    self.import_report["total_rows"] += 1
                    
                    # Map columns
                    lead_data = self._map_row(row, column_mapping, tenant_id, default_source)
                    
                    # Validate
                    if not lead_data.get("email") and not lead_data.get("phone"):
                        self.import_report["failed"] += 1
                        self.import_report["errors"].append({
                            "row": row_num,
                            "error": "No email or phone provided",
                        })
                        continue
                    
                    # Check for duplicates
                    if await self._is_duplicate(db, tenant_id, lead_data):
                        self.import_report["duplicates"] += 1
                        continue
                    
                    # Create lead
                    lead = Lead(**lead_data)
                    db.add(lead)
                    db.flush()  # Flush to get ID
                    
                    # Create initial score
                    score = LeadScore(
                        lead_id=lead.id,
                        tenant_id=tenant_id,
                        score=0,
                        previous_score=0,
                        score_delta=0,
                        event_type="import",
                        event_metadata={"source": default_source},
                    )
                    db.add(score)
                    
                    self.import_report["imported"] += 1
                
                db.commit()
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error during CSV import: {e}")
                self.import_report["errors"].append({
                    "row": 0,
                    "error": f"Database error: {str(e)}",
                })
            finally:
                db.close()
            
            logger.info(
                f"CSV import complete: {self.import_report['imported']} imported, "
                f"{self.import_report['duplicates']} duplicates, "
                f"{self.import_report['failed']} failed"
            )
            
            return self.import_report
            
        except Exception as e:
            logger.error(f"CSV import failed: {e}")
            self.import_report["errors"].append({
                "row": 0,
                "error": f"File parsing failed: {str(e)}",
            })
            return self.import_report
    
    def _detect_columns(self, headers: List[str]) -> Dict[str, str]:
        """Auto-detect column mapping from headers.
        
        Args:
            headers: CSV column headers
            
        Returns:
            Column mapping
        """
        column_mapping = {}
        headers_lower = [h.lower().strip() for h in headers]
        
        for field, patterns in self.COLUMN_PATTERNS.items():
            for pattern in patterns:
                if pattern in headers_lower:
                    idx = headers_lower.index(pattern)
                    column_mapping[field] = headers[idx]
                    break
        
        return column_mapping
    
    # Valid Lead model columns from Lead SQLAlchemy model
    LEAD_MODEL_FIELDS = {
        "id", "tenant_id", "email", "first_name", "last_name", 
        "company", "status", "revenue_score", "phone", "created_at"
    }

    def _map_row(
        self,
        row: Dict[str, str],
        column_mapping: Dict[str, str],
        tenant_id: str,
        default_source: str,
    ) -> Dict[str, Any]:
        """Map CSV row to lead data. Strips unknown columns.
        
        Args:
            row: CSV row
            column_mapping: Column mapping
            tenant_id: Tenant UUID
            default_source: Default source
            
        Returns:
            Lead data dictionary (only valid Lead columns)
        """
        from uuid import uuid4
        
        lead_data: dict[str, Any] = {
            "id": uuid4(),
            "tenant_id": tenant_id,
            "status": "new",
        }
        
        # Map fields - strip columns not in Lead model
        for field, column in column_mapping.items():
            value = row.get(column, "").strip()
            
            if field == "full_name" and value:
                parts = value.split(" ", 1)
                if len(parts) == 2:
                    lead_data["first_name"] = parts[0]
                    lead_data["last_name"] = parts[1]
                else:
                    lead_data["first_name"] = parts[0]
                    lead_data["last_name"] = ""
            elif field == "email" and value:
                lead_data["email"] = value.lower()
            elif field == "phone" and value:
                lead_data["phone"] = self._clean_phone(value)
            elif field in self.LEAD_MODEL_FIELDS and value:
                lead_data[field] = value
        
        return lead_data
    
    def _clean_phone(self, phone: str) -> str:
        """Clean and format phone number.
        
        Args:
            phone: Raw phone number
            
        Returns:
            Cleaned phone number
        """
        # Remove all non-digit characters except +
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        
        # Ensure it starts with + for international format
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        
        return cleaned
    
    async def _is_duplicate(self, db: Session, tenant_id: str, lead_data: Dict) -> bool:
        """Check if lead already exists.
        
        Args:
            db: Database session
            tenant_id: Tenant UUID
            lead_data: Lead data
            
        Returns:
            True if duplicate
        """
        from sqlalchemy import select
        
        # Check by email
        if lead_data.get("email"):
            stmt = select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.email == lead_data["email"],
            )
            if db.execute(stmt).scalar_one_or_none():
                return True
        
        # Check by phone
        if lead_data.get("phone"):
            stmt = select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.phone == lead_data["phone"],
            )
            if db.execute(stmt).scalar_one_or_none():
                return True
        
        return False
    
    def get_import_report(self) -> Dict[str, Any]:
        """Get last import report.
        
        Returns:
            Import report
        """
        return self.import_report
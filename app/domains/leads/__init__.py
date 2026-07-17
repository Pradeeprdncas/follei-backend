"""Leads domain — prospect management, scoring, temperature tracking."""
from app.models.leads.lead import Lead, LeadTemperature
from app.domains.leads.events import *

__all__ = ["Lead", "LeadTemperature"]

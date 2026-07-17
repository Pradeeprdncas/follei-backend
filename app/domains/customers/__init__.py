"""Customers domain — converted accounts, health tracking, churn analysis."""
from app.models.customers.customer import Customer
from app.domains.customers.events import *

__all__ = ["Customer"]

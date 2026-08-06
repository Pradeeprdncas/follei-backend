"""
Salesforce SObject API v57.0 Endpoints.
Uses Salesforce SObject paths and the SOQL query endpoint.
"""
QUERY = "/services/data/v57.0/query"
CONTACTS = "/services/data/v57.0/sobjects/Contact"
CONTACT_DETAIL = "/services/data/v57.0/sobjects/Contact/{contact_id}"

COMPANIES = "/services/data/v57.0/sobjects/Account"
COMPANY_DETAIL = "/services/data/v57.0/sobjects/Account/{company_id}"

DEALS = "/services/data/v57.0/sobjects/Opportunity"
DEAL_DETAIL = "/services/data/v57.0/sobjects/Opportunity/{deal_id}"

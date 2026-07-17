"""ERP tool parameter validation schemas."""

CREATE_CUSTOMER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "The name of the customer"},
        "email": {"type": "string", "description": "Optional email address"},
        "account_number": {"type": "string", "description": "Optional customer account number override"},
    },
    "required": ["name"],
}

UPDATE_CUSTOMER_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_id": {"type": "string", "description": "The ERP identifier of the customer"},
        "customer_data": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Updated name"},
                "email": {"type": "string", "description": "Updated email"},
            }
        }
    },
    "required": ["customer_id", "customer_data"],
}

SEARCH_CUSTOMER_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Customer search term (e.g. name query)"}
    },
    "required": ["query"],
}

CREATE_INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_id": {"type": "string", "description": "Customer account/partner ID"},
        "amount": {"type": "number", "description": "The invoice billing amount"},
        "invoice_number": {"type": "string", "description": "Optional custom invoice number reference"},
    },
    "required": ["customer_id", "amount"],
}

GET_INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_id": {"type": "string", "description": "The ERP invoice reference identifier"}
    },
    "required": ["invoice_id"],
}

CREATE_PURCHASE_ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_id": {"type": "string", "description": "The supplier/vendor ID"},
        "item_id": {"type": "string", "description": "The product/material code"},
        "quantity": {"type": "number", "description": "Order quantity count"},
        "po_number": {"type": "string", "description": "Optional custom purchase order number override"},
    },
    "required": ["vendor_id", "item_id", "quantity"],
}

GET_INVENTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string", "description": "The product or material code ID"}
    },
    "required": ["item_id"],
}

UPDATE_INVENTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string", "description": "The product or material code ID"},
        "quantity": {"type": "number", "description": "The new stock balance quantity level"},
    },
    "required": ["item_id", "quantity"],
}

CREATE_VENDOR_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "The supplier/vendor company name"},
        "vendor_number": {"type": "string", "description": "Optional custom vendor account number override"},
    },
    "required": ["name"],
}

CREATE_SALES_ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_id": {"type": "string", "description": "Ordering customer account ID"},
        "item_id": {"type": "string", "description": "Material or product ID code"},
        "quantity": {"type": "number", "description": "Sales quantity unit count"},
        "order_number": {"type": "string", "description": "Optional sales order number reference"},
    },
    "required": ["customer_id", "item_id", "quantity"],
}

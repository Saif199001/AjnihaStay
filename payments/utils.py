import uuid

def generate_invoice_number():
    return "INV-" + uuid.uuid4().hex[:8].upper()
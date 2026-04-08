from .models import Tenant, Occupancy, Charge


# 🔥 CREATE TENANT (ALL FIELDS SUPPORT)
def create_tenant(user, data, files):

    tenant = Tenant.objects.create(
        owner=user,
        full_name=data.get("full_name"),
        phone=data.get("phone"),
        email=data.get("email"),
        profile_photo=files.get("profile_photo"),   # 🔥 FILE
        nationality=data.get("nationality"),
        id_proof_type=data.get("id_proof_type"),
        id_number=data.get("id_number"),
        id_document=files.get("id_document"),       # 🔥 FILE
        permanent_address=data.get("permanent_address"),
        district=data.get("district"),
        state=data.get("state"),
        pin_code=data.get("pin_code"),
        emergency_contact=data.get("emergency_contact"),
    )

    return tenant


# 🔥 GET TENANTS
def get_tenants(user):
    return Tenant.objects.filter(owner=user)


# 🔥 CREATE OCCUPANCY (same as before)
def create_occupancy(user, data):

    occupancy = Occupancy.objects.create(
        tenant_id=data.get("tenant"),
        unit_id=data.get("unit"),
        subunit_id=data.get("subunit"),
        allotted_by=user,
        rent=data.get("rent"),
        billing_type=data.get("billing_type"),
        billing_cycle=data.get("billing_cycle"),
        check_in_date=data.get("check_in_date"),
        next_due_date=data.get("next_due_date"),
        security_deposit=data.get("security_deposit") or 0,
        deposit_paid=data.get("deposit_paid") or False,
    )

    return occupancy

# 🔥 CREATE CHARGE
def create_charge(data):

    charge = Charge.objects.create(
        occupancy_id=data.get("occupancy"),
        charge_type=data.get("charge_type"),
        description=data.get("description"),
        amount=data.get("amount"),
        charge_date=data.get("charge_date"),
    )

    return charge


# 🔥 GET CHARGES (BY OCCUPANCY)
def get_charges(occupancy_id, user):
    return Charge.objects.filter(occupancy_id=occupancy_id, occupancy__tenant__owner=user
    )
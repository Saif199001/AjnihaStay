from django.utils import timezone
from rest_framework import serializers


class DashboardQuerySerializer(serializers.Serializer):
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    upcoming_days = serializers.IntegerField(required=False, min_value=1, max_value=90)
    availability_limit = serializers.IntegerField(required=False, min_value=1, max_value=500)
    upcoming_vacancy_limit = serializers.IntegerField(required=False, min_value=1, max_value=500)

    def validate(self, attrs):
        today = timezone.localdate()
        start = attrs.get("period_start") or today.replace(day=1)
        end = attrs.get("period_end") or today
        if start > end:
            raise serializers.ValidationError({"period_end": "period_end must be on or after period_start."})
        return attrs


class DashboardAvailabilitySerializer(serializers.Serializer):
    property_id = serializers.IntegerField()
    property_name = serializers.CharField()
    unit_id = serializers.IntegerField()
    unit_number = serializers.CharField()
    subunit_id = serializers.IntegerField(allow_null=True)
    subunit_number = serializers.CharField(allow_null=True, allow_blank=True)
    available_capacity = serializers.IntegerField(min_value=1)
    type = serializers.ChoiceField(choices=("unit", "subunit"))


class DashboardVacancySerializer(serializers.Serializer):
    occupancy_id = serializers.IntegerField()
    property_id = serializers.IntegerField()
    property_name = serializers.CharField()
    unit_id = serializers.IntegerField()
    unit_number = serializers.CharField()
    subunit_id = serializers.IntegerField(allow_null=True)
    subunit_number = serializers.CharField(allow_null=True, allow_blank=True)
    tenant_id = serializers.IntegerField()
    tenant_name = serializers.CharField()
    vacancy_date = serializers.DateField()


class DashboardSummarySerializer(serializers.Serializer):
    total_properties = serializers.IntegerField(min_value=0)
    total_units = serializers.IntegerField(min_value=0)
    total_unit_capacity = serializers.IntegerField(min_value=0)
    occupied_unit_slots = serializers.IntegerField(min_value=0)
    available_unit_slots = serializers.IntegerField(min_value=0)
    occupancy_rate = serializers.FloatField(min_value=0, max_value=100)
    active_tenants = serializers.IntegerField(min_value=0)
    total_subunits = serializers.IntegerField(min_value=0)
    occupied_subunits = serializers.IntegerField(min_value=0)
    available_subunits = serializers.IntegerField(min_value=0)


class DashboardFinancialSerializer(serializers.Serializer):
    period_invoiced = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    period_rent = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    period_charges = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    period_collected = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    collection_rate = serializers.FloatField(min_value=0, max_value=100)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    overdue = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class DashboardResponseSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    period = serializers.DictField(child=serializers.DateField())
    summary = DashboardSummarySerializer()
    financial = DashboardFinancialSerializer()
    availability = DashboardAvailabilitySerializer(many=True)
    availability_total = serializers.IntegerField(min_value=0)
    availability_truncated = serializers.BooleanField()
    upcoming_vacancies = DashboardVacancySerializer(many=True)
    upcoming_vacancies_total = serializers.IntegerField(min_value=0)
    upcoming_vacancies_truncated = serializers.BooleanField()

from decimal import Decimal

from django.test import SimpleTestCase

from payments.serializers import PaymentAllocationRequestSerializer


class PaymentAllocationSerializerTests(SimpleTestCase):
    def test_amount_precision_matches_model_limit(self):
        serializer = PaymentAllocationRequestSerializer(
            data={"invoice": 1, "amount": "99999999.99"}
        )
        self.assertTrue(serializer.is_valid())

    def test_amount_over_model_precision_is_rejected(self):
        serializer = PaymentAllocationRequestSerializer(
            data={"invoice": 1, "amount": "100000000.00"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("amount", serializer.errors)

    def test_amount_is_normalized_to_decimal(self):
        serializer = PaymentAllocationRequestSerializer(
            data={"invoice": 1, "amount": "1000.00"}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["amount"], Decimal("1000.00"))

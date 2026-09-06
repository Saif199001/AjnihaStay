"""Payment signals are intentionally non-authoritative.

Financial state transitions are owned by payments.services.record_payment()
and future canonical financial commands. This module remains available for
compatibility with existing app loading while deliberately avoiding invoice
financial mutation from ORM lifecycle signals.
"""

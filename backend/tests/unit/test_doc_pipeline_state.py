"""Structural type-shape tests for DocPipelineState and PaymentRecordDict.

These tests assert all required keys are present in the TypedDict annotations.
No runtime graph invocation is required — pure introspection.
"""

from backend.src.graph.doc_pipeline.state import DocPipelineState, PaymentRecordDict


class TestPaymentRecordDictShape:
    REQUIRED_KEYS = {
        "customer_name",
        "account_number",
        "payee",
        "payment_id",
        "payment_method",
        "payment_date",
        "invoice_number",
        "reference_doc_number",
        "amount_paid",
        "currency",
        "deductions",
        "deduction_type",
        "notes",
        "page_number",
        "confidence_scores",
        "validation_status",
    }

    def test_all_required_keys_present(self):
        annotations = PaymentRecordDict.__annotations__
        missing = self.REQUIRED_KEYS - set(annotations.keys())
        assert not missing, f"PaymentRecordDict is missing keys: {missing}"

    def test_no_extra_undeclared_keys(self):
        """Fail fast if a field is renamed or removed without updating the constant."""
        annotations = set(PaymentRecordDict.__annotations__.keys())
        undeclared = annotations - self.REQUIRED_KEYS
        assert not undeclared, (
            f"PaymentRecordDict has undeclared keys not in REQUIRED_KEYS: {undeclared}. "
            "Update REQUIRED_KEYS if this is intentional."
        )


class TestDocPipelineStateShape:
    REQUIRED_KEYS = {
        "batch_id",
        "run_record_id",
        "source_file_path",
        "work_file_path",
        "guid_filename",
        "doc_type",
        "prompt_config",
        "page_images",
        "raw_records",
        "normalised_records",
        "validated_records",
        "extraction_attempts",
        "error",
        "error_type",
    }

    def test_all_required_keys_present(self):
        annotations = DocPipelineState.__annotations__
        missing = self.REQUIRED_KEYS - set(annotations.keys())
        assert not missing, f"DocPipelineState is missing keys: {missing}"

    def test_no_extra_undeclared_keys(self):
        annotations = set(DocPipelineState.__annotations__.keys())
        undeclared = annotations - self.REQUIRED_KEYS
        assert not undeclared, (
            f"DocPipelineState has undeclared keys not in REQUIRED_KEYS: {undeclared}. "
            "Update REQUIRED_KEYS if this is intentional."
        )

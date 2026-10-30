"""The models carry every field the specification names (spec 3B, 4), with the spec's value
sets, and every rule is a named database constraint. No database needed."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from oak_binder.db import Base
from oak_binder.models import SECTIONS, BinderState, Template, WpStatus

# Spec 4, the Pass 1 tables, field for field. Foreign keys carry the _id suffix.
SPEC_FIELDS: dict[str, set[str]] = {
    "binder": {
        "engagement",
        "template",
        "report_date",
        "assembly_due",
        "assembled_at",
        "assembly_hash",
        "retention_until",
        "state",
    },
    "wp": {
        "binder_id",
        "ref",
        "section",
        "title",
        "sa_refs",
        "objective",
        "procedure",
        "population_sample",  # spec 3B: "population and sample"
        "result",
        "conclusion",
        "status",
        "current_version",
    },
    "wp_version": {
        "wp_id",
        "version",
        "body",
        "prepared_by",
        "prepared_at",
        "reviewed_by",
        "reviewed_at",
        "content_hash",
        "amendment_reason",
    },
    "wp_attachment": {"wp_version_id", "vault_doc_id", "identifying_chars", "sha256"},
    # Stage 6: the append-only record of assembly, amendment, purge and production (spec 3F,
    # 3G: "the manifest records the amendment", "the purge writes its own record").
    "binder_event": {"binder_id", "kind", "actor", "at", "reason", "details"},
    # Spec 4: review_note wp · raised_by · assigned_to · text · state · responded_at · cleared_by
    "review_note": {
        "wp_id",
        "raised_by",
        "assigned_to",
        "text",
        "state",
        "responded_at",
        "cleared_by",
    },
    # Spec 4: access_log binder · user · action · at (post-assembly only; spec 3H)
    "access_log": {"binder_id", "user", "action", "at"},
    # Spec 4: xref from_wp · to_wp | to_fs_line | to_vault_doc · direction
    "xref": {"from_wp", "to_wp", "to_fs_line", "to_vault_doc", "direction"},
}


def test_pass1_tables_and_no_others() -> None:
    assert set(Base.metadata.tables) == set(SPEC_FIELDS)


def test_every_spec_field_is_a_column() -> None:
    for table, fields in SPEC_FIELDS.items():
        columns = set(Base.metadata.tables[table].columns.keys())
        assert fields <= columns, f"{table} is missing {fields - columns}"


def test_status_values_follow_the_spec_in_order() -> None:
    assert [s.value for s in WpStatus] == [
        "draft",
        "prepared",
        "in_review",
        "reviewed",
        "signed_off",
    ]


def test_templates_are_the_four_engagement_types() -> None:
    assert {t.value for t in Template} == {"statutory", "tax_audit", "bank_branch", "internal"}


def test_binder_states() -> None:
    assert [s.value for s in BinderState] == ["open", "assembled", "purged"]


def test_sections_are_a_to_t_w_x_z() -> None:
    assert SECTIONS == tuple("ABCDEFGHIJKLMNOPQRST") + ("W", "X", "Z")
    assert not {"U", "V", "Y"} & set(SECTIONS)


def test_every_rule_is_a_named_constraint() -> None:
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint | UniqueConstraint | ForeignKeyConstraint):
                assert constraint.name, f"unnamed {type(constraint).__name__} on {table.name}"


def test_no_cascading_deletes_in_an_audit_file() -> None:
    for table in Base.metadata.tables.values():
        for fk in table.foreign_key_constraints:
            assert fk.ondelete == "RESTRICT", f"{table.name}.{fk.name} must RESTRICT"


def test_named_rules_from_the_spec_exist() -> None:
    names = {c.name for t in Base.metadata.tables.values() for c in t.constraints}
    assert {
        "ck_wp_signed_off_has_conclusion",  # spec 8.1
        "ck_binder_report_clocks",  # spec 3F, 3G, 8.7: +60 days, +7 years
        "ck_binder_assembly",  # spec 3F: assembled means frozen with a hash
        "uq_wp_binder_ref",  # spec 3B: reference stable, never reused within a binder
        "ck_wp_version_content_hash",  # spec 4: content_hash
        "ck_wp_attachment_sha256",  # spec 4: sha256
    } <= names

"""PostgreSQL Row-Level Security DDL shared by init_db() and the Alembic migration.

Every tenant-scoped table gets:
    ENABLE + FORCE ROW LEVEL SECURITY (FORCE so the table owner is filtered too), and
    POLICY tenant_isolation: tenant_id = current_setting('app.current_tenant_id')

tenant_id columns are VARCHAR(36) holding the canonical (lower-case) UUID text, so the policy
compares text instead of casting every row to uuid (keeps the tenant_id index usable). NULLIF(..., '')
makes an unset/reset setting match nothing instead of raising a cast error.

NOTE: PostgreSQL superusers and roles with BYPASSRLS ignore every policy. The API must connect as
an ordinary role for RLS to be enforced.
"""

from typing import Iterable, List

from sqlalchemy import MetaData

TENANT_SETTING = "app.current_tenant_id"
POLICY_NAME = "tenant_isolation"


def tenant_scoped_tables(metadata: MetaData) -> List[str]:
    return sorted(t.name for t in metadata.sorted_tables if "tenant_id" in t.c)


def rls_statements(table: str, column: str = "tenant_id") -> List[str]:
    predicate = f"{column} = NULLIF(current_setting('{TENANT_SETTING}', true), '')"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}",
        f"CREATE POLICY {POLICY_NAME} ON {table} USING ({predicate}) WITH CHECK ({predicate})",
    ]


def all_rls_statements(tenant_tables: Iterable[str]) -> List[str]:
    stmts: List[str] = []
    for table in tenant_tables:
        stmts.extend(rls_statements(table))
    # The tenants table is keyed by its own id
    stmts.extend(rls_statements("tenants", column="id"))
    return stmts

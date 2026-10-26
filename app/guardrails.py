import re
from typing import Tuple, List

ALLOWED_TABLES = {"orders", "customers", "products", "departments"}

FORBIDDEN_SQL_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
    "CREATE", "REPLACE", "GRANT", "REVOKE", "ATTACH", "DETACH",
    "PRAGMA", "VACUUM", "EXEC", "EXECUTE", "MERGE"
}


class SQLGuardrailViolation(Exception):
    """Raised when generated SQL violates read-only or Responsible AI guardrails."""
    pass


def validate_and_sanitize_sql(sql: str, max_rows: int = 100) -> Tuple[str, List[str]]:
    """
    Enforces strict read-only SQL execution and safety guardrails:
    1. Only single-statement SELECT or WITH ... SELECT queries are allowed.
    2. Blocks all 17 mutating/administrative SQL keywords (DROP, DELETE, UPDATE, INSERT, ALTER, etc.).
    3. Blocks stacked queries (;) and SQL injection comment markers (-- or /* */).
    4. Verifies every FROM/JOIN table against the approved DataCo schema allowlist.
    5. Caps result size by appending `LIMIT 100` if no LIMIT <= 100 is present.
    """
    notes: List[str] = []
    if not sql or not sql.strip():
        raise SQLGuardrailViolation("Empty SQL query rejected.")

    cleaned = sql.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    if ";" in cleaned:
        raise SQLGuardrailViolation("Stacked multi-statement SQL queries (';') are prohibited.")

    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLGuardrailViolation("SQL inline or block comments ('--', '/*') are prohibited.")

    upper_tokens = re.findall(r"\b[A-Z_]+\b", cleaned.upper())
    if not upper_tokens or upper_tokens[0] not in ("SELECT", "WITH"):
        raise SQLGuardrailViolation(
            f"Only read-only SELECT or WITH queries are permitted (found '{upper_tokens[0] if upper_tokens else 'NONE'}')."
        )

    for tok in upper_tokens:
        if tok in FORBIDDEN_SQL_KEYWORDS:
            raise SQLGuardrailViolation(f"Mutating or administrative SQL keyword '{tok}' blocked by guardrail.")

    cte_aliases = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", cleaned, flags=re.IGNORECASE))
    cte_lower = {a.lower() for a in cte_aliases}

    referenced_tables = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", cleaned, flags=re.IGNORECASE)
    for tbl in referenced_tables:
        t_low = tbl.lower()
        if t_low not in ALLOWED_TABLES and t_low not in cte_lower:
            raise SQLGuardrailViolation(
                f"Table '{tbl}' is not in the approved DataCo schema allowlist: {sorted(ALLOWED_TABLES)}."
            )

    if "LIMIT" not in upper_tokens:
        cleaned = f"{cleaned} LIMIT {max_rows}"
        notes.append(f"Appended automatic LIMIT {max_rows} cap.")
    else:
        limit_match = re.search(r"\bLIMIT\s+(\d+)", cleaned, flags=re.IGNORECASE)
        if limit_match and int(limit_match.group(1)) > max_rows:
            cleaned = re.sub(r"\bLIMIT\s+\d+", f"LIMIT {max_rows}", cleaned, flags=re.IGNORECASE)
            notes.append(f"Reduced excessive LIMIT to {max_rows} cap.")

    return cleaned, notes

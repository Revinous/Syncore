from __future__ import annotations

from textual.widgets import DataTable


def simple_table(columns: list[str]) -> DataTable:
    table = DataTable(zebra_stripes=True)
    for column in columns:
        table.add_column(column)
    return table

"""Helpers for immutable Arrow table updates."""

import pyarrow as pa


def set_column(
    table: pa.Table, name: str, values: pa.Array | pa.ChunkedArray
) -> pa.Table:
    if name in table.column_names:
        return table.set_column(table.schema.get_field_index(name), name, values)
    return table.append_column(name, values)

"""Write and reread Iceberg rows through an independent PyIceberg client.

Adapted from lakekeeper-ubi's storage fixture; this script is streamed into a
throwaway engine container and is not an application dependency.
"""

from __future__ import annotations

import os
import sys

import pyarrow
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError

ROWS = {"id": [1, 2, 3], "label": ["alpha", "beta", "gamma"], "value": [1.5, 2.5, 3.5]}


def main() -> int:
    mode = sys.argv[1]
    catalog = RestCatalog(
        "qualification",
        **{
            "uri": os.environ["CATALOG_URI"],
            "warehouse": "qualification",
            "s3.endpoint": os.environ["S3_ENDPOINT"],
            "s3.access-key-id": os.environ["S3_ACCESS_KEY_ID"],
            "s3.secret-access-key": os.environ["S3_SECRET_ACCESS_KEY"],
            "s3.region": "local",
            "s3.path-style-access": "true",
        },
    )
    expected = pyarrow.table(ROWS)
    if mode == "write":
        try:
            catalog.create_namespace("roundtrip")
        except NamespaceAlreadyExistsError:
            pass
        table = catalog.create_table("roundtrip.readings", schema=expected.schema)
        table.append(expected)
        print(f"metadata-location={table.metadata_location}")
    elif mode != "read":
        raise SystemExit(f"unsupported mode: {mode}")

    table = catalog.load_table("roundtrip.readings")
    actual = table.scan().to_arrow()
    if actual.sort_by("id").to_pydict() != expected.sort_by("id").to_pydict():
        raise SystemExit("Iceberg row content did not round-trip")
    data_files = [task.file.file_path for task in table.scan().plan_files()]
    if not data_files:
        raise SystemExit("the Iceberg table has no data files")
    for path in data_files:
        print(f"data-file={path}")
    print(f"{mode}: {actual.num_rows} rows round-tripped through PyIceberg")
    return 0


if __name__ == "__main__":
    sys.exit(main())

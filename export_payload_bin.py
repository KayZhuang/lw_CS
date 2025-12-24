#!/usr/bin/env python3
# coding=utf8
"""
Export protobuf payload bytes from a log line (with "payload=...") into a .bin file.

Usage:
  python3 export_payload_bin.py <input_txt> <output_bin>

The input file should contain a single line in the same format used by message_common_simulate:
  ... version=.. orchId=.. customerId=.. clientId=.. tranId=.. type=.. payload=...
Only the protobuf payload bytes are exported (NOT the CommServer header).
"""

import sys

from proto_tools import handle_header


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: export_payload_bin.py <input_txt> <output_bin>", file=sys.stderr)
        return 2

    in_path = sys.argv[1]
    out_path = sys.argv[2]

    with open(in_path, "r", encoding="utf-8") as f:
        line = f.read().strip()

    if not line:
        print("ERROR: input file is empty", file=sys.stderr)
        return 2

    hdr = handle_header(line)
    payload = hdr["payload"]

    with open(out_path, "wb") as f:
        f.write(payload)

    print(f"OK: wrote {len(payload)} bytes to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



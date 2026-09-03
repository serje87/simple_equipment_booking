#!/usr/bin/env python3
import argparse
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent / "data")) / "equipment.db"

parser = argparse.ArgumentParser(description="Manage equipment records")
sub = parser.add_subparsers(dest="command", required=True)
sub.add_parser("list")
add = sub.add_parser("add"); add.add_argument("name"); add.add_argument("description"); add.add_argument("--address"); add.add_argument("--rdp", action="store_true"); add.add_argument("--ssh", action="store_true")
update = sub.add_parser("update"); update.add_argument("id", type=int); update.add_argument("--name"); update.add_argument("--description"); update.add_argument("--address"); update.add_argument("--clear-address", action="store_true"); update.add_argument("--rdp", choices=("on", "off")); update.add_argument("--ssh", choices=("on", "off"))
delete = sub.add_parser("delete"); delete.add_argument("id", type=int)
args = parser.parse_args()

database = sqlite3.connect(DB_PATH)
database.row_factory = sqlite3.Row
if args.command == "list":
    for row in database.execute("SELECT id, name, description, ip_or_hostname, rdp_enabled, ssh_enabled, booked_by_user_id FROM equipment ORDER BY name"):
        protocols = ",".join(name for name, enabled in (("RDP", row["rdp_enabled"]), ("SSH", row["ssh_enabled"])) if enabled) or "none"
        print(f"{row['id']:>3}  {row['name']}  |  {row['description']}  |  {row['ip_or_hostname'] or '-'}  |  {protocols}  |  {'booked' if row['booked_by_user_id'] else 'available'}")
elif args.command == "add":
    database.execute("INSERT INTO equipment(name, description, ip_or_hostname, rdp_enabled, ssh_enabled) VALUES (?, ?, ?, ?, ?)", (args.name, args.description, args.address, int(args.rdp), int(args.ssh))); database.commit()
elif args.command == "update":
    if args.name is None and args.description is None and args.address is None and not args.clear_address and args.rdp is None and args.ssh is None: parser.error("provide at least one field to update")
    fields=[]; values=[]
    if args.name is not None: fields.append("name = ?"); values.append(args.name)
    if args.description is not None: fields.append("description = ?"); values.append(args.description)
    if args.address is not None: fields.append("ip_or_hostname = ?"); values.append(args.address)
    if args.clear_address: fields.append("ip_or_hostname = NULL")
    if args.rdp is not None: fields.append("rdp_enabled = ?"); values.append(int(args.rdp == "on"))
    if args.ssh is not None: fields.append("ssh_enabled = ?"); values.append(int(args.ssh == "on"))
    values.append(args.id); database.execute(f"UPDATE equipment SET {', '.join(fields)} WHERE id = ?", values); database.commit()
elif args.command == "delete":
    database.execute("DELETE FROM equipment WHERE id = ?", (args.id,)); database.commit()

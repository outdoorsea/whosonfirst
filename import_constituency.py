#!/usr/bin/env python3
"""
Simple script to import a specific WOF SQLite database.
"""
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from import_wof_data import WOFImporter

def main():
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'wof'),
        'user': os.getenv('DB_USER', 'user'),
        'password': os.getenv('DB_PASS', 'password')
    }

    importer = WOFImporter(db_config=db_config, update_mode=False)

    # Connect to database
    importer.connect()

    # Import from the constituency database
    db_path = Path('wof_data/whosonfirst-data-constituency-us-latest.db')

    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    print(f"Importing from {db_path}...")
    count = importer.import_from_sqlite(db_path)
    print(f"Successfully imported {count} constituency records")

    # Close connection
    if importer.conn:
        importer.conn.close()

if __name__ == '__main__':
    main()

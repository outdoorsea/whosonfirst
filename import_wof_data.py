#!/usr/bin/env python3
"""
Who's On First Data Import Script
Downloads and imports WOF GeoJSON data into a PostGIS database.

Usage:
    python import_wof_data.py --regions US CA GB --placetypes locality neighbourhood

This script downloads WOF data bundles and imports them into PostgreSQL/PostGIS.
"""

import os
import sys
import json
import argparse
import logging
import requests
import bz2
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import execute_values
from shapely.geometry import shape
from shapely import wkt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'wof'),
    'user': os.getenv('DB_USER', 'user'),
    'password': os.getenv('DB_PASS', 'password')
}

# WOF Distribution URLs
WOF_DIST_BASE = "https://data.geocode.earth/wof/dist/"

# Common placetypes to import
PLACETYPE_PRIORITY = [
    'continent',
    'country',
    'region',
    'county',
    'locality',
    'neighbourhood',
    'borough'
]


class WOFImporter:
    """Handles downloading and importing WOF data into PostGIS."""

    def __init__(self, db_config: Dict, update_mode: bool = False):
        self.db_config = db_config
        self.conn = None
        self.cursor = None
        self.update_mode = update_mode

    def connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("Database connection closed")

    def setup_database(self):
        """Create tables and extensions if they don't exist."""
        logger.info("Setting up database schema...")

        # Enable PostGIS extension
        self.cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

        # Create whosonfirst table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS whosonfirst (
            id BIGINT PRIMARY KEY,
            parent_id BIGINT,
            name VARCHAR(255),
            placetype VARCHAR(50),
            country_code VARCHAR(2),
            properties JSONB,
            geom GEOMETRY(Geometry, 4326),
            bbox GEOMETRY(Polygon, 4326),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        self.cursor.execute(create_table_sql)

        # Create indexes if they don't exist
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_wof_placetype ON whosonfirst(placetype);",
            "CREATE INDEX IF NOT EXISTS idx_wof_parent_id ON whosonfirst(parent_id);",
            "CREATE INDEX IF NOT EXISTS idx_wof_country_code ON whosonfirst(country_code);",
            "CREATE INDEX IF NOT EXISTS idx_wof_name ON whosonfirst(name);",
            "CREATE INDEX IF NOT EXISTS idx_wof_geom ON whosonfirst USING GIST(geom);",
            "CREATE INDEX IF NOT EXISTS idx_wof_bbox ON whosonfirst USING GIST(bbox);",
            "CREATE INDEX IF NOT EXISTS idx_wof_properties ON whosonfirst USING GIN(properties);"
        ]

        for index_sql in indexes:
            self.cursor.execute(index_sql)

        self.conn.commit()
        logger.info("Database schema setup complete")

    def download_bundle(self, region: str, placetype: str, download_dir: Path) -> Optional[Path]:
        """
        Download a WOF data bundle (SQLite database).

        Args:
            region: ISO country code (e.g., 'US', 'GB', 'CA')
            placetype: WOF placetype (not used for SQLite bundles)
            download_dir: Directory to save downloaded files

        Returns:
            Path to decompressed database file, or None if download failed
        """
        # Construct download URL for SQLite database
        # Example: https://data.geocode.earth/wof/dist/whosonfirst-data-admin-us-latest.db.bz2
        bundle_name = f"whosonfirst-data-admin-{region.lower()}-latest.db.bz2"
        url = f"{WOF_DIST_BASE}{bundle_name}"

        compressed_path = download_dir / bundle_name
        decompressed_path = download_dir / bundle_name.replace('.bz2', '')

        # Skip if already decompressed
        if decompressed_path.exists():
            logger.info(f"Database already exists: {decompressed_path}")
            return decompressed_path

        # Download if not already downloaded
        if not compressed_path.exists():
            logger.info(f"Downloading {url}...")

            try:
                response = requests.get(url, stream=True, timeout=300)
                response.raise_for_status()

                # Download with progress
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(compressed_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (1024 * 1024 * 10) == 0:  # Log every 10MB
                                percent = (downloaded / total_size) * 100
                                logger.info(f"Download progress: {percent:.1f}%")

                logger.info(f"Downloaded: {compressed_path}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download {url}: {e}")
                return None

        # Decompress the bz2 file
        logger.info(f"Decompressing {compressed_path}...")
        try:
            with bz2.open(compressed_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    # Decompress in chunks
                    while True:
                        chunk = f_in.read(1024 * 1024)  # 1MB chunks
                        if not chunk:
                            break
                        f_out.write(chunk)

            logger.info(f"Decompressed to: {decompressed_path}")
            return decompressed_path

        except Exception as e:
            logger.error(f"Failed to decompress {compressed_path}: {e}")
            return None

    def import_from_sqlite(self, db_path: Path, placetypes: Optional[List[str]] = None) -> int:
        """
        Import data from a WOF SQLite database.

        Args:
            db_path: Path to the SQLite database file
            placetypes: Optional list of placetypes to filter

        Returns:
            Number of records imported
        """
        logger.info(f"Importing from SQLite database: {db_path}")

        try:
            # Connect to SQLite database
            sqlite_conn = sqlite3.connect(db_path)
            sqlite_cursor = sqlite_conn.cursor()

            # Build query - only id and body are in the schema
            query = "SELECT id, body FROM geojson"
            sqlite_cursor.execute(query)

            imported = 0
            batch_size = 100
            batch = []

            for row in sqlite_cursor:
                wof_id, body_json = row

                try:
                    # Parse GeoJSON body
                    feature = json.loads(body_json)
                    parsed = self.parse_geojson_feature(feature)

                    # Filter by placetype if specified
                    if parsed and placetypes and parsed['placetype'] not in placetypes:
                        continue

                    if parsed:
                        batch.append(parsed)

                        if len(batch) >= batch_size:
                            # Import batch
                            for record in batch:
                                try:
                                    self.insert_record(record)
                                    imported += 1
                                except psycopg2.IntegrityError:
                                    if not self.update_mode:
                                        self.conn.rollback()
                                except Exception as e:
                                    logger.error(f"Failed to insert record {record['id']}: {e}")
                                    self.conn.rollback()

                            self.conn.commit()
                            batch = []

                            if imported % 1000 == 0:
                                logger.info(f"Imported {imported} records...")

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for ID {wof_id}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to process record {wof_id}: {e}")
                    continue

            # Import remaining batch
            if batch:
                for record in batch:
                    try:
                        self.insert_record(record)
                        imported += 1
                    except psycopg2.IntegrityError:
                        if not self.update_mode:
                            self.conn.rollback()
                    except Exception as e:
                        logger.error(f"Failed to insert record: {e}")
                        self.conn.rollback()

                self.conn.commit()

            sqlite_conn.close()
            logger.info(f"Import complete: {imported} records imported")
            return imported

        except Exception as e:
            logger.error(f"Failed to import from SQLite: {e}")
            return 0

    def parse_geojson_feature(self, feature: Dict) -> Optional[Dict]:
        """
        Parse a WOF GeoJSON feature into database format.

        Args:
            feature: GeoJSON feature dictionary

        Returns:
            Dictionary with parsed data, or None if parsing failed
        """
        try:
            properties = feature.get('properties', {})
            geometry = feature.get('geometry')

            # Extract key fields
            wof_id = properties.get('wof:id')
            if not wof_id:
                return None

            parent_id = properties.get('wof:parent_id', -1)
            name = properties.get('wof:name', '') or properties.get('name', '')
            placetype = properties.get('wof:placetype', '')
            country_code = properties.get('wof:country', '') or properties.get('iso:country', '')

            # Convert geometry to WKT
            geom_wkt = None
            bbox_wkt = None

            if geometry:
                try:
                    geom_shape = shape(geometry)
                    geom_wkt = geom_shape.wkt

                    # Create bounding box
                    bounds = geom_shape.bounds  # (minx, miny, maxx, maxy)
                    if bounds:
                        bbox_wkt = f"POLYGON(({bounds[0]} {bounds[1]}, {bounds[2]} {bounds[1]}, {bounds[2]} {bounds[3]}, {bounds[0]} {bounds[3]}, {bounds[0]} {bounds[1]}))"
                except Exception as e:
                    logger.warning(f"Failed to parse geometry for {wof_id}: {e}")

            return {
                'id': wof_id,
                'parent_id': parent_id,
                'name': name,
                'placetype': placetype,
                'country_code': country_code,
                'properties': json.dumps(properties),
                'geom': geom_wkt,
                'bbox': bbox_wkt
            }

        except Exception as e:
            logger.warning(f"Failed to parse feature: {e}")
            return None

    def import_geojson_file(self, geojson_path: Path):
        """Import a single GeoJSON file."""
        try:
            with open(geojson_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle both Feature and FeatureCollection
            features = []
            if data.get('type') == 'FeatureCollection':
                features = data.get('features', [])
            elif data.get('type') == 'Feature':
                features = [data]
            else:
                logger.warning(f"Unknown GeoJSON type in {geojson_path}")
                return 0

            imported = 0
            for feature in features:
                parsed = self.parse_geojson_feature(feature)
                if parsed:
                    try:
                        self.insert_record(parsed)
                        imported += 1
                    except psycopg2.IntegrityError:
                        # Record already exists (only in non-update mode)
                        if not self.update_mode:
                            self.conn.rollback()
                        else:
                            # This shouldn't happen in update mode, but handle it
                            logger.warning(f"Integrity error in update mode for ID {parsed['id']}")
                            self.conn.rollback()
                    except Exception as e:
                        logger.error(f"Failed to insert record: {e}")
                        self.conn.rollback()

            self.conn.commit()
            return imported

        except Exception as e:
            logger.error(f"Failed to import {geojson_path}: {e}")
            return 0

    def insert_record(self, record: Dict):
        """
        Insert a single record into the database.
        If update_mode is True, uses UPSERT to update existing records.
        """
        if self.update_mode:
            # UPSERT: Insert or update if exists
            sql = """
            INSERT INTO whosonfirst (id, parent_id, name, placetype, country_code, properties, geom, bbox)
            VALUES (%(id)s, %(parent_id)s, %(name)s, %(placetype)s, %(country_code)s, %(properties)s::jsonb,
                    ST_GeomFromText(%(geom)s, 4326), ST_GeomFromText(%(bbox)s, 4326))
            ON CONFLICT (id) DO UPDATE SET
                parent_id = EXCLUDED.parent_id,
                name = EXCLUDED.name,
                placetype = EXCLUDED.placetype,
                country_code = EXCLUDED.country_code,
                properties = EXCLUDED.properties,
                geom = EXCLUDED.geom,
                bbox = EXCLUDED.bbox,
                created_at = CURRENT_TIMESTAMP
            """
        else:
            # Standard insert (will raise IntegrityError if duplicate)
            sql = """
            INSERT INTO whosonfirst (id, parent_id, name, placetype, country_code, properties, geom, bbox)
            VALUES (%(id)s, %(parent_id)s, %(name)s, %(placetype)s, %(country_code)s, %(properties)s::jsonb,
                    ST_GeomFromText(%(geom)s, 4326), ST_GeomFromText(%(bbox)s, 4326))
            """

        self.cursor.execute(sql, record)

    def import_directory(self, data_dir: Path, placetypes: Optional[List[str]] = None):
        """
        Recursively import all GeoJSON files in a directory.

        Args:
            data_dir: Directory containing WOF GeoJSON files
            placetypes: Optional list of placetypes to filter
        """
        logger.info(f"Importing data from {data_dir}...")

        total_imported = 0
        file_count = 0

        # Find all .geojson files
        for geojson_file in data_dir.rglob('*.geojson'):
            # Filter by placetype if specified
            if placetypes:
                # WOF files are typically organized like: data/123/456/789/123456789.geojson
                # We need to read the file to check placetype
                # For efficiency, we could check the directory structure, but let's be thorough
                pass

            file_count += 1
            imported = self.import_geojson_file(geojson_file)
            total_imported += imported

            if file_count % 100 == 0:
                logger.info(f"Processed {file_count} files, imported {total_imported} records")

        logger.info(f"Import complete: {total_imported} records from {file_count} files")
        return total_imported


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Import Who\'s On First data into PostGIS'
    )
    parser.add_argument(
        '--regions',
        nargs='+',
        default=['US'],
        help='ISO country codes to import (e.g., US CA GB FR)'
    )
    parser.add_argument(
        '--placetypes',
        nargs='+',
        default=PLACETYPE_PRIORITY,
        help='Placetypes to import'
    )
    parser.add_argument(
        '--download-dir',
        type=str,
        default='./wof_data',
        help='Directory to download and extract data'
    )
    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='Skip download and use existing data'
    )
    parser.add_argument(
        '--update',
        action='store_true',
        help='Update existing records (UPSERT mode). Use this to refresh data with latest changes.'
    )

    args = parser.parse_args()

    # Create download directory
    download_dir = Path(args.download_dir)
    download_dir.mkdir(exist_ok=True)

    # Initialize importer
    importer = WOFImporter(DB_CONFIG, update_mode=args.update)

    if args.update:
        logger.info("Running in UPDATE mode - existing records will be refreshed")
    else:
        logger.info("Running in INSERT mode - existing records will be skipped")

    try:
        # Connect to database
        importer.connect()

        # Setup database schema
        importer.setup_database()

        # Process each region
        for region in args.regions:
            logger.info(f"Processing region: {region}")

            if not args.skip_download:
                # Download and decompress SQLite database
                db_path = importer.download_bundle(region, 'admin', download_dir)
                if not db_path:
                    logger.error(f"Failed to download bundle for {region}")
                    continue
            else:
                # Use existing database file
                db_name = f"whosonfirst-data-admin-{region.lower()}-latest.db"
                db_path = download_dir / db_name
                if not db_path.exists():
                    logger.error(f"Database file not found: {db_path}")
                    continue

            # Import data from SQLite database
            importer.import_from_sqlite(db_path, args.placetypes)

        logger.info("All imports complete!")

    except Exception as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)
    finally:
        importer.disconnect()


if __name__ == '__main__':
    main()

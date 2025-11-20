# Who's on First (WOF) Cloud Setup Guide

**Version**: 1.0
**Date**: November 2025

## 1. Overview

This document outlines a cloud-based alternative for hosting the Who's on First (WOF) data. While the local SQLite database is excellent for local development and smaller-scale deployments, a cloud-based solution is recommended for production environments to ensure scalability, manageability, and performance, especially when dealing with the entire world's dataset.

The recommended cloud architecture is a **managed PostgreSQL database with the PostGIS extension**.

### Benefits of a Cloud-Based PostGIS Approach:
- **Scalability**: Managed database services (like AWS RDS, Google Cloud SQL, or Azure Database for PostgreSQL) can be easily scaled up as query load increases.
- **Performance**: PostGIS is the industry standard for geospatial queries and provides powerful indexing capabilities (like GiST indexes) that are highly optimized for point-in-polygon lookups.
- **Manageability**: Cloud providers handle database maintenance, backups, and replication, reducing operational overhead.
- **Centralization**: The database serves as a single source of truth for all backend services, which is crucial for a distributed or microservices-based architecture.

---

## 2. Setup and Configuration

### Step 1: Provision a Managed PostgreSQL Database

Choose a cloud provider and set up a managed PostgreSQL instance.

- **AWS**: Use **Amazon RDS for PostgreSQL**.
- **Google Cloud**: Use **Cloud SQL for PostgreSQL**.
- **Azure**: Use **Azure Database for PostgreSQL**.

When provisioning, choose an instance size appropriate for the WOF dataset (which can be several hundred gigabytes). Start with a general-purpose instance and monitor performance.

### Step 2: Enable the PostGIS Extension

After the database is running, connect to it using a SQL client (like `psql` or DBeaver) and enable the PostGIS extension. This adds all the necessary geospatial data types and functions to your database.

```sql
-- Connect to your database and run this command
CREATE EXTENSION postgis;

-- Verify the installation
SELECT PostGIS_full_version();
```

---

## 3. Data Import (ETL Process)

This is the most complex part of the setup. The WOF data, typically distributed as GeoJSON files, needs to be imported into your PostGIS database. The `wof-postgis` project on GitHub is a valuable resource for this.

### High-Level ETL (Extract, Transform, Load) Steps:

1.  **Download WOF Data**: Instead of the SQLite bundle, you will download the GeoJSON data bundles from the WOF distributors.
    *   **Download Page**: [https://dist.whosonfirst.org/geojson/](https://dist.whosonfirst.org/geojson/)

2.  **Define Database Schema**: Create tables in your PostgreSQL database to hold the WOF data. A primary table will store the `id`, `parent_id`, `name`, `placetype`, and other properties, along with a `geometry` column of type `GEOMETRY`.

    ```sql
    CREATE TABLE whosonfirst (
        id BIGINT PRIMARY KEY,
        parent_id BIGINT,
        name VARCHAR(255),
        placetype VARCHAR(50),
        properties JSONB,
        geom GEOMETRY(Geometry, 4326) -- Store as standard WGS 84 lat/lon
    );
    ```

3.  **Create an Import Script**: Write a script (e.g., in Python) that:
    *   Reads each GeoJSON file.
    *   Parses the properties and geometry.
    *   Transforms the data into a format suitable for your database schema.
    *   Inserts the data into the `whosonfirst` table.
    *   Use a library like `psycopg2` for database interaction and `shapely` for handling geometries.

4.  **Build a Geospatial Index**: After the data is imported, create a GiST (Generalized Search Tree) index on the geometry column. **This is critical for fast point-in-polygon queries.**

    ```sql
    CREATE INDEX wof_geom_idx ON whosonfirst USING GIST (geom);
    ```

---

## 4. Querying the Data

With the data imported and indexed, the `WhosOnFirstService` in the Lilypad backend will execute SQL queries against this database instead of the local SQLite file.

### Example: Point-in-Polygon Query

To find the smallest administrative region that contains a given latitude and longitude, you can use the `ST_Contains` function from PostGIS.

```sql
-- Find the neighborhood that contains the point for San Francisco City Hall
-- Longitude: -122.4194, Latitude: 37.7749

SELECT
    id,
    name,
    placetype
FROM
    whosonfirst
WHERE
    placetype = 'neighbourhood' AND
    ST_Contains(geom, ST_SetSRID(ST_MakePoint(-122.4194, 37.7749), 4326));
```

### Example: Hierarchy Lookup

Once you have a `wof:id`, you can query for its parent and ancestors by following the `parent_id` chain or by using the hierarchy data stored in the `properties` JSONB column.

---

## 5. Maintenance and Updates

- **Data Freshness**: The WOF data is updated periodically. You will need to create an automated process (e.g., a weekly or monthly cron job) that runs your ETL script to download and import the latest data.
- **Staging Environment**: Always run the data import process in a staging environment first to catch any schema changes or data quality issues before updating the production database.

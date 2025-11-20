# Who's On First - Data Management Guide

This guide explains how to import, update, and expand your Who's On First dataset over time.

## Import Modes

The `import_wof_data.py` script supports two modes:

### 1. INSERT Mode (Default)
- **Behavior**: Adds new records, skips existing ones (by WOF ID)
- **Use for**: Initial imports, adding new regions
- **Command**: `python import_wof_data.py --regions US`

### 2. UPDATE Mode
- **Behavior**: Adds new records AND updates existing ones with latest data
- **Use for**: Refreshing data with upstream changes
- **Command**: `python import_wof_data.py --regions US --update`

---

## Common Workflows

### Initial Setup: Start with US Data

```bash
# First time: Import US localities and neighbourhoods
python import_wof_data.py --regions US --placetypes locality neighbourhood

# This downloads ~2-5GB and takes 1-2 hours
```

**What happens:**
- Downloads `whosonfirst-data-admin-us-latest.zip` to `./wof_data/`
- Extracts GeoJSON files
- Imports all US localities and neighbourhoods
- Creates spatial indexes for fast queries

---

### Expanding: Add New Regions

```bash
# Later: Add Canada data (INSERT mode - default)
python import_wof_data.py --regions CA --placetypes locality neighbourhood

# Add multiple regions at once
python import_wof_data.py --regions GB FR DE --placetypes locality neighbourhood
```

**What happens:**
- Downloads new region bundles
- Imports only NEW records (skips if ID already exists)
- Safe to run multiple times
- Your US data remains unchanged

---

### Updating: Refresh Existing Data

Who's On First data is updated regularly with corrections, new places, and boundary changes.

```bash
# Update US data with latest changes (UPDATE mode)
python import_wof_data.py --regions US --update --placetypes locality neighbourhood

# Update all your regions
python import_wof_data.py --regions US CA GB FR --update
```

**What happens:**
- Downloads latest bundles (or uses cached with `--skip-download`)
- **Updates** existing records with new data
- **Inserts** any new places
- Refreshes geometries, names, and properties

---

## Data Import Options

### By Region (ISO Country Codes)

```bash
# Single region
python import_wof_data.py --regions US

# Multiple regions
python import_wof_data.py --regions US CA MX

# Many regions
python import_wof_data.py --regions US CA GB FR DE ES IT
```

**Common ISO codes:**
- `US` - United States
- `CA` - Canada
- `GB` - United Kingdom
- `FR` - France
- `DE` - Germany
- `MX` - Mexico
- `AU` - Australia
- `JP` - Japan

[Full list](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2)

### By Placetype

```bash
# Just localities (cities, towns)
python import_wof_data.py --regions US --placetypes locality

# Localities and neighbourhoods
python import_wof_data.py --regions US --placetypes locality neighbourhood

# All administrative levels
python import_wof_data.py --regions US --placetypes continent country region county locality neighbourhood borough
```

**Placetype hierarchy (largest to smallest):**
1. `continent` - Continents (e.g., North America)
2. `country` - Countries (e.g., United States)
3. `region` - States/Provinces (e.g., California)
4. `county` - Counties (e.g., San Francisco County)
5. `locality` - Cities/Towns (e.g., San Francisco)
6. `neighbourhood` - Neighborhoods (e.g., Mission District)
7. `borough` - Boroughs (e.g., Manhattan)

### Advanced Options

```bash
# Skip download if you already have the files
python import_wof_data.py --regions US --skip-download

# Custom download directory
python import_wof_data.py --regions US --download-dir /path/to/data

# Combine all options
python import_wof_data.py \
  --regions US CA \
  --placetypes locality neighbourhood \
  --download-dir ./my_wof_data \
  --update
```

---

## Real-World Scenarios

### Scenario 1: Starting Small, Growing Over Time

**Week 1: Launch with US data**
```bash
python import_wof_data.py --regions US --placetypes locality neighbourhood
```
- Result: ~500,000 US places
- Storage: ~5GB
- Time: 1-2 hours

**Month 2: Expand to North America**
```bash
python import_wof_data.py --regions CA MX --placetypes locality neighbourhood
```
- Result: +200,000 places (CA + MX)
- Storage: +2GB
- Time: 30 minutes
- **Your US data is unchanged**

**Month 6: Refresh with latest data**
```bash
python import_wof_data.py --regions US CA MX --update --placetypes locality neighbourhood
```
- Result: Updates all 700,000 places with latest WOF data
- Storage: Same (~7GB)
- Time: 2-3 hours

---

### Scenario 2: Global Coverage from Day 1

**Import all major regions:**
```bash
python import_wof_data.py \
  --regions US CA GB FR DE ES IT AU JP CN \
  --placetypes locality neighbourhood
```
- Result: ~3-5 million places
- Storage: ~50GB
- Time: 6-12 hours

**Monthly refresh:**
```bash
# Set up a cron job to update monthly
0 2 1 * * cd /path/to/whosonfirst && python import_wof_data.py --regions US CA GB FR DE ES IT AU JP CN --update --skip-download
```

---

### Scenario 3: Full World Dataset

**Import everything:**
```bash
# Download all available regions
# Note: This is MASSIVE (100GB+, 24+ hours)
python import_wof_data.py \
  --regions US CA GB FR DE ES IT AU JP CN BR IN RU ... \
  --placetypes continent country region county locality neighbourhood borough
```

**Better approach:** Import incrementally by continent
```bash
# North America
python import_wof_data.py --regions US CA MX

# Europe
python import_wof_data.py --regions GB FR DE ES IT

# Asia
python import_wof_data.py --regions CN JP IN

# etc.
```

---

## Monitoring Import Progress

### During Import

The script logs progress every 100 files:
```
INFO - Processed 100 files, imported 4523 records
INFO - Processed 200 files, imported 9104 records
```

### Check Database Contents

```bash
# Connect to database
./scripts/connect-db.sh

# Or manually
psql -h localhost -U user -d wof
```

```sql
-- Count records by placetype
SELECT placetype, COUNT(*) as count
FROM whosonfirst
GROUP BY placetype
ORDER BY count DESC;

-- Count by country
SELECT country_code, COUNT(*) as count
FROM whosonfirst
GROUP BY country_code
ORDER BY count DESC;

-- Check latest imports
SELECT placetype, country_code, COUNT(*) as count, MAX(created_at) as last_updated
FROM whosonfirst
GROUP BY placetype, country_code
ORDER BY last_updated DESC
LIMIT 20;

-- Database size
SELECT pg_size_pretty(pg_database_size('wof'));

-- Table size
SELECT pg_size_pretty(pg_total_relation_size('whosonfirst'));
```

---

## Performance Tips

### Speed Up Imports

1. **Use faster storage** (SSD preferred)
2. **Increase database resources** during import:
   ```sql
   -- Temporarily increase work_mem for import
   SET work_mem = '256MB';
   ```
3. **Import in batches** by placetype:
   ```bash
   # Import localities first (they're bigger)
   python import_wof_data.py --regions US --placetypes locality

   # Then neighbourhoods
   python import_wof_data.py --regions US --placetypes neighbourhood
   ```

### Reduce Storage

```sql
-- After import, vacuum and analyze
VACUUM ANALYZE whosonfirst;

-- Check index usage
SELECT indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan;
```

---

## Backup and Restore

### Before Major Updates

```bash
# Backup database before major update
pg_dump -h localhost -U user -d wof -F c -f wof_backup_$(date +%Y%m%d).dump

# Or just the whosonfirst table
pg_dump -h localhost -U user -d wof -t whosonfirst -F c -f wof_table_backup.dump
```

### Restore if Needed

```bash
# Restore full database
pg_restore -h localhost -U user -d wof -c wof_backup_20250114.dump

# Restore just the table
pg_restore -h localhost -U user -d wof -t whosonfirst wof_table_backup.dump
```

---

## Troubleshooting

### Import is Slow
- **Solution**: Check disk I/O, database CPU, and network
- **Tip**: Use `--skip-download` after first download

### Running Out of Space
- **Solution**: Import fewer placetypes or regions
- **Tip**: Start with just `locality` placetype

### Records Not Updating
- **Solution**: Make sure you're using `--update` flag
- **Check**: Verify the downloaded bundle is actually newer

### Download Fails
- **Solution**: Check internet connection to data.whosonfirst.org
- **Tip**: Download manually and use `--skip-download`

---

## Maintenance Schedule

### Recommended Schedule

**For production systems:**
- **Weekly**: Check database health, monitor size
- **Monthly**: Update data with `--update` flag
- **Quarterly**: Full backup and test restore
- **Annually**: Review and optimize indexes

**Example cron jobs:**
```bash
# Monthly data update (first Sunday at 2 AM)
0 2 * * 0 [ $(date +\%d) -le 7 ] && cd /path/to/whosonfirst && python import_wof_data.py --regions US CA --update --skip-download 2>&1 | logger -t wof-import

# Weekly health check
0 3 * * 1 psql -h localhost -U user -d wof -c "SELECT COUNT(*) FROM whosonfirst" 2>&1 | logger -t wof-health
```

---

## Summary: Your Workflow

```bash
# 1. Initial US import
python import_wof_data.py --regions US --placetypes locality neighbourhood

# 2. Add more regions later (safe, won't touch US data)
python import_wof_data.py --regions CA GB FR

# 3. Refresh with latest WOF data (updates existing + adds new)
python import_wof_data.py --regions US CA GB FR --update

# 4. Repeat step 3 monthly to stay current
```

**Key Points:**
- ✅ **Default mode (INSERT)**: Safe for adding new regions
- ✅ **Update mode**: Refreshes existing data
- ✅ **Idempotent**: Safe to run multiple times
- ✅ **Incremental**: Add regions as you grow
- ✅ **No data loss**: Updates preserve existing data structure

---

**Questions?** Check the [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) or database logs for more details.

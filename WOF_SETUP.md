# Who's on First (WOF) SQLite Database Setup

This document provides instructions for downloading, deploying, and testing the Who's on First (WOF) SQLite database for use in the Lilypad backend.

## 1. Download the WOF SQLite Database

The WOF data is available as pre-packaged SQLite databases. For our purposes, we will use the main distribution, which contains all the necessary data for our location-based services.

*   **Download Page**: [https://dist.whosonfirst.org/sqlite/](https://dist.whosonfirst.org/sqlite/)
*   **File to Download**: `whosonfirst-data-latest.db.bz2` (or the latest version available)

You can download this file using a web browser or via the command line:

```bash
curl -O https://dist.whosonfirst.org/sqlite/whosonfirst-data-latest.db.bz2
```

After downloading, you will need to decompress the file:

```bash
bunzip2 whosonfirst-data-latest.db.bz2
```

This will result in a file named `whosonfirst-data-latest.db`.

## 2. Deploy the Database

For local development, the database file should be placed in a location accessible by the Lilypad backend, but outside of the source code to avoid committing a large file to the git repository.

1.  **Create a `data` directory** at the root of the `lilypad-chat-backend` project, if it doesn't already exist.
2.  **Add the `data` directory to your `.gitignore` file** to prevent the database from being tracked by git.
3.  **Move the database file** into the `data` directory:

    ```bash
    mv whosonfirst-data-latest.db lilypad-chat-backend/data/
    ```

## 3. Test the Database

To ensure the database is working correctly, you can connect to it using the `sqlite3` command-line tool and run a simple query.

1.  **Connect to the database**:

    ```bash
    sqlite3 lilypad-chat-backend/data/whosonfirst-data-latest.db
    ```

2.  **Run a test query**. For example, to find the record for San Francisco:

    ```sql
    SELECT id, name, placetype FROM spr WHERE name = 'San Francisco' AND placetype = 'locality';
    ```

    You should see a result similar to this:

    ```
    85922583|San Francisco|locality
    ```

3.  **Exit the SQLite shell**:

    ```
    .quit
    ```

Once you have successfully completed these steps, the WOF database is ready for use by the `WhosOnFirstService` in the Lilypad backend.

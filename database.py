
import aiosqlite

DATABASE_NAME = "monitors.db"


async def initialize_database():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                city TEXT NOT NULL,
                condition TEXT NOT NULL,
                threshold REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

      
                # Add the rain-alert tracking column if needed.
        try:
            await db.execute("""
                ALTER TABLE monitors
                ADD COLUMN last_rain_alert_for TEXT
            """)
        except aiosqlite.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise

        await db.commit()

    print("Database initialized successfully!")



async def add_monitor(chat_id, city, condition, threshold):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO monitors
            (chat_id, city, condition, threshold)
            VALUES (?, ?, ?, ?)
        """, (chat_id, city, condition, threshold))

        await db.commit()
        return cursor.lastrowid


async def get_active_monitors():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        
        # Expire rain monitors after 24 hours.
        # Keep other monitors' existing 7-day expiry.
        await db.execute("""
    UPDATE monitors
    SET active = 0
    WHERE active = 1
      AND (
          (condition = 'rain'
           AND created_at <= datetime('now', '-24 hours'))
          OR
          (condition != 'rain'
           AND created_at <= datetime('now', '-7 days'))
      )
""")
        await db.commit()

        db.row_factory = aiosqlite.Row

        cursor = await db.execute("""
            SELECT * FROM monitors
            WHERE active = 1
        """)


        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def deactivate_monitor(monitor_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("""
            UPDATE monitors
            SET active = 0
            WHERE id = ?
        """, (monitor_id,))

        await db.commit()

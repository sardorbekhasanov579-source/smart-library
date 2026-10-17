"""Lokal SQLite bazasidan serverdagi PostgreSQL bazasiga ma'lumot ko'chirish.

`loaddata` har bir yozuvni alohida yuboradi — sekin va aloqa uzilishiga
chidamsiz. Bu skript PostgreSQL'ning `COPY` buyrug'idan foydalanadi:
butun jadval bitta oqimda yuboriladi, bir necha soniyada tugaydi.

Ishlatish (Windows cmd):

    set "DATABASE_URL=postgresql://...neon...?sslmode=require&channel_binding=require"
    python yuklash.py

Qo'shimcha imkoniyatlar:

    python yuklash.py --list                 jadvallar ro'yxati va yozuvlar soni
    python yuklash.py readers loans          faqat ko'rsatilgan jadvallar
    python yuklash.py --all                  barcha jadvallar
    python yuklash.py --force                serverdagi eski yozuvlarni o'chirib qayta yuklash

Diqqat: skript faqat o'qiydi (SQLite) va yozadi (PostgreSQL).
Lokal bazangizga hech qanday o'zgarish kiritmaydi.
"""
import os
import sqlite3
import sys

try:
    import psycopg
except ImportError:
    sys.exit(
        "psycopg o'rnatilmagan. Quyidagini ishga tushiring:\n"
        "    pip install \"psycopg[binary]\""
    )

SQLITE_PATH = "db.sqlite3"

# Bog'liqlik tartibi muhim: avval mualliflar/toifalar, keyin kitoblar.
FOND_TABLES = ["authors", "categories", "books", "book_copies"]

ALL_TABLES = FOND_TABLES + [
    "users",
    "readers",
    "loans",
    "reservations",
    "settings",
    "quizzes",
    "quiz_questions",
    "quiz_choices",
    "telegram_accounts",
    "quiz_assignments",
    "quiz_attempts",
    "quiz_answers",
]


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------
def sqlite_tables(con):
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def sqlite_columns(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def sqlite_count(con, table):
    try:
        return con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.Error:
        return None


def pg_columns(cur, table):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def pg_count(cur, table):
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]


def fix_sequence(cur, table):
    """COPY dan keyin id ketma-ketligini to'g'rilaydi."""
    cur.execute(
        """
        SELECT pg_get_serial_sequence(%s, 'id')
        """,
        (table,),
    )
    row = cur.fetchone()
    seq = row[0] if row else None
    if not seq:
        return
    cur.execute(
        f'SELECT setval(%s, COALESCE((SELECT MAX(id) FROM "{table}"), 1))', (seq,)
    )


# ---------------------------------------------------------------------------
# Asosiy ish
# ---------------------------------------------------------------------------
def copy_table(sqlite_con, pg_con, table, force=False):
    """Bitta jadvalni ko'chiradi. (holat, xabar) qaytaradi."""
    with pg_con.cursor() as cur:
        target_cols = pg_columns(cur, table)
        if not target_cols:
            return "skip", "serverda bunday jadval yo'q"

        source_cols = sqlite_columns(sqlite_con, table)
        if not source_cols:
            return "skip", "lokal bazada bunday jadval yo'q"

        cols = [c for c in source_cols if c in target_cols]
        if not cols:
            return "skip", "mos ustunlar topilmadi"

        existing = pg_count(cur, table)
        if existing and not force:
            return "skip", f"serverda allaqachon {existing} ta yozuv bor"
        if existing and force:
            cur.execute(f'DELETE FROM "{table}"')

        total = sqlite_count(sqlite_con, table) or 0
        if total == 0:
            return "empty", "lokal bazada yozuv yo'q"

        quoted = ", ".join(f'"{c}"' for c in cols)
        rows = sqlite_con.execute(f'SELECT {quoted} FROM "{table}"')

        sent = 0
        with cur.copy(f'COPY "{table}" ({quoted}) FROM STDIN') as copy:
            for row in rows:
                copy.write_row(row)
                sent += 1
                if sent % 500 == 0:
                    print(f"      {sent} / {total}...", flush=True)

        fix_sequence(cur, table)
    pg_con.commit()
    return "ok", f"{sent} ta yozuv ko'chirildi"


def main():
    args = sys.argv[1:]
    force = "--force" in args
    show_list = "--list" in args
    take_all = "--all" in args
    names = [a for a in args if not a.startswith("--")]

    if not os.path.exists(SQLITE_PATH):
        sys.exit(
            f"'{SQLITE_PATH}' topilmadi. Skriptni loyiha papkasida ishga tushiring."
        )

    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        sys.exit(
            "DATABASE_URL o'rnatilmagan.\n"
            '    set "DATABASE_URL=postgresql://...neon...?sslmode=require"'
        )

    sqlite_con = sqlite3.connect(SQLITE_PATH)

    if show_list:
        print("Lokal bazadagi jadvallar:\n")
        for name in sqlite_tables(sqlite_con):
            if name.startswith("sqlite_") or name.startswith("django_"):
                continue
            print(f"  {name:24} {sqlite_count(sqlite_con, name)}")
        return

    tables = names or (ALL_TABLES if take_all else FOND_TABLES)

    print("Serverga ulanmoqda...", flush=True)
    with psycopg.connect(dsn, connect_timeout=30) as pg_con:
        with pg_con.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'")
        pg_con.commit()
        print("Ulandi.\n", flush=True)

        done = skipped = failed = 0
        for table in tables:
            print(f"  {table}", flush=True)
            try:
                status, message = copy_table(sqlite_con, pg_con, table, force=force)
            except Exception as exc:
                pg_con.rollback()
                failed += 1
                print(f"      XATO: {exc}\n", flush=True)
                continue

            if status == "ok":
                done += 1
                print(f"      OK — {message}\n", flush=True)
            else:
                skipped += 1
                print(f"      o'tkazildi — {message}\n", flush=True)

        print(f"Natija: ko'chirildi {done}, o'tkazildi {skipped}, xato {failed}")

        if failed:
            print(
                "\nXato bo'lgan jadvallarni qayta urinib ko'ring. Serverdagi eski "
                "yozuvlarni almashtirmoqchi bo'lsangiz --force qo'shing."
            )

        print("\nServerdagi holat:")
        with pg_con.cursor() as cur:
            for table in tables:
                try:
                    print(f"  {table:24} {pg_count(cur, table)}")
                except Exception:
                    pg_con.rollback()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""安装后修正数据库里记录的旧路径（D:\\AI -> 新安装目录）。"""
import os
import sqlite3
import sys


def main():
    base = os.path.abspath(sys.argv[1])
    db = os.path.join(base, "data", "app.db")
    if not os.path.exists(db):
        print("no app.db, skip")
        return
    con = sqlite3.connect(db)
    try:
        cur = con.execute("UPDATE files SET path = REPLACE(path, 'D:\\AI', ?)", (base,))
        con.commit()
        print("db paths updated:", cur.rowcount)
    finally:
        con.close()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
蜗牛AI 学员门户 — 数据库管理小工具（命令行）
用法（在 server/ 目录，使用 portal 虚拟环境）：
  venv/bin/python manage.py listusers
  venv/bin/python manage.py adduser <用户名> <姓名> <角色> <密码>
  venv/bin/python manage.py deluser <用户名>
  venv/bin/python manage.py listcaps
  venv/bin/python manage.py addcap <id> <类别> <标题> <说明>
  venv/bin/python manage.py resetpw <用户名> <新密码>

角色：student（学员）| ta（助教）| instructor（总讲师）
"""
import sys
import sqlite3
import hashlib
import secrets
from pathlib import Path

DB = Path(__file__).resolve().parent / "snailai.db"


def conn():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000).hex()


def adduser(username, name, role, password):
    if role not in ("student", "ta", "instructor"):
        print("角色必须是 student / ta / instructor"); return
    salt = secrets.token_hex(16)
    c = conn()
    c.execute("INSERT OR REPLACE INTO users(username,name,role,password_hash,salt) "
              "VALUES(?,?,?,?,?)", (username, name, role, _hash(password, salt), salt))
    c.commit(); c.close()
    print(f"已添加/更新用户：{username}（{name}，{role}）")


def deluser(username):
    c = conn()
    c.execute("DELETE FROM users WHERE username=?", (username,))
    c.execute("DELETE FROM checks WHERE student_username=?", (username,))
    c.commit(); c.close()
    print(f"已删除用户及其勾选记录：{username}")


def listusers():
    c = conn()
    print(f"{'用户名':<14}{'姓名':<20}{'角色'}")
    for r in c.execute("SELECT username,name,role FROM users ORDER BY role,username"):
        print(f"{r['username']:<14}{r['name']:<20}{r['role']}")
    c.close()


def listcaps():
    c = conn()
    for r in c.execute("SELECT id,category,title FROM capabilities ORDER BY id"):
        print(f"{r['id']:<6}{r['category']:<14}{r['title']}")
    c.close()


def addcap(cid, cat, title, desc):
    c = conn()
    c.execute("INSERT OR REPLACE INTO capabilities(id,title,description,category) VALUES(?,?,?,?)",
              (cid, title, desc, cat))
    c.commit(); c.close()
    print(f"已添加/更新能力项：{cid} {title}")


def resetpw(username, password):
    c = conn()
    u = c.execute("SELECT salt FROM users WHERE username=?", (username,)).fetchone()
    if not u:
        print("用户不存在"); return
    c.execute("UPDATE users SET password_hash=? WHERE username=?",
              (_hash(password, u["salt"]), username))
    c.commit(); c.close()
    print(f"已重置 {username} 的密码")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)
    cmd = args[0]
    if cmd == "listusers":
        listusers()
    elif cmd == "adduser" and len(args) == 5:
        adduser(args[1], args[2], args[3], args[4])
    elif cmd == "deluser" and len(args) == 2:
        deluser(args[1])
    elif cmd == "listcaps":
        listcaps()
    elif cmd == "addcap" and len(args) == 5:
        addcap(args[1], args[2], args[3], args[4])
    elif cmd == "resetpw" and len(args) == 3:
        resetpw(args[1], args[2])
    else:
        print(__doc__)

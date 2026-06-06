"""
数据库模块：SQLite 表定义 + CRUD 操作
支持多群管理，所有数据按 group_id 隔离
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from config import config


def get_db_path() -> Path:
    config.ensure_dirs()
    return config.DATABASE_PATH


def get_conn() -> sqlite3.Connection:
    """获取数据库连接（启用 WAL 模式 + 外键）"""
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化所有表"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            display_name TEXT,
            wxid TEXT,
            message_count INTEGER DEFAULT 0,
            sender_count INTEGER DEFAULT 0,
            date_range_start TEXT,
            date_range_end TEXT,
            analyzed_days INTEGER DEFAULT 0,
            file_path TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_id INTEGER,
            wxid TEXT,
            display_name TEXT,
            nickname TEXT,
            remark TEXT,
            group_nickname TEXT,
            avatar TEXT,
            message_count INTEGER DEFAULT 0,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            active_members INTEGER DEFAULT 0,
            report_json TEXT,
            model_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, date),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS member_portraits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            display_name TEXT,
            total_analyzed_messages INTEGER DEFAULT 0,
            portrait_json TEXT,
            data_start_date TEXT,
            data_end_date TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, member_id),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS analysis_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            date TEXT,
            analysis_type TEXT,
            status TEXT,
            model_used TEXT,
            duration_ms INTEGER,
            error_msg TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 向后兼容：为已有数据库添加新列
    _migrate_db(conn)
    conn.commit()
    conn.close()


def _migrate_db(conn):
    """数据库迁移：为旧版本表结构添加新列"""
    # 检查 member_portraits 是否已有 data_start_date 列
    cur = conn.execute("PRAGMA table_info(member_portraits)")
    cols = {row[1] for row in cur.fetchall()}
    if "data_start_date" not in cols:
        conn.execute("ALTER TABLE member_portraits ADD COLUMN data_start_date TEXT")
    if "data_end_date" not in cols:
        conn.execute("ALTER TABLE member_portraits ADD COLUMN data_end_date TEXT")


# ==================== 群管理 CRUD ====================

def create_group(name: str, wxid: str = "", display_name: str = "",
                 message_count: int = 0, sender_count: int = 0,
                 date_start: str = "", date_end: str = "",
                 file_path: str = "") -> int:
    """创建群记录，返回 group_id"""
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO chat_groups (name, display_name, wxid, message_count,
           sender_count, date_range_start, date_range_end, file_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, display_name, wxid, message_count, sender_count,
         date_start, date_end, file_path)
    )
    conn.commit()
    gid = cur.lastrowid
    conn.close()
    return gid


def list_groups() -> list[dict]:
    """列出所有活跃的群"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chat_groups WHERE status='active' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_group(group_id: int) -> dict | None:
    """获取单个群信息"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM chat_groups WHERE id=?", (group_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_group(group_id: int):
    """删除群及其所有关联数据（CASCADE）"""
    conn = get_conn()
    conn.execute("DELETE FROM chat_groups WHERE id=?", (group_id,))
    conn.commit()
    conn.close()


def update_group_stats(group_id: int, analyzed_days: int):
    """更新已分析天数"""
    conn = get_conn()
    conn.execute(
        "UPDATE chat_groups SET analyzed_days=? WHERE id=?",
        (analyzed_days, group_id)
    )
    conn.commit()
    conn.close()


# ==================== 成员 CRUD ====================

def upsert_members(group_id: int, senders: list[dict]):
    """批量写入群成员（INSERT OR REPLACE）"""
    conn = get_conn()
    for s in senders:
        conn.execute(
            """INSERT OR REPLACE INTO group_members
               (group_id, sender_id, wxid, display_name, nickname, remark,
                group_nickname, avatar)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (group_id,
             s.get("senderID"),
             s.get("wxid", ""),
             s.get("displayName", ""),
             s.get("nickname", ""),
             s.get("remark", ""),
             s.get("groupNickname", ""),
             s.get("avatar", ""))
        )
    conn.commit()
    conn.close()


def get_members(group_id: int) -> list[dict]:
    """获取群成员列表，按消息数降序"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM group_members WHERE group_id=? ORDER BY message_count DESC",
        (group_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member(group_id: int, member_id: int) -> dict | None:
    """获取单个成员"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM group_members WHERE group_id=? AND id=?",
        (group_id, member_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_member_by_sender_id(group_id: int, sender_id: int) -> dict | None:
    """通过原始 senderID 获取成员"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM group_members WHERE group_id=? AND sender_id=?",
        (group_id, sender_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_member_message_count(group_id: int, sender_id: int, count: int):
    """更新成员消息计数"""
    conn = get_conn()
    conn.execute(
        "UPDATE group_members SET message_count=? WHERE group_id=? AND sender_id=?",
        (count, group_id, sender_id)
    )
    conn.commit()
    conn.close()


# ==================== 每日报告 CRUD ====================

def save_daily_report(group_id: int, date: str, message_count: int,
                       active_members: int, report_json: str,
                       model_used: str):
    """保存每日报告（INSERT OR REPLACE）"""
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO daily_reports
           (group_id, date, message_count, active_members, report_json, model_used)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (group_id, date, message_count, active_members, report_json, model_used)
    )
    conn.commit()
    conn.close()


def get_daily_report(group_id: int, date: str) -> dict | None:
    """获取某天的报告"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM daily_reports WHERE group_id=? AND date=?",
        (group_id, date)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_analyzed_dates(group_id: int) -> list[str]:
    """获取已分析的日期列表"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT date FROM daily_reports WHERE group_id=? ORDER BY date DESC",
        (group_id,)
    ).fetchall()
    conn.close()
    return [r["date"] for r in rows]


def get_recent_reports(group_id: int, limit: int = 7) -> list[dict]:
    """获取最近的报告摘要"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT date, message_count, active_members, report_json, model_used, created_at
           FROM daily_reports WHERE group_id=?
           ORDER BY date DESC LIMIT ?""",
        (group_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 群友画像 CRUD ====================

def save_member_portrait(group_id: int, member_id: int, display_name: str,
                          total_messages: int, portrait_json: str,
                          data_start: str = "", data_end: str = ""):
    """保存成员画像"""
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO member_portraits
           (group_id, member_id, display_name, total_analyzed_messages,
            portrait_json, data_start_date, data_end_date, last_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (group_id, member_id, display_name, total_messages,
         portrait_json, data_start, data_end, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_portraits(group_id: int) -> list[dict]:
    """获取群所有成员画像"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM member_portraits WHERE group_id=?",
        (group_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_portrait(group_id: int, member_id: int) -> dict | None:
    """获取单个成员画像"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM member_portraits WHERE group_id=? AND member_id=?",
        (group_id, member_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_stale_portraits(group_id: int, refresh_days: int) -> list[dict]:
    """获取需要刷新的画像（累积新消息 >= refresh_days 天）"""
    conn = get_conn()
    # 画像的 total_analyzed_messages 小于成员实际 message_count 超过阈值
    rows = conn.execute(
        """SELECT mp.*, gm.message_count as current_count
           FROM member_portraits mp
           JOIN group_members gm ON mp.member_id = gm.id AND mp.group_id = gm.group_id
           WHERE mp.group_id=? AND (gm.message_count - mp.total_analyzed_messages) >= ?""",
        (group_id, refresh_days * 50)  # 粗略估计：每天至少50条新消息
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 分析日志 ====================

def log_analysis(group_id: int, date: str, analysis_type: str,
                 status: str, model_used: str = "",
                 duration_ms: int = 0, error_msg: str = ""):
    """记录分析任务日志"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO analysis_log
           (group_id, date, analysis_type, status, model_used, duration_ms, error_msg)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (group_id, date, analysis_type, status, model_used, duration_ms, error_msg)
    )
    conn.commit()
    conn.close()


def get_group_dates(group_id: int) -> list[str]:
    """获取某个群有消息的日期列表（从 analysis_log 推断或外部传入）"""
    # 日期信息存储在 daily_reports 中（已分析过），也可以外部提供所有日期
    conn = get_conn()
    rows = conn.execute(
        "SELECT date_range_start, date_range_end FROM chat_groups WHERE id=?",
        (group_id,)
    ).fetchone()
    conn.close()
    return dict(rows) if rows else None

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


def cleanup_old_logs(retention_days: int = 90, max_records: int = 500):
    """清理过期的分析日志和任务记录

    Args:
        retention_days: 保留最近 N 天的记录
        max_records: 每个表最多保留的记录数
    """
    try:
        conn = get_conn()
        # 清理分析日志
        conn.execute(
            "DELETE FROM analysis_log WHERE created_at < datetime('now', ?)",
            (f'-{retention_days} days',)
        )
        # 保留最近 max_records 条任务记录
        conn.execute("""
            DELETE FROM task_records WHERE id NOT IN (
                SELECT id FROM task_records ORDER BY created_at DESC LIMIT ?
            )
        """, (max_records,))
        conn.commit()
        conn.close()
    except Exception:
        pass  # 清理失败不影响主流程


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
            wxid TEXT NOT NULL DEFAULT '',
            display_name TEXT,
            nickname TEXT,
            remark TEXT,
            group_nickname TEXT,
            avatar TEXT,
            message_count INTEGER DEFAULT 0,
            UNIQUE(group_id, wxid),
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

        CREATE TABLE IF NOT EXISTS portrait_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            portrait_json TEXT,
            analyzed_msg_count INTEGER DEFAULT 0,
            data_start_date TEXT,
            data_end_date TEXT,
            model_used TEXT,
            duration_ms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS member_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            member_a_id INTEGER NOT NULL,
            member_b_id INTEGER NOT NULL,
            co_msg_count INTEGER DEFAULT 0,
            reply_count INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, member_a_id, member_b_id),
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

        CREATE TABLE IF NOT EXISTS task_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            group_id INTEGER,
            task_type TEXT,
            target TEXT,
            status TEXT,
            total_duration_ms INTEGER DEFAULT 0,
            model_used TEXT,
            steps_json TEXT,
            error_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 向后兼容：为已有数据库添加新列
    _migrate_db(conn)
    conn.commit()
    conn.close()
    # 清理过期日志（不阻塞启动）
    cleanup_old_logs()


def _migrate_db(conn):
    """数据库迁移：为旧版本表结构添加新列和索引"""
    # member_portraits 新列
    cur = conn.execute("PRAGMA table_info(member_portraits)")
    cols = {row[1] for row in cur.fetchall()}
    if "data_start_date" not in cols:
        conn.execute("ALTER TABLE member_portraits ADD COLUMN data_start_date TEXT")
    if "data_end_date" not in cols:
        conn.execute("ALTER TABLE member_portraits ADD COLUMN data_end_date TEXT")

    # group_members v0.5 迁移：唯一键从 sender_id 改为 wxid
    cur = conn.execute("PRAGMA index_list(group_members)")
    indexes = {row[1] for row in cur.fetchall()}
    has_wxid_index = any("wxid" in idx for idx in indexes)
    has_sender_index = any("sender_id" in idx for idx in indexes)

    if not has_wxid_index:
        # 1. 确保 wxid 列有值（旧数据可能为空）
        conn.execute("""
            UPDATE group_members SET wxid = 'fallback_' || sender_id
            WHERE wxid IS NULL OR wxid = ''
        """)
        # 2. 修复 member_portraits 外键：指向保留的 member
        fixed_rows = conn.execute("""
            UPDATE member_portraits SET member_id = (
                SELECT MAX(gm2.id) FROM group_members gm2
                WHERE gm2.group_id = member_portraits.group_id
                  AND gm2.wxid = (
                    SELECT gm.wxid FROM group_members gm
                    WHERE gm.id = member_portraits.member_id
                  )
            )
            WHERE member_id NOT IN (
                SELECT MAX(gm3.id) FROM group_members gm3
                GROUP BY gm3.group_id, gm3.wxid
            )
            AND EXISTS (
                SELECT 1 FROM group_members gm
                WHERE gm.id = member_portraits.member_id
                  AND gm.wxid IS NOT NULL AND gm.wxid != ''
            )
        """).rowcount
        # 无法修复的孤儿画像直接删除
        deleted = conn.execute("""
            DELETE FROM member_portraits
            WHERE member_id NOT IN (SELECT id FROM group_members)
        """).rowcount
        if fixed_rows or deleted:
            pass  # 静默处理
        # 3. 清理重复：按 wxid 去重，保留 id 最大的
        conn.execute("""
            DELETE FROM group_members WHERE id NOT IN (
                SELECT MAX(id) FROM group_members
                WHERE wxid IS NOT NULL AND wxid != ''
                GROUP BY group_id, wxid
            )
        """)
        # 4. 删旧索引 + 建 wxid 新索引
        if has_sender_index:
            for idx_name in indexes:
                if "sender_id" in idx_name:
                    conn.execute(f"DROP INDEX IF EXISTS {idx_name}")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_group_members_wxid "
            "ON group_members(group_id, wxid)"
        )


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
    """批量写入群成员：按 wxid 去重，新成员插入，已有成员更新非空字段

    wxid 是微信账号的稳定标识，不会因重新导出而改变。
    sender_id 是导出工具临时编号，仅用于匹配消息。
    """
    conn = get_conn()
    for s in senders:
        sender_id = s.get("senderID", 0)
        wxid = s.get("wxid", "") or f"fallback_{sender_id}"
        display_name = s.get("displayName", "")
        nickname = s.get("nickname", "")
        remark = s.get("remark", "")
        group_nickname = s.get("groupNickname", "")
        avatar = s.get("avatar", "")

        conn.execute(
            """INSERT INTO group_members
               (group_id, sender_id, wxid, display_name, nickname, remark,
                group_nickname, avatar)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(group_id, wxid) DO UPDATE SET
               sender_id = excluded.sender_id,
               display_name = COALESCE(NULLIF(excluded.display_name, ''), display_name),
               nickname = COALESCE(NULLIF(excluded.nickname, ''), nickname),
               remark = COALESCE(NULLIF(excluded.remark, ''), remark),
               group_nickname = COALESCE(NULLIF(excluded.group_nickname, ''), group_nickname),
               avatar = COALESCE(NULLIF(excluded.avatar, ''), avatar)""",
            (group_id, sender_id, wxid, display_name, nickname, remark,
             group_nickname, avatar)
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


def update_member_message_count(group_id: int, wxid: str, count: int):
    """更新成员消息计数（按 wxid）"""
    conn = get_conn()
    conn.execute(
        "UPDATE group_members SET message_count=? WHERE group_id=? AND wxid=?",
        (count, group_id, wxid)
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


# ==================== 画像版本历史 ====================

def save_portrait_version(group_id: int, member_id: int, version: int,
                           portrait_json: str, analyzed_msg_count: int = 0,
                           data_start: str = "", data_end: str = "",
                           model_used: str = "", duration_ms: int = 0):
    """保存画像的历史版本"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO portrait_versions
           (group_id, member_id, version, portrait_json, analyzed_msg_count,
            data_start_date, data_end_date, model_used, duration_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (group_id, member_id, version, portrait_json, analyzed_msg_count,
         data_start, data_end, model_used, duration_ms)
    )
    conn.commit()
    conn.close()


def get_portrait_versions(group_id: int, member_id: int) -> list[dict]:
    """获取成员的画像版本历史（最新在前）"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM portrait_versions
           WHERE group_id=? AND member_id=?
           ORDER BY version DESC""",
        (group_id, member_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_portrait_version(group_id: int, member_id: int) -> int:
    """获取成员画像的最新版本号，从未有过则返回 0"""
    conn = get_conn()
    row = conn.execute(
        """SELECT MAX(version) as max_v FROM portrait_versions
           WHERE group_id=? AND member_id=?""",
        (group_id, member_id)
    ).fetchone()
    conn.close()
    return row["max_v"] or 0


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
    """获取某个群有消息的日期列表"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT date_range_start, date_range_end FROM chat_groups WHERE id=?",
        (group_id,)
    ).fetchone()
    conn.close()
    return dict(rows) if rows else None


# ==================== 任务记录 CRUD ====================

def save_task_record(task_id: str, group_id: int, task_type: str, target: str,
                     status: str, total_duration_ms: int, model_used: str = "",
                     steps_json: str = "", error_summary: str = ""):
    """保存任务执行记录"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO task_records (task_id, group_id, task_type, target, status,
           total_duration_ms, model_used, steps_json, error_summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, group_id, task_type, target, status,
         total_duration_ms, model_used, steps_json, error_summary)
    )
    conn.commit()
    conn.close()


def get_task_history(group_id: int = None, limit: int = 20) -> list[dict]:
    """查询任务历史"""
    conn = get_conn()
    if group_id:
        rows = conn.execute(
            "SELECT * FROM task_records WHERE group_id=? ORDER BY created_at DESC LIMIT ?",
            (group_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM task_records ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task_record(task_id: str) -> dict | None:
    """查询单个任务记录"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM task_records WHERE task_id=?", (task_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

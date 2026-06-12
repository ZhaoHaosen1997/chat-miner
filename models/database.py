"""
数据库模块：SQLite 表定义 + CRUD 操作
支持多群管理，所有数据按 group_id 隔离
"""
import sqlite3
import json
from collections import defaultdict
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
    conn = None
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
    except Exception:
        pass  # 清理失败不影响主流程
    finally:
        if conn:
            conn.close()


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

        CREATE TABLE IF NOT EXISTS periodic_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            report_type TEXT NOT NULL,
            period_key TEXT NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            day_count INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            active_members INTEGER DEFAULT 0,
            report_json TEXT NOT NULL,
            model_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, report_type, period_key),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        -- v0.9 群鱼塘
        CREATE TABLE IF NOT EXISTS fish_pond (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            wxid TEXT NOT NULL DEFAULT '',
            fish_name TEXT,
            species TEXT NOT NULL,
            rarity TEXT NOT NULL DEFAULT '普通',
            -- D&D 六维 (稀有度基准 6/8/10/12 + 随机 ±2 + 种族 ASI)
            strength INTEGER NOT NULL DEFAULT 10,
            dexterity INTEGER NOT NULL DEFAULT 10,
            constitution INTEGER NOT NULL DEFAULT 10,
            intelligence INTEGER NOT NULL DEFAULT 10,
            wisdom INTEGER NOT NULL DEFAULT 10,
            charisma INTEGER NOT NULL DEFAULT 10,
            -- 经验与等级
            experience INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            -- 鱼状态
            growth REAL NOT NULL DEFAULT 0,
            happiness REAL NOT NULL DEFAULT 50,
            hp INTEGER NOT NULL DEFAULT 20,
            stage TEXT NOT NULL DEFAULT '鱼苗',
            -- 活跃追踪
            consecutive_days INTEGER DEFAULT 0,
            last_active_date TEXT,
            last_fed_date TEXT,
            -- 生死标记
            is_alive INTEGER NOT NULL DEFAULT 1,
            -- 时间戳
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, wxid),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS fish_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            wxid TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,
            event_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scale_coin_wallet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            wxid TEXT NOT NULL DEFAULT '',
            balance INTEGER NOT NULL DEFAULT 0,
            total_earned INTEGER NOT NULL DEFAULT 0,
            total_spent INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, wxid),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scale_coin_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            wxid TEXT NOT NULL DEFAULT '',
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        -- v0.9.3 道具库存
        CREATE TABLE IF NOT EXISTS fish_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            wxid TEXT NOT NULL DEFAULT '',
            item_key TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, wxid, item_key),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );

        -- v0.9.3 黑市
        CREATE TABLE IF NOT EXISTS fish_black_market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            item_key TEXT NOT NULL,
            price INTEGER NOT NULL,
            stock INTEGER NOT NULL DEFAULT 1,
            stock_remaining INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, date, item_key),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );
    """)
    # v0.12.0: 模型配置
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS model_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            model_type TEXT NOT NULL DEFAULT 'local',
            endpoint TEXT NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            extra_params TEXT DEFAULT '',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    _seed_model_configs_from_env(conn)
    # v0.11.0: 年度奖项
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS annual_awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            award_name TEXT NOT NULL,
            award_reason TEXT,
            award_emoji TEXT DEFAULT '🏆',
            ceremony_version INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (member_id) REFERENCES group_members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_annual_awards_group_year
            ON annual_awards(group_id, year);
        CREATE INDEX IF NOT EXISTS idx_annual_awards_member
            ON annual_awards(member_id);
    """)
    # 向后兼容：为已有数据库添加新列
    _migrate_db(conn)
    # v0.13.1: portrait_versions 唯一约束（防版本号重复）
    cur = conn.execute("PRAGMA index_list(portrait_versions)")
    indexes = {row[1] for row in cur.fetchall()}
    has_version_unique = any("version" in idx for idx in indexes)
    if not has_version_unique:
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_portrait_versions_unique "
                "ON portrait_versions(group_id, member_id, version)"
            )
        except Exception:
            pass  # 已存在则跳过
    # v0.9.3: 装备栏
    cur = conn.execute("PRAGMA table_info(fish_pond)")
    cols = {row[1] for row in cur.fetchall()}
    if "equipped_item" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN equipped_item TEXT DEFAULT ''")
    if "active_consumable" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN active_consumable TEXT DEFAULT ''")
    conn.commit()
    conn.close()
    # 清理过期日志（不阻塞启动）
    cleanup_old_logs()


def _seed_model_configs_from_env(conn):
    """首次启动时，如果 model_configs 为空，从 .env 播种默认模型配置"""
    count = conn.execute("SELECT COUNT(*) FROM model_configs").fetchone()[0]
    if count > 0:
        return  # 已有配置，不覆盖

    # 播种 Ollama 本地默认模型
    conn.execute(
        """INSERT INTO model_configs (name, model_type, endpoint, model_name, is_default)
           VALUES (?, 'local', ?, ?, 1)""",
        ("Ollama (env)", config.OLLAMA_HOST, config.OLLAMA_MODEL)
    )

    # 如果配置了 DeepSeek API Key，播种在线默认模型
    if config.DEEPSEEK_API_KEY:
        conn.execute(
            """INSERT INTO model_configs (name, model_type, endpoint, api_key, model_name, is_default)
               VALUES (?, 'online', ?, ?, ?, 1)""",
            ("DeepSeek (env)", config.DEEPSEEK_API_URL, config.DEEPSEEK_API_KEY, config.DEEPSEEK_MODEL)
        )
    conn.commit()


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

    # v0.9 群鱼塘迁移：检查新表是否存在
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fish_pond'"
    )
    if not cur.fetchone():
        # 表不存在时会由 init_db 创建，这里处理已有数据库升级
        pass  # init_db 使用 CREATE TABLE IF NOT EXISTS，自动处理


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
    """获取群成员列表，按消息数降序（排除群自身）"""
    conn = get_conn()
    # 获取群的 wxid，用于排除群自身的 sender 条目
    group = conn.execute("SELECT wxid FROM chat_groups WHERE id=?", (group_id,)).fetchone()
    group_wxid = group["wxid"] if group else None
    if group_wxid:
        rows = conn.execute(
            "SELECT * FROM group_members WHERE group_id=? AND wxid!=? ORDER BY message_count DESC",
            (group_id, group_wxid)
        ).fetchall()
    else:
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


def get_daily_reports_batch(group_id: int, dates: list[str]) -> list[dict]:
    """批量获取多天的报告（单次连接，避免逐条打开阻塞事件循环）"""
    if not dates:
        return []
    conn = get_conn()
    placeholders = ",".join("?" * len(dates))
    rows = conn.execute(
        f"""SELECT * FROM daily_reports
            WHERE group_id=? AND date IN ({placeholders})
            ORDER BY date""",
        (group_id, *dates)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


# ==================== 周期报告（周报/月报）CRUD ====================

def save_periodic_report(group_id: int, report_type: str, period_key: str,
                          date_start: str, date_end: str, day_count: int,
                          total_messages: int, active_members: int,
                          report_json: str, model_used: str = ""):
    """保存周报/月报（INSERT OR REPLACE）"""
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO periodic_reports
           (group_id, report_type, period_key, date_start, date_end,
            day_count, total_messages, active_members, report_json, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (group_id, report_type, period_key, date_start, date_end,
         day_count, total_messages, active_members, report_json, model_used)
    )
    conn.commit()
    conn.close()


def get_periodic_report(group_id: int, report_type: str,
                        period_key: str) -> dict | None:
    """获取单个周期报告"""
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM periodic_reports
           WHERE group_id=? AND report_type=? AND period_key=?""",
        (group_id, report_type, period_key)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_periodic_reports(group_id: int, report_type: str = "") -> list[dict]:
    """列出群的所有周期报告，按 period_key 倒序"""
    conn = get_conn()
    if report_type:
        rows = conn.execute(
            """SELECT * FROM periodic_reports
               WHERE group_id=? AND report_type=?
               ORDER BY period_key DESC""",
            (group_id, report_type)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM periodic_reports
               WHERE group_id=?
               ORDER BY period_key DESC""",
            (group_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_periodic_report(group_id: int, report_type: str,
                           period_key: str) -> bool:
    """删除周期报告，返回是否成功删除"""
    conn = get_conn()
    cur = conn.execute(
        """DELETE FROM periodic_reports
           WHERE group_id=? AND report_type=? AND period_key=?""",
        (group_id, report_type, period_key)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ==================== 年度奖项 v0.11 CRUD ====================

def save_annual_awards(group_id: int, year: int, awards: list[dict],
                        ceremony_version: int = 1):
    """保存年度奖项列表。先删旧奖项再批量插入"""
    conn = get_conn()
    conn.execute(
        "DELETE FROM annual_awards WHERE group_id=? AND year=?",
        (group_id, year)
    )
    for a in awards:
        conn.execute(
            """INSERT INTO annual_awards
               (group_id, year, member_id, award_name, award_reason,
                award_emoji, ceremony_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (group_id, year, a["member_id"], a["award_name"],
             a.get("award_reason", ""), a.get("award_emoji", "🏆"),
             ceremony_version)
        )
    conn.commit()
    conn.close()


def get_annual_awards(group_id: int, year: int) -> list[dict]:
    """获取某群某年的所有奖项"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT aa.*, gm.display_name, gm.wxid
           FROM annual_awards aa
           LEFT JOIN group_members gm ON aa.member_id = gm.id
           WHERE aa.group_id=? AND aa.year=?
           ORDER BY aa.id""",
        (group_id, year)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member_awards(group_id: int, member_id: int) -> list[dict]:
    """获取某成员的所有年份奖项"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM annual_awards
           WHERE group_id=? AND member_id=?
           ORDER BY year DESC, id""",
        (group_id, member_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member_awards_batch(group_id: int, member_ids: list[int]) -> dict[int, list[dict]]:
    """批量获取多个成员的奖项，返回 {member_id: [award_dict, ...]}"""
    if not member_ids:
        return {}
    conn = get_conn()
    placeholders = ','.join('?' * len(member_ids))
    rows = conn.execute(
        f"""SELECT * FROM annual_awards
            WHERE group_id=? AND member_id IN ({placeholders})
            ORDER BY member_id, year DESC, id""",
        [group_id] + member_ids
    ).fetchall()
    conn.close()
    result = defaultdict(list)
    for r in rows:
        result[r["member_id"]].append(dict(r))
    return dict(result)


def delete_annual_awards(group_id: int, year: int) -> bool:
    """删除某群某年的所有奖项"""
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM annual_awards WHERE group_id=? AND year=?",
        (group_id, year)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ==================== 群鱼塘 v0.9 CRUD ====================

def upsert_fish(group_id: int, wxid: str, fish_name: str, species: str,
                rarity: str, strength: int, dexterity: int, constitution: int,
                intelligence: int, wisdom: int, charisma: int,
                experience: int = 0, level: int = 1,
                growth: float = 0, happiness: float = 50, hp: int = 20,
                stage: str = "鱼苗", consecutive_days: int = 0,
                last_active_date: str = "", last_fed_date: str = "",
                is_alive: int = 1) -> int:
    """创建或更新鱼（按 group_id + wxid 唯一键）"""
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO fish_pond
           (group_id, wxid, fish_name, species, rarity,
            strength, dexterity, constitution, intelligence, wisdom, charisma,
            experience, level, growth, happiness, hp, stage,
            consecutive_days, last_active_date, last_fed_date, is_alive, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(group_id, wxid) DO UPDATE SET
           fish_name = excluded.fish_name,
           species = excluded.species,
           rarity = excluded.rarity,
           strength = excluded.strength,
           dexterity = excluded.dexterity,
           constitution = excluded.constitution,
           intelligence = excluded.intelligence,
           wisdom = excluded.wisdom,
           charisma = excluded.charisma,
           experience = excluded.experience,
           level = excluded.level,
           growth = excluded.growth,
           happiness = excluded.happiness,
           hp = excluded.hp,
           stage = excluded.stage,
           consecutive_days = excluded.consecutive_days,
           last_active_date = excluded.last_active_date,
           last_fed_date = excluded.last_fed_date,
           is_alive = excluded.is_alive,
           updated_at = datetime('now')""",
        (group_id, wxid, fish_name, species, rarity,
         strength, dexterity, constitution, intelligence, wisdom, charisma,
         experience, level, growth, happiness, hp, stage,
         consecutive_days, last_active_date, last_fed_date, is_alive)
    )
    conn.commit()
    fid = cur.lastrowid
    conn.close()
    return fid


def get_fish(group_id: int, wxid: str) -> dict | None:
    """获取单条鱼"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM fish_pond WHERE group_id=? AND wxid=?",
        (group_id, wxid)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_fish(group_id: int) -> list[dict]:
    """获取群所有鱼（存活优先，按成长值降序）"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM fish_pond WHERE group_id=?
           ORDER BY is_alive DESC, growth DESC""",
        (group_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alive_fish(group_id: int) -> list[dict]:
    """获取所有存活的鱼"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM fish_pond WHERE group_id=? AND is_alive=1
           ORDER BY growth DESC""",
        (group_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_fish_dead(group_id: int, wxid: str) -> bool:
    """标记鱼死亡（鲨鱼事件），保留历史数据"""
    conn = get_conn()
    conn.execute(
        """UPDATE fish_pond SET is_alive=0, updated_at=datetime('now')
           WHERE group_id=? AND wxid=?""",
        (group_id, wxid)
    )
    conn.commit()
    conn.close()
    return True


# v0.13.0: 白名单校验，防止 SQL 注入
_FISH_FIELD_WHITELIST = {
    "fish_name", "species", "rarity",
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
    "experience", "level", "growth", "happiness", "hp", "stage",
    "consecutive_days", "last_active_date", "last_fed_date", "is_alive",
    "equipped_item", "active_consumable",
}


def update_fish_field(group_id: int, wxid: str, field: str, value):
    """更新鱼的单字段（白名单校验防注入）"""
    if field not in _FISH_FIELD_WHITELIST:
        raise ValueError(f"非法字段名: {field}")
    conn = get_conn()
    conn.execute(
        f"""UPDATE fish_pond SET {field}=?, updated_at=datetime('now')
            WHERE group_id=? AND wxid=?""",
        (value, group_id, wxid)
    )
    conn.commit()
    conn.close()


def update_fish_multi(group_id: int, wxid: str, updates: dict):
    """更新鱼的多个字段"""
    if not updates:
        return
    conn = get_conn()
    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values())
    conn.execute(
        f"UPDATE fish_pond SET {sets}, updated_at=datetime('now') "
        f"WHERE group_id=? AND wxid=?",
        (*values, group_id, wxid)
    )
    conn.commit()
    conn.close()


# ==================== 鱼塘事件 CRUD ====================

def add_fish_event(group_id: int, wxid: str, event_type: str,
                   event_data: dict = None) -> int:
    """记录鱼塘事件"""
    import json
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO fish_events (group_id, wxid, event_type, event_data)
           VALUES (?, ?, ?, ?)""",
        (group_id, wxid, event_type,
         json.dumps(event_data, ensure_ascii=False) if event_data else "")
    )
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return eid


def get_fish_events(group_id: int, wxid: str = "", limit: int = 20) -> list[dict]:
    """获取鱼塘事件列表"""
    conn = get_conn()
    if wxid:
        rows = conn.execute(
            """SELECT * FROM fish_events WHERE group_id=? AND wxid=?
               ORDER BY created_at DESC LIMIT ?""",
            (group_id, wxid, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM fish_events WHERE group_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (group_id, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 鳞币 CRUD ====================

def get_coin_wallet(group_id: int, wxid: str) -> dict:
    """获取鳞币钱包，不存在则返回默认值"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM scale_coin_wallet WHERE group_id=? AND wxid=?",
        (group_id, wxid)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"group_id": group_id, "wxid": wxid, "balance": 0,
            "total_earned": 0, "total_spent": 0}


def ensure_coin_wallet(group_id: int, wxid: str) -> dict:
    """确保钱包存在，不存在则创建"""
    conn = get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO scale_coin_wallet (group_id, wxid)
           VALUES (?, ?)""",
        (group_id, wxid)
    )
    conn.commit()
    conn.close()
    return get_coin_wallet(group_id, wxid)


def earn_coins(group_id: int, wxid: str, amount: int,
               reason: str, description: str = "") -> dict:
    """获得鳞币（v0.13.1: 加事务保护）"""
    ensure_coin_wallet(group_id, wxid)
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """UPDATE scale_coin_wallet
               SET balance = balance + ?, total_earned = total_earned + ?,
                   updated_at = datetime('now')
               WHERE group_id=? AND wxid=?""",
            (amount, amount, group_id, wxid)
        )
        # 流水
        conn.execute(
            """INSERT INTO scale_coin_transactions (group_id, wxid, amount, reason, description)
               VALUES (?, ?, ?, ?, ?)""",
            (group_id, wxid, amount, reason, description)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_coin_wallet(group_id, wxid)


def spend_coins(group_id: int, wxid: str, amount: int,
                reason: str, description: str = "") -> dict | None:
    """消费鳞币，余额不足返回 None（v0.13.1: 加事务保护）"""
    wallet = ensure_coin_wallet(group_id, wxid)
    if wallet["balance"] < amount:
        return None
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """UPDATE scale_coin_wallet
               SET balance = balance - ?, total_spent = total_spent + ?,
                   updated_at = datetime('now')
               WHERE group_id=? AND wxid=?""",
            (amount, amount, group_id, wxid)
        )
        conn.execute(
            """INSERT INTO scale_coin_transactions (group_id, wxid, amount, reason, description)
               VALUES (?, ?, ?, ?, ?)""",
            (group_id, wxid, -amount, reason, description)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_coin_wallet(group_id, wxid)


def get_coin_transactions(group_id: int, wxid: str, limit: int = 20) -> list[dict]:
    """获取鳞币流水"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM scale_coin_transactions
           WHERE group_id=? AND wxid=?
           ORDER BY created_at DESC LIMIT ?""",
        (group_id, wxid, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_coin_leaderboard(group_id: int, limit: int = 10) -> list[dict]:
    """鳞币排行榜"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM scale_coin_wallet WHERE group_id=?
           ORDER BY balance DESC LIMIT ?""",
        (group_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 道具库存 v0.9.3 CRUD ====================

def get_inventory(group_id: int, wxid: str) -> list[dict]:
    """获取库存"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM fish_inventory WHERE group_id=? AND wxid=? AND quantity > 0",
        (group_id, wxid)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_item(group_id: int, wxid: str, item_key: str, qty: int = 1):
    """添加道具到库存"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO fish_inventory (group_id, wxid, item_key, quantity)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(group_id, wxid, item_key) DO UPDATE SET
           quantity = quantity + excluded.quantity""",
        (group_id, wxid, item_key, qty)
    )
    conn.commit()
    conn.close()


def remove_item(group_id: int, wxid: str, item_key: str, qty: int = 1) -> bool:
    """从库存移除道具，返回是否成功"""
    conn = get_conn()
    row = conn.execute(
        "SELECT quantity FROM fish_inventory WHERE group_id=? AND wxid=? AND item_key=?",
        (group_id, wxid, item_key)
    ).fetchone()
    if not row or row["quantity"] < qty:
        conn.close()
        return False
    new_qty = row["quantity"] - qty
    if new_qty <= 0:
        conn.execute(
            "DELETE FROM fish_inventory WHERE group_id=? AND wxid=? AND item_key=?",
            (group_id, wxid, item_key)
        )
    else:
        conn.execute(
            "UPDATE fish_inventory SET quantity=? WHERE group_id=? AND wxid=? AND item_key=?",
            (new_qty, group_id, wxid, item_key)
        )
    conn.commit()
    conn.close()
    return True


# ==================== 黑市 v0.9.3 CRUD ====================

def set_black_market(group_id: int, date: str, items: list[dict]):
    """设置某天黑市商品"""
    conn = get_conn()
    conn.execute("DELETE FROM fish_black_market WHERE group_id=? AND date=?",
                 (group_id, date))
    for item in items:
        conn.execute(
            """INSERT INTO fish_black_market (group_id, date, item_key, price, stock, stock_remaining)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (group_id, date, item["key"], item["price"], item["stock"], item["stock"])
        )
    conn.commit()
    conn.close()


def get_black_market(group_id: int, date: str) -> list[dict]:
    """获取某天黑市商品"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM fish_black_market WHERE group_id=? AND date=? AND stock_remaining > 0",
        (group_id, date)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buy_from_market(group_id: int, wxid: str, date: str,
                    item_key: str) -> dict | None:
    """从黑市购买，返回商品信息或 None"""
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM fish_black_market
           WHERE group_id=? AND date=? AND item_key=? AND stock_remaining > 0""",
        (group_id, date, item_key)
    ).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute(
        """UPDATE fish_black_market SET stock_remaining = stock_remaining - 1
           WHERE id=?""", (row["id"],)
    )
    conn.commit()
    conn.close()
    return dict(row)


# ==================== 模型配置 CRUD v0.12.0 ====================

def list_model_configs() -> list[dict]:
    """列出所有模型配置，按 model_type + is_default desc 排序"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM model_configs ORDER BY model_type, is_default DESC, id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_model_config(config_id: int) -> dict | None:
    """获取单个模型配置"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM model_configs WHERE id=?", (config_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_model_config(name: str, model_type: str, endpoint: str = "",
                        api_key: str = "", model_name: str = "",
                        is_default: bool = False, extra_params: str = "") -> int:
    """创建模型配置，返回新 ID。若 is_default=True，先清除同类型其他默认"""
    conn = get_conn()
    if is_default:
        conn.execute(
            "UPDATE model_configs SET is_default=0, updated_at=CURRENT_TIMESTAMP "
            "WHERE model_type=? AND is_default=1", (model_type,)
        )
    cur = conn.execute(
        """INSERT INTO model_configs (name, model_type, endpoint, api_key, model_name, is_default, extra_params)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, model_type, endpoint, api_key, model_name, 1 if is_default else 0, extra_params)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_model_config(config_id: int, **kwargs) -> bool:
    """部分更新模型配置。自动维护 is_default 唯一性"""
    allowed = {"name", "model_type", "endpoint", "api_key", "model_name",
               "is_default", "extra_params", "is_enabled"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return False

    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM model_configs WHERE id=?", (config_id,)
    ).fetchone()
    if not existing:
        conn.close()
        return False

    # 如果设置 is_default=1，先清除同类型其他默认
    if fields.get("is_default"):
        model_type = fields.get("model_type", existing["model_type"])
        conn.execute(
            "UPDATE model_configs SET is_default=0, updated_at=CURRENT_TIMESTAMP "
            "WHERE model_type=? AND is_default=1 AND id!=?", (model_type, config_id)
        )

    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [config_id]
    conn.execute(
        f"UPDATE model_configs SET {set_clause} WHERE id=?",
        values
    )
    conn.commit()
    conn.close()
    return True


def delete_model_config(config_id: int) -> bool:
    """删除模型配置。若删除的是默认，自动提升同类型第一条为默认"""
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM model_configs WHERE id=?", (config_id,)
    ).fetchone()
    if not existing:
        conn.close()
        return False

    conn.execute("DELETE FROM model_configs WHERE id=?", (config_id,))

    # 如果删除的是默认模型，提升同类型第一条为默认
    if existing["is_default"]:
        first = conn.execute(
            "SELECT id FROM model_configs WHERE model_type=? AND is_enabled=1 "
            "ORDER BY id ASC LIMIT 1",
            (existing["model_type"],)
        ).fetchone()
        if first:
            conn.execute(
                "UPDATE model_configs SET is_default=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (first["id"],)
            )

    conn.commit()
    conn.close()
    return True


def get_default_model(model_type: str) -> dict | None:
    """获取某类型的默认配置（已启用）"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM model_configs WHERE model_type=? AND is_default=1 AND is_enabled=1 "
        "ORDER BY id ASC LIMIT 1",
        (model_type,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

"""
数据库模块：SQLite 表定义 + CRUD 操作
支持多群管理，所有数据按 group_id 隔离
"""
import sqlite3
import json
import logging
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from config import config

logger = logging.getLogger(__name__)


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


@contextmanager
def db():
    """数据库连接上下文管理器，自动 commit/rollback/close（v1.2.11）"""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cleanup_old_logs(retention_days: int = None, max_records: int = None):
    """清理过期的分析日志和任务记录

    Args:
        retention_days: 保留最近 N 天的记录（None=从 config 读取）
        max_records: 每个表最多保留的记录数（None=从 config 读取）
    """
    if retention_days is None:
        retention_days = getattr(config, "LOG_RETENTION_DAYS", 90)
    if max_records is None:
        max_records = getattr(config, "LOG_MAX_RECORDS", 500)

    try:
        with db() as conn:
            # 清理分析日志
            deleted_logs = conn.execute(
                "DELETE FROM analysis_log WHERE created_at < datetime('now', ?)",
                (f'-{retention_days} days',)
            ).rowcount
            # 保留最近 max_records 条任务记录
            deleted_tasks = conn.execute("""
                DELETE FROM task_records WHERE id NOT IN (
                    SELECT id FROM task_records ORDER BY created_at DESC LIMIT ?
                )
            """, (max_records,)).rowcount
            if deleted_logs or deleted_tasks:
                logger.info(
                    "日志清理: 删除 %d 条旧分析日志 (保留%d天), %d 条旧任务记录 (保留%d条)",
                    deleted_logs, retention_days, deleted_tasks, max_records
                )
    except Exception as e:
        logger.warning("清理过期日志失败: %s", e)  # 清理失败不影响主流程


def _backup_db_if_exists():
    """启动前自动备份数据库（版本变化时备份，防止迁移损坏旧数据）

    在 .db.bak 旁边写一个 .db.bak.version 文件记录备份时的版本号。
    当前运行版本与备份版本不同时 → 创建新备份（覆盖旧备份）。
    """
    import shutil
    from config import config
    db_path = get_db_path()
    backup_path = db_path.with_suffix(".db.bak")
    version_path = db_path.with_suffix(".db.bak.version")
    if not db_path.exists() or db_path.stat().st_size == 0:
        return

    need_backup = False
    if not backup_path.exists():
        need_backup = True
    else:
        # 版本变化时重新备份
        try:
            old_version = version_path.read_text().strip() if version_path.exists() else ""
            if old_version != config.VERSION:
                logger.info(f"版本变化 {old_version} → {config.VERSION}，创建新备份")
                need_backup = True
        except Exception:
            need_backup = True

    if need_backup:
        try:
            shutil.copy2(db_path, backup_path)
            version_path.write_text(config.VERSION)
            logger.info(f"数据库已备份: {backup_path} (v{config.VERSION})")
        except Exception as e:
            logger.warning("数据库备份失败: %s", e)  # 备份失败不影响启动


def init_db():
    """初始化所有表 + 兼容旧版本数据库迁移"""
    # v1.0: 启动前创建备份，防止迁移损坏旧数据
    _backup_db_if_exists()

    with db() as conn:
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

            -- v1.16.4 鱼际关系网
            CREATE TABLE IF NOT EXISTS fish_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                fish_wxid_a TEXT NOT NULL,
                fish_wxid_b TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                strength INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(group_id, fish_wxid_a, fish_wxid_b, relation_type),
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
        _seed_default_model_configs(conn)
        # v1.0.2: 应用设置（可热更新配置 + 停用词）
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                value_type TEXT NOT NULL DEFAULT 'string',
                description TEXT NOT NULL DEFAULT '',
                is_sensitive INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        _seed_app_settings(conn)
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

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                event_type TEXT NOT NULL CHECK(event_type IN ('decision','discussion','social','announcement','meme')),
                participant_ids TEXT DEFAULT '[]',
                key_quotes TEXT DEFAULT '[]',
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                message_start_idx INTEGER DEFAULT 0,
                message_end_idx INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                ai_model_used TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_events_group_time
                ON events(group_id, start_time);
            CREATE INDEX IF NOT EXISTS idx_events_type
                ON events(group_id, event_type);

            CREATE TABLE IF NOT EXISTS event_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','analyzing','analyzed','empty')),
                event_count INTEGER DEFAULT 0,
                summary_json TEXT DEFAULT '{}',
                event_id INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                analyzed_at TEXT,
                FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_event_windows_group_time
                ON event_windows(group_id, start_time);
            CREATE INDEX IF NOT EXISTS idx_event_windows_group_status
                ON event_windows(group_id, status);

            -- v1.18.3 群梗百科
            CREATE TABLE IF NOT EXISTS group_memes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                term TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT DEFAULT 'ai',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(group_id, term),
                FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
            );
        """)
        # 向后兼容：为已有数据库添加新列
        _migrate_db(conn)
        # v0.13.3: 常用查询索引
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_analysis_log_created_at ON analysis_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_analysis_log_group ON analysis_log(group_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_task_records_group ON task_records(group_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_portrait_versions_member ON portrait_versions(group_id, member_id);
        """)
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
            except Exception as e:
                logger.debug("创建索引失败(可能已存在): %s", e)
        # v0.9.3: 装备栏
        cur = conn.execute("PRAGMA table_info(fish_pond)")
        cols = {row[1] for row in cur.fetchall()}
        if "equipped_item" not in cols:
            conn.execute("ALTER TABLE fish_pond ADD COLUMN equipped_item TEXT DEFAULT ''")
        if "active_consumable" not in cols:
            conn.execute("ALTER TABLE fish_pond ADD COLUMN active_consumable TEXT DEFAULT ''")
        # WeFlow 同步设置（v0.x）：补足已有数据库缺失的配置项
        _migrate_weflow_settings(conn)
        # WeFlow 按群同步开关 + 状态
        _migrate_weflow_group_columns(conn)
        # v1.2.11: 修正 display_name 优先级（群昵称 > 昵称 > 备注）
        _migrate_display_name_priority(conn)
        # v1.5.0: 跨群身份 + QQ 平台支持
        _migrate_v1_5_0(conn)
        # v1.5.2: 全面画像
        _migrate_v1_5_2(conn)
        # v1.5.4: 可配置提示词 + 轮询间隔
        _migrate_v1_5_4(conn)
        # v1.16.0: 静默鱼塘 — 精力系统 + 性格系统 + Emoji 多态
        _migrate_v1_16_0(conn)
        # v1.16.1: 鱼塘金库
        _migrate_v1_16_1(conn)
        # v1.16.2: 鱼塘升级系统
        _migrate_v1_16_2(conn)
        # v1.16.3: 鱼塘 max_hp
        _migrate_v1_16_3(conn)
        # v1.16.4: 鱼塘终章 — 关系网 + 季节 + 天气扩展 + 传奇任务 + 定制
        _migrate_v1_16_4(conn)
        # v1.17.0: 本地大模型全局开关 — 旧用户自动开启
        _migrate_v1_17_0(conn)
        # v1.18.0: 事件探测
        _migrate_v1_18_0(conn)
        # v1.18.1: 事件两步拆分 — event_windows 表 + events.window_id
        _migrate_v1_18_1(conn)
        # v1.18.2: 事件丰富化 — report_json 列
        _migrate_v1_18_2(conn)
        # v1.18.3: 回填旧事件的 window_id
        _migrate_v1_18_3(conn)
        # v1.18.4: 群梗百科（group_memes 表由 CREATE TABLE IF NOT EXISTS 自动创建）
        _migrate_v1_18_4(conn)
    # 注：cleanup_old_logs()移至 main.py lifespan，在 load_from_db() 之后执行
    # 确保用户通过设置页面配置的保留策略生效


def _migrate_weflow_settings(conn):
    """v0.x: 为已有数据库补足 WeFlow 相关 app_settings"""
    existing = {
        row[0] for row in
        conn.execute("SELECT key FROM app_settings WHERE key LIKE 'weflow_%'").fetchall()
    }
    weflow_defaults = [
        ("weflow_enabled", str(config.WEFLOW_ENABLED).lower(), "bool",
         "WeFlow 自动同步开关"),
        ("weflow_base_url", config.WEFLOW_BASE_URL, "string",
         "WeFlow API 地址"),
        ("weflow_access_token", config.WEFLOW_ACCESS_TOKEN, "string",
         "WeFlow Access Token"),
        ("weflow_sync_interval_hours", str(config.WEFLOW_SYNC_INTERVAL_HOURS), "int",
         "WeFlow 自动同步间隔(小时)"),
    ]
    added = 0
    for key, value, value_type, description in weflow_defaults:
        if key not in existing:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, value_type, description) "
                "VALUES (?, ?, ?, ?)",
                (key, value, value_type, description)
            )
            added += 1
    if added:
        import logging
        logging.getLogger(__name__).info("DB migrate: added %d WeFlow settings", added)


def _migrate_weflow_group_columns(conn):
    """v1.2.x: chat_groups 新增 WeFlow 按群同步开关 + 状态列"""
    cur = conn.execute("PRAGMA table_info(chat_groups)")
    cols = {row[1] for row in cur.fetchall()}
    if "weflow_auto_sync" not in cols:
        conn.execute("ALTER TABLE chat_groups ADD COLUMN weflow_auto_sync INTEGER DEFAULT 0")
        import logging
        logging.getLogger(__name__).info("DB migrate: added chat_groups.weflow_auto_sync")
    if "weflow_last_sync_at" not in cols:
        conn.execute("ALTER TABLE chat_groups ADD COLUMN weflow_last_sync_at TEXT DEFAULT ''")
    if "weflow_last_sync_result" not in cols:
        conn.execute("ALTER TABLE chat_groups ADD COLUMN weflow_last_sync_result TEXT DEFAULT ''")
    # 修正存量 sender_count：排除群自身的系统 sender（wxid 含 @chatroom 的群）
    conn.execute("""
        UPDATE chat_groups SET sender_count = (
            SELECT COUNT(*) FROM group_members
            WHERE group_members.group_id = chat_groups.id
              AND (chat_groups.wxid NOT LIKE '%@chatroom' OR group_members.wxid != chat_groups.wxid)
        )
        WHERE wxid LIKE '%@chatroom'
    """)
    conn.commit()


def _migrate_display_name_priority(conn):
    """v1.2.11: 修正存量成员 display_name 优先级（群昵称 > 昵称 > 备注）

    旧优先级：remark → groupCard → name → nickname（备注优先，不合群聊习惯）
    新优先级：groupCard → nickname → remark → name（群昵称优先）
    """
    updated = conn.execute("""
        UPDATE group_members SET display_name =
            COALESCE(NULLIF(group_nickname, ''), NULLIF(nickname, ''), NULLIF(remark, ''), display_name)
        WHERE COALESCE(NULLIF(group_nickname, ''), NULLIF(nickname, '')) != ''
    """).rowcount
    if updated:
        import logging
        logging.getLogger(__name__).info("DB migrate: 修正 %d 个成员的 display_name 优先级", updated)


def _migrate_v1_5_0(conn):
    """v1.5.0: persona + platform + uin migration
    Pure additive: only ADD COLUMN + CREATE TABLE IF NOT EXISTS.
    No existing data is modified.
    """
    # 1. chat_groups.platform
    cur = conn.execute("PRAGMA table_info(chat_groups)")
    cols = {row[1] for row in cur.fetchall()}
    if "platform" not in cols:
        conn.execute("ALTER TABLE chat_groups ADD COLUMN platform TEXT DEFAULT ''")
        logger.info("DB migrate v1.5.0: added chat_groups.platform")

    # 2. group_members.uin (QQ number)
    cur = conn.execute("PRAGMA table_info(group_members)")
    cols = {row[1] for row in cur.fetchall()}
    if "uin" not in cols:
        conn.execute("ALTER TABLE group_members ADD COLUMN uin TEXT DEFAULT ''")
        logger.info("DB migrate v1.5.0: added group_members.uin")

    # 3. personas + persona_members (pure additive)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS personas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS persona_members (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id  INTEGER NOT NULL,
            member_id   INTEGER NOT NULL UNIQUE,
            FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE,
            FOREIGN KEY (member_id) REFERENCES group_members(id) ON DELETE CASCADE
        );
    """)
    logger.info("DB migrate v1.5.0: personas + persona_members tables ready")


def _migrate_v1_5_2(conn):
    """v1.5.2: personas comprehensive_portrait columns
    Pure additive: only ADD COLUMN, no data modification.
    """
    cur = conn.execute('PRAGMA table_info(personas)')
    cols = {row[1] for row in cur.fetchall()}
    if 'comprehensive_portrait_json' not in cols:
        conn.execute("ALTER TABLE personas ADD COLUMN comprehensive_portrait_json TEXT DEFAULT ''")
        import logging
        logging.getLogger(__name__).info('DB migrate v1.5.2: added personas.comprehensive_portrait_json')
    if 'comprehensive_portrait_updated' not in cols:
        conn.execute('ALTER TABLE personas ADD COLUMN comprehensive_portrait_updated TIMESTAMP')
        import logging
        logging.getLogger(__name__).info('DB migrate v1.5.2: added personas.comprehensive_portrait_updated')


def _migrate_v1_5_4(conn):
    """v1.5.4: prompt_profiles 表 + 轮询间隔 app_settings

    纯增量：仅 CREATE TABLE + INSERT 默认数据。
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prompt_profiles (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            analysis_type TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT '',
            is_default    INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    logger.info("DB migrate v1.5.4: prompt_profiles table ready")


def _migrate_v1_16_0(conn):
    """v1.16.0: 静默鱼塘 — 精力系统 + 性格系统 + Emoji 多态
    纯增量：ALTER TABLE ADD COLUMN + DEFAULT，不影响已有数据。
    """
    cur = conn.execute("PRAGMA table_info(fish_pond)")
    cols = {row[1] for row in cur.fetchall()}
    if "energy" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN energy INTEGER DEFAULT 100")
        logger.info("DB migrate v1.16.0: added fish_pond.energy")
    if "max_energy" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN max_energy INTEGER DEFAULT 100")
        logger.info("DB migrate v1.16.0: added fish_pond.max_energy")
    if "personality_traits" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN personality_traits TEXT DEFAULT '[]'")
        logger.info("DB migrate v1.16.0: added fish_pond.personality_traits")
    if "emoji_variant" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN emoji_variant TEXT DEFAULT ''")
        logger.info("DB migrate v1.16.0: added fish_pond.emoji_variant")


def _migrate_v1_16_1(conn):
    """v1.16.1: 鱼塘金库 + 被动事件冷却追踪"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pond_treasury (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL UNIQUE,
            balance INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS pond_treasury_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );
    """)
    logger.info("DB migrate v1.16.1: pond_treasury tables ready")


def _migrate_v1_16_2(conn):
    """v1.16.2: 鱼塘升级系统"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pond_upgrades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            upgrade_key TEXT NOT NULL,
            level INTEGER DEFAULT 0,
            UNIQUE(group_id, upgrade_key),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        )
    """)
    logger.info("DB migrate v1.16.2: pond_upgrades table ready")


def _migrate_v1_16_3(conn):
    """v1.16.3: 鱼塘 max_hp — 存储最大生命值，修正鱼缸血条显示
    仅在列首次添加时一次性计算所有鱼的 max_hp。后续启动不再重复计算，由业务逻辑维护。"""
    cur = conn.execute("PRAGMA table_info(fish_pond)")
    cols = {row[1] for row in cur.fetchall()}
    if "max_hp" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN max_hp INTEGER DEFAULT 20")
        logger.info("DB migrate v1.16.3: added fish_pond.max_hp")
        # 一次性：为已有鱼计算 max_hp（从 con + level + stage 推导）
        from services.fish_pond import compute_max_hp as _cmh
        rows = conn.execute(
            "SELECT id, group_id, wxid, constitution, level, stage, hp FROM fish_pond"
        ).fetchall()
        fixed = 0
        for row in rows:
            try:
                mx = _cmh(row[3] or 10, row[4] or 1, row[5] or "鱼苗")
            except Exception:
                mx = 20
            if mx < 1:
                mx = 1
            # 如果当前 hp 超过新计算的 max_hp，修正 hp 到 max_hp
            cur_hp = row[6] or 0
            if cur_hp > mx:
                conn.execute(
                    "UPDATE fish_pond SET max_hp=?, hp=? WHERE id=?",
                    (mx, mx, row[0])
                )
            else:
                conn.execute(
                    "UPDATE fish_pond SET max_hp=? WHERE id=?",
                    (mx, row[0])
                )
            fixed += 1
        if fixed:
            logger.info("DB migrate v1.16.3: computed max_hp for %d fish", fixed)


def _migrate_v1_16_4(conn):
    """v1.16.4: 鱼塘终章 — 鱼际关系表 + 传奇鱼任务列 + 新 settings key"""
    # 1. fish_pond 新增 legendary_quest_step 列
    cur = conn.execute("PRAGMA table_info(fish_pond)")
    cols = {row[1] for row in cur.fetchall()}
    if "legendary_quest_step" not in cols:
        conn.execute("ALTER TABLE fish_pond ADD COLUMN legendary_quest_step INTEGER DEFAULT 0")
        logger.info("DB migrate v1.16.4: added fish_pond.legendary_quest_step")

    # 2. fish_relationships 表已是 CREATE TABLE IF NOT EXISTS，
    #    但旧库可能没有（schema 中的 DDL 只在首次创建），这里补建
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fish_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            fish_wxid_a TEXT NOT NULL,
            fish_wxid_b TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            strength INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, fish_wxid_a, fish_wxid_b, relation_type),
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        );
    """)
    logger.info("DB migrate v1.16.4: fish_relationships table ready")


def _migrate_v1_17_0(conn):
    """v1.17.0: 本地大模型全局开关 — 检测旧用户已有本地模型配置，自动开启开关"""
    # 1. 检查 model_configs 中是否有本地模型记录
    has_local = conn.execute(
        "SELECT COUNT(*) FROM model_configs WHERE model_type='local'"
    ).fetchone()[0] > 0

    if has_local:
        # 旧用户已有本地模型 → 自动开启开关，确保升级后功能不受影响
        # 使用 UPSERT：_seed_app_settings 已写入 false，需覆盖
        conn.execute("""
            INSERT INTO app_settings (key, value, value_type, description)
            VALUES ('local_llm_enabled', 'true', 'bool', '启用本地大模型（Ollama），关闭后隐藏本地模型相关功能')
            ON CONFLICT(key) DO UPDATE SET value = 'true'
        """)
        logger.info("DB migrate v1.17.0: 检测到已有本地模型，local_llm_enabled 自动设为 true")
    else:
        logger.info("DB migrate v1.17.0: 无本地模型记录，local_llm_enabled 保持默认 false")


def _migrate_v1_18_0(conn):
    """v1.18.0: 事件探测 — 插入默认 prompt_profiles + 补种事件探测 app_settings。

    纯增量：仅 INSERT 缺失数据，不修改已有数据。
    """
    # 1. 补种事件探测 app_settings（不覆盖已有值）
    existing_settings = {
        row[0] for row in
        conn.execute("SELECT key FROM app_settings WHERE key LIKE 'event_%'").fetchall()
    }
    event_settings = [
        ("event_window_size", "200", "int", "事件探测窗口消息数"),
        ("event_window_overlap", "20", "int", "事件探测窗口重叠消息数"),
        ("event_ai_concurrency", "3", "int", "事件探测 AI 并发数"),
        ("event_active_group_threshold", "30", "int", "活跃群判定阈值(条/小时)"),
        ("event_active_peak_absolute", "80", "int", "活跃群尖峰绝对阈值(条/30分钟)"),
        ("event_quiet_peak_multiplier", "3", "int", "安静群尖峰相对倍数"),
    ]
    added = 0
    for key, value, value_type, description in event_settings:
        if key not in existing_settings:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, value_type, description) "
                "VALUES (?, ?, ?, ?)",
                (key, value, value_type, description)
            )
            added += 1
    if added:
        logger.info("DB migrate v1.18.0: added %d event detection settings", added)

    # 2. 插入默认事件探测 System Prompt（不覆盖已有 profile）
    import logging as _logging
    existing = conn.execute(
        "SELECT COUNT(*) FROM prompt_profiles WHERE analysis_type='event_detection'"
    ).fetchone()[0]
    if existing == 0:
        default_prompt = (
            "你是一个群聊历史学家+八卦记者+脱口秀段子手的混合体。\n"
            "你的任务是从群聊对话中发掘那些值得被记住的事件——\n"
            "无论是重要决定、欢乐瞬间、名场面诞生，还是群友之间的默契互动。\n\n"
            "你像一个坐在群里的隐形观察员，把精华时刻记录下来，\n"
            "用轻松诙谐的口吻写成事件卡片。读者看完应该会心一笑：\n"
            "“对对对，那天就是这样！”\n\n"
            "事件类型：\n"
            "- decision：群内做出了某个决定（讨论→收敛→结论）\n"
            "- discussion：围绕某个话题的深度讨论\n"
            "- social：社交互动（庆祝、欢迎、告别、起哄等）\n"
            "- announcement：某人宣布了重要消息\n"
            "- meme：梗/文化的诞生和传播\n\n"
            "如果这段对话中没有明显事件（就是日常闲聊），返回空 events 数组。"
        )
        conn.execute(
            "INSERT INTO prompt_profiles (name, analysis_type, system_prompt, is_default) "
            "VALUES (?, 'event_detection', ?, 1)",
            ("默认事件分析风格", default_prompt)
        )
        logger.info("DB migrate v1.18.0: added default event_detection prompt profile")
    else:
        logger.info("DB migrate v1.18.0: event_detection prompt profile already exists")


def _migrate_v1_18_1(conn):
    """v1.18.1: 事件两步拆分 — events.window_id + event_windows 配置迁移

    1. event_windows 表由 init_db 的 CREATE TABLE IF NOT EXISTS 自动创建
    2. 仅处理增量：ALTER TABLE events ADD COLUMN window_id
    3. 替换旧 event_* 配置为新的自适应切分配置
    """
    # 1. events.window_id 列
    cur = conn.execute("PRAGMA table_info(events)")
    cols = {row[1] for row in cur.fetchall()}
    if "window_id" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN window_id INTEGER")
        logger.info("DB migrate v1.18.1: added events.window_id")

    # 2. 替换旧配置：EVENT_WINDOW_SIZE/OVERLAP → 新自适应切分配置
    new_settings = [
        ("event_min_gap_minutes", "15", "int", "事件组最小时间间隙(分钟)"),
        ("event_min_group_size", "10", "int", "事件组最小消息数"),
        ("event_max_group_size", "500", "int", "事件组最大消息数"),
    ]
    for key, value, value_type, description in new_settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, value_type, description) "
            "VALUES (?, ?, ?, ?)",
            (key, value, value_type, description)
        )
    logger.info("DB migrate v1.18.1: added adaptive segmentation settings")


def _migrate_v1_18_2(conn):
    """v1.18.2: 事件丰富化 — events.report_json 列"""
    cur = conn.execute("PRAGMA table_info(events)")
    cols = {row[1] for row in cur.fetchall()}
    if "report_json" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN report_json TEXT DEFAULT ''")
        logger.info("DB migrate v1.18.2: added events.report_json")


def _migrate_v1_18_3(conn):
    """v1.18.3: 回填旧事件的 window_id — 从 event_windows 表关联"""
    result = conn.execute(
        "UPDATE events SET window_id = ("
        "  SELECT id FROM event_windows WHERE event_windows.event_id = events.id"
        ") WHERE window_id IS NULL"
    )
    count = result.rowcount
    if count > 0:
        logger.info("DB migrate v1.18.3: backfilled %d events.window_id from event_windows", count)


def _migrate_v1_18_4(conn):
    """v1.18.4: 群梗百科 — group_memes 由 CREATE TABLE IF NOT EXISTS 自动创建"""


# ── 群梗百科 CRUD ─────────────────────────────────────────────────

def get_group_memes(group_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM group_memes WHERE group_id=? ORDER BY term", (group_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_group_meme(group_id: int, term: str, description: str, source: str = "user") -> int | None:
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO group_memes (group_id, term, description, source) VALUES (?,?,?,?)",
                (group_id, term.strip(), description.strip(), source)
            )
            return cur.lastrowid
    except Exception:
        return None


def update_group_meme(meme_id: int, description: str) -> bool:
    with db() as conn:
        cur = conn.execute(
            "UPDATE group_memes SET description=?, updated_at=datetime('now','localtime') WHERE id=?",
            (description.strip(), meme_id)
        )
        return cur.rowcount > 0


def delete_group_meme(meme_id: int) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM group_memes WHERE id=?", (meme_id,))
        return cur.rowcount > 0


def _seed_default_model_configs(conn):
    """v1.0: 首次启动时预置默认模型配置。在线模型 api_key 为空，用户自行填写。"""
    count = conn.execute("SELECT COUNT(*) FROM model_configs").fetchone()[0]
    if count > 0:
        return  # 已有配置，不覆盖

    # 1. 在线模型（DeepSeek）— 用户只需粘贴 API Key
    conn.execute(
        """INSERT INTO model_configs (name, model_type, endpoint, api_key, model_name, is_default)
           VALUES (?, 'online', ?, '', ?, 1)""",
        ("在线模型", config.DEEPSEEK_API_URL, config.DEEPSEEK_MODEL)
    )

    # 2. 本地模型（Ollama）— 高级用户可选
    conn.execute(
        """INSERT INTO model_configs (name, model_type, endpoint, model_name, is_default)
           VALUES (?, 'local', ?, ?, 1)""",
        ("Ollama (本地)", config.OLLAMA_HOST, config.OLLAMA_MODEL)
    )
    conn.commit()


# v1.2.8: 所有可热更新设置的注册表（key, default_value, value_type, description）
# 同时用于 _seed_app_settings（补种缺失键）和 upsert_app_setting（确定 value_type）
_APP_SETTINGS_REGISTRY = None


def _get_settings_registry():
    """惰性构建设置注册表 {key: (value, value_type, description)}"""
    global _APP_SETTINGS_REGISTRY
    if _APP_SETTINGS_REGISTRY is not None:
        return _APP_SETTINGS_REGISTRY
    _APP_SETTINGS_REGISTRY = {}
    for entry in _SETTINGS_DEFS:
        key, value, value_type, description = entry
        _APP_SETTINGS_REGISTRY[key] = (value, value_type, description)
    # 停用词特殊处理
    _APP_SETTINGS_REGISTRY["stopwords_text"] = (config.DEFAULT_STOPWORDS, "string", "用户自定义过滤词")
    return _APP_SETTINGS_REGISTRY


def _seed_app_settings(conn):
    """v1.2.8: 补足缺失的 app_settings + 修复 value_type 错误的历史数据"""
    existing_rows = {row[0]: row[1] for row in conn.execute("SELECT key, value_type FROM app_settings").fetchall()}
    registry = _get_settings_registry()

    # 1. 补足缺失的键
    for key, (value, value_type, description) in registry.items():
        if key not in existing_rows:
            conn.execute(
                "INSERT INTO app_settings (key, value, value_type, description) "
                "VALUES (?, ?, ?, ?)",
                (key, value, value_type, description)
            )
        elif existing_rows[key] != value_type:
            # 2. 修复 value_type 错误的历史数据（如 upsert 误写为 'string'）
            conn.execute(
                "UPDATE app_settings SET value_type = ? WHERE key = ?",
                (value_type, key)
            )
            logger.warning(f"已修复 app_settings.{key} 的 value_type: {existing_rows[key]} → {value_type}")

    conn.commit()


# 所有可热更新设置的定义（key, str_value, value_type, description）
_SETTINGS_DEFS = [
        # 高级：Ollama
        ("ollama_timeout", str(config.OLLAMA_TIMEOUT), "int",
         "Ollama 请求超时(秒)"),
        # 高级：GPU 分布式锁
        ("gpu_lock_enabled", str(config.GPU_LOCK_ENABLED).lower(), "bool",
         "GPU 分布式锁开关"),
        ("gpu_lock_url", config.GPU_LOCK_URL, "string",
         "GPU 锁服务地址"),
        ("gpu_lock_who", config.GPU_LOCK_WHO, "string",
         "GPU 锁持有者标识"),
        ("gpu_lock_retry_interval", str(config.GPU_LOCK_RETRY_INTERVAL), "int",
         "GPU 锁重试间隔(秒)"),
        ("gpu_lock_max_retries", str(config.GPU_LOCK_MAX_RETRIES), "int",
         "GPU 锁最大重试次数"),
        # 高级：DeepSeek
        ("online_retry_count", str(config.ONLINE_RETRY_COUNT), "int",
         "在线模型失败重试次数"),
        ("deepseek_timeout", str(config.DEEPSEEK_TIMEOUT), "int",
         "DeepSeek API 超时(秒)"),
        ("weekly_temperature", str(config.WEEKLY_TEMPERATURE), "float",
         "周报 AI 温度(0-2)"),
        ("monthly_temperature", str(config.MONTHLY_TEMPERATURE), "float",
         "月报 AI 温度(0-2)"),
        ("deepseek_max_tokens_weekly", str(config.DEEPSEEK_MAX_TOKENS_WEEKLY), "int",
         "周报最大输出 Token 数"),
        ("deepseek_max_tokens_monthly", str(config.DEEPSEEK_MAX_TOKENS_MONTHLY), "int",
         "月报最大输出 Token 数"),
        # 高级：画像
        ("portrait_refresh_days", str(config.PORTRAIT_REFRESH_DAYS), "int",
         "画像刷新阈值(天)"),
        # 高级：周期报告可用性阈值（周报/月报/年报 最低天数+消息数）
        ("weekly_min_days", str(config.WEEKLY_MIN_DAYS), "int",
         "周报最低天数"),
        ("weekly_min_msgs", str(config.WEEKLY_MIN_MSGS), "int",
         "周报最低消息数"),
        ("monthly_min_days", str(config.MONTHLY_MIN_DAYS), "int",
         "月报最低天数"),
        ("monthly_min_msgs", str(config.MONTHLY_MIN_MSGS), "int",
         "月报最低消息数"),
        ("annual_min_days", str(config.ANNUAL_MIN_DAYS), "int",
         "年报最低天数"),
        ("annual_min_msgs", str(config.ANNUAL_MIN_MSGS), "int",
         "年报最低消息数"),
        # WeFlow 增量同步
        ("weflow_enabled", str(config.WEFLOW_ENABLED).lower(), "bool",
         "WeFlow 自动同步开关"),
        ("weflow_base_url", config.WEFLOW_BASE_URL, "string",
         "WeFlow API 地址"),
        ("weflow_access_token", config.WEFLOW_ACCESS_TOKEN, "string",
         "WeFlow Access Token"),
        ("weflow_sync_interval_hours", str(config.WEFLOW_SYNC_INTERVAL_HOURS), "int",
         "WeFlow 自动同步间隔(小时)"),
        # v1.5.4: 轮询间隔
        ("poll_interval_dashboard_ms", "10000", "int",
         "仪表盘轮询间隔(毫秒)"),
        ("poll_interval_portraits_ms", "10000", "int",
         "画像页轮询间隔(毫秒)"),
        ("poll_interval_stats_s", "30", "int",
         "GUI统计轮询间隔(秒)"),
        # v1.16.0: 鱼塘精力系统
        ("pond_energy_regen_amount", "5", "int",
         "鱼塘精力每轮恢复量"),
        ("pond_touch_daily_limit", "5", "int",
         "摸鱼每日次数上限"),
        # v1.16.1: 鱼塘自动化被动事件 + 金库
        ("pond_auto_events_enabled", "false", "bool",
         "鱼塘自动化全局开关"),
        ("pond_event_interval_minutes", "30", "int",
         "被动事件间隔(分钟)"),
        ("pond_treasury_tax_rate", "5", "int",
         "金库税率(%，全群鳞币总和百分比)"),
        # v1.16.4: 鱼塘终章 — 公告牌 + 创意工坊
        ("pond_bulletin_board", "", "string",
         "鱼塘公告牌内容"),
        ("custom_flavor_texts", "[]", "string",
         "用户自定义风味文本（JSON数组）"),
        ("custom_last_words", "[]", "string",
         "用户自定义鱼遗言（JSON数组）"),
        ("custom_daily_status", "[]", "string",
         "用户自定义状态语（JSON数组）"),
        # v1.16.5: 作弊模式 + 天气覆盖
        ("pond_cheat_mode", "false", "bool",
         "允许作弊开关（开启后禁用成就，启用调试面板）"),
        ("pond_cheat_weather_override", "", "string",
         "调试天气覆盖（空=不覆盖）"),
        # v1.17.0: 本地大模型全局开关
        ("local_llm_enabled", str(config.LOCAL_LLM_ENABLED).lower(), "bool",
         "启用本地大模型（Ollama），关闭后隐藏本地模型相关功能"),
        ("local_llm_host", config.LOCAL_LLM_HOST, "string",
         "Ollama 服务默认地址（添加本地模型时默认使用）"),
        ("local_llm_fallback_model", config.LOCAL_LLM_FALLBACK_MODEL, "string",
         "子任务重试降级模型名（本地模型失败时使用）"),
        # v1.17.0: 管道执行参数
        ("pipeline_max_retries", str(config.PIPELINE_MAX_RETRIES), "int",
         "子任务最大重试次数"),
        ("pipeline_step_timeout", str(config.PIPELINE_STEP_TIMEOUT), "int",
         "单个子任务超时(秒)"),
        ("pipeline_circuit_breaker_threshold", str(config.PIPELINE_CIRCUIT_BREAKER_THRESHOLD), "int",
         "熔断触发阈值(连续失败N次触发)"),
        ("pipeline_circuit_breaker_cooldown", str(config.PIPELINE_CIRCUIT_BREAKER_COOLDOWN), "int",
         "熔断冷却时间(秒)"),
        # 日志清理
        ("log_retention_days", str(config.LOG_RETENTION_DAYS), "int",
         "分析日志保留天数"),
        ("log_max_records", str(config.LOG_MAX_RECORDS), "int",
         "任务记录最多保留条数"),
        # v1.18.0: 事件探测（event_window_size/overlap/ai_concurrency 已在 v1.18.1 废弃）
        ("event_active_group_threshold", str(config.EVENT_ACTIVE_GROUP_THRESHOLD), "int",
         "活跃群判定阈值(条/小时)"),
        ("event_active_peak_absolute", str(config.EVENT_ACTIVE_PEAK_ABSOLUTE), "int",
         "活跃群尖峰绝对阈值(条/小时)"),
        ("event_quiet_peak_multiplier", str(config.EVENT_QUIET_PEAK_MULTIPLIER), "int",
         "安静群尖峰相对倍数"),
        # v1.18.1: 自适应事件组切分
        ("event_min_gap_minutes", str(config.EVENT_MIN_GAP_MINUTES), "int",
         "事件组最小时间间隙(分钟)"),
        ("event_min_group_size", str(config.EVENT_MIN_GROUP_SIZE), "int",
         "事件组最小消息数"),
        ("event_max_group_size", str(config.EVENT_MAX_GROUP_SIZE), "int",
         "事件组最大消息数"),
    ]
    # _seed_app_settings 使用 _SETTINGS_DEFS + _get_settings_registry() 统一处理


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
        if deleted:
            logger.warning("数据库迁移: 删除 %d 行孤儿画像（member_id 不在 group_members 中），"
                          "备份文件: %s", deleted, get_db_path().with_suffix(".db.bak"))
        if fixed_rows or deleted:
            logger.info("数据库迁移: 修复 %d 行, 删除 %d 行", fixed_rows, deleted)
        # 3. 清理重复：按 wxid 去重，保留 id 最大的
        dup_cursor = conn.execute("""
            DELETE FROM group_members WHERE id NOT IN (
                SELECT MAX(id) FROM group_members
                WHERE wxid IS NOT NULL AND wxid != ''
                GROUP BY group_id, wxid
            )
        """)
        if dup_cursor.rowcount:
            logger.warning("数据库迁移: 删除 %d 个重复成员记录（按 wxid 去重），备份文件: %s",
                         dup_cursor.rowcount, get_db_path().with_suffix(".db.bak"))
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
                 file_path: str = "", platform: str = "") -> int:
    """创建群记录，返回 group_id。v1.5.0: 新增 platform 参数。"""
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO chat_groups (name, display_name, wxid, message_count,
               sender_count, date_range_start, date_range_end, file_path, platform)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, display_name, wxid, message_count, sender_count,
             date_start, date_end, file_path, platform)
        )
        gid = cur.lastrowid
    return gid


def list_groups() -> list[dict]:
    """列出所有活跃的群"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_groups WHERE status='active' ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_group(group_id: int) -> dict | None:
    """获取单个群信息"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM chat_groups WHERE id=?", (group_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_group(group_id: int):
    """删除群及其所有关联数据（CASCADE）"""
    with db() as conn:
        conn.execute("DELETE FROM chat_groups WHERE id=?", (group_id,))


def update_group_stats(group_id: int, analyzed_days: int):
    """更新已分析天数"""
    with db() as conn:
        conn.execute(
            "UPDATE chat_groups SET analyzed_days=? WHERE id=?",
            (analyzed_days, group_id)
        )


# ==================== 成员 CRUD ====================

def upsert_members(group_id: int, senders: list[dict]):
    """批量写入群成员：按 wxid 去重，新成员插入，已有成员更新非空字段

    wxid 是微信账号的稳定标识，不会因重新导出而改变。
    sender_id 是导出工具临时编号，仅用于匹配消息。
    """
    with db() as conn:
        for s in senders:
            sender_id = s.get("senderID", 0)
            wxid = s.get("wxid", "") or f"fallback_{sender_id}"
            display_name = s.get("displayName", "")
            nickname = s.get("nickname", "")
            remark = s.get("remark", "")
            group_nickname = s.get("groupNickname", "")
            avatar = s.get("avatar", "")
            uin = s.get("uin", "")  # v1.5.0: QQ 号

            conn.execute(
                """INSERT INTO group_members
                   (group_id, sender_id, wxid, display_name, nickname, remark,
                    group_nickname, avatar, uin)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(group_id, wxid) DO UPDATE SET
                   sender_id = excluded.sender_id,
                   display_name = COALESCE(NULLIF(excluded.display_name, ''), display_name),
                   nickname = COALESCE(NULLIF(excluded.nickname, ''), nickname),
                   remark = COALESCE(NULLIF(excluded.remark, ''), remark),
                   group_nickname = COALESCE(NULLIF(excluded.group_nickname, ''), group_nickname),
                   avatar = COALESCE(NULLIF(excluded.avatar, ''), avatar),
                   uin = COALESCE(NULLIF(excluded.uin, ''), uin)""",
                (group_id, sender_id, wxid, display_name, nickname, remark,
                 group_nickname, avatar, uin)
            )


def upsert_avatars_only(group_id: int, wxid_avatar_map: dict[str, str]):
    """仅更新已有成员的 avatar 字段（用于已有群重新导入时补充头像）"""
    if not wxid_avatar_map:
        return
    with db() as conn:
        for wxid, avatar in wxid_avatar_map.items():
            conn.execute(
                "UPDATE group_members SET avatar=? WHERE group_id=? AND wxid=? AND (avatar IS NULL OR avatar='')",
                (avatar, group_id, wxid)
            )


def get_members(group_id: int) -> list[dict]:
    """获取群成员列表，按消息数降序（排除群自身的系统 sender，仅群聊）"""
    with db() as conn:
        group = conn.execute("SELECT wxid FROM chat_groups WHERE id=?", (group_id,)).fetchone()
        group_wxid = group["wxid"] if group else None
        # 只有群聊才需要排除群自身系统 sender（wxid 含 @chatroom），私聊不过滤
        if group_wxid and "@chatroom" in group_wxid:
            rows = conn.execute(
                "SELECT * FROM group_members WHERE group_id=? AND wxid!=? ORDER BY message_count DESC",
                (group_id, group_wxid)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM group_members WHERE group_id=? ORDER BY message_count DESC",
                (group_id,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_member(group_id: int, member_id: int) -> dict | None:
    """获取单个成员"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM group_members WHERE group_id=? AND id=?",
            (group_id, member_id)
        ).fetchone()
    return dict(row) if row else None


def get_member_by_sender_id(group_id: int, sender_id: int) -> dict | None:
    """通过原始 senderID 获取成员"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM group_members WHERE group_id=? AND sender_id=?",
            (group_id, sender_id)
        ).fetchone()
    return dict(row) if row else None


def update_member_message_count(group_id: int, wxid: str, count: int):
    """更新成员消息计数（按 wxid）"""
    with db() as conn:
        conn.execute(
            "UPDATE group_members SET message_count=? WHERE group_id=? AND wxid=?",
            (count, group_id, wxid)
        )


# ==================== 每日报告 CRUD ====================

def save_daily_report(group_id: int, date: str, message_count: int,
                       active_members: int, report_json: str,
                       model_used: str):
    """保存每日报告（INSERT OR REPLACE）"""
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO daily_reports
               (group_id, date, message_count, active_members, report_json, model_used)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (group_id, date, message_count, active_members, report_json, model_used)
        )


def get_daily_report(group_id: int, date: str) -> dict | None:
    """获取某天的报告"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM daily_reports WHERE group_id=? AND date=?",
            (group_id, date)
        ).fetchone()
    return dict(row) if row else None


def get_daily_reports_batch(group_id: int, dates: list[str]) -> list[dict]:
    """批量获取多天的报告（单次连接，避免逐条打开阻塞事件循环）"""
    if not dates:
        return []
    with db() as conn:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""SELECT * FROM daily_reports
                WHERE group_id=? AND date IN ({placeholders})
                ORDER BY date""",
            (group_id, *dates)
        ).fetchall()
    return [dict(r) for r in rows]


def get_analyzed_dates(group_id: int) -> list[str]:
    """获取已分析的日期列表"""
    with db() as conn:
        rows = conn.execute(
            "SELECT date FROM daily_reports WHERE group_id=? ORDER BY date DESC",
            (group_id,)
        ).fetchall()
    return [r["date"] for r in rows]


# v0.13.2: 分析中日期追踪（防并发 analyze-all 重复处理）
_analyzing_dates: set[str] = set()


def mark_date_analyzing(group_id: int, date: str):
    """标记日期为分析中"""
    _analyzing_dates.add(f"{group_id}:{date}")


def unmark_date_analyzing(group_id: int, date: str):
    """取消分析中标记"""
    _analyzing_dates.discard(f"{group_id}:{date}")


def is_date_analyzing(group_id: int, date: str) -> bool:
    """检查日期是否正在分析中"""
    return f"{group_id}:{date}" in _analyzing_dates


def get_recent_reports(group_id: int, limit: int = 7) -> list[dict]:
    """获取最近的报告摘要"""
    with db() as conn:
        rows = conn.execute(
            """SELECT date, message_count, active_members, report_json, model_used, created_at
               FROM daily_reports WHERE group_id=?
               ORDER BY date DESC LIMIT ?""",
            (group_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


# ==================== 群友画像 CRUD ====================

def save_member_portrait(group_id: int, member_id: int, display_name: str,
                          total_messages: int, portrait_json: str,
                          data_start: str = "", data_end: str = ""):
    """保存成员画像"""
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO member_portraits
               (group_id, member_id, display_name, total_analyzed_messages,
                portrait_json, data_start_date, data_end_date, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (group_id, member_id, display_name, total_messages,
             portrait_json, data_start, data_end, datetime.now().isoformat())
        )


def get_portraits(group_id: int) -> list[dict]:
    """获取群所有成员画像"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM member_portraits WHERE group_id=?",
            (group_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_portrait(group_id: int, member_id: int) -> dict | None:
    """获取单个成员画像"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM member_portraits WHERE group_id=? AND member_id=?",
            (group_id, member_id)
        ).fetchone()
    return dict(row) if row else None


def get_stale_portraits(group_id: int, refresh_days: int) -> list[dict]:
    """获取需要刷新的画像（累积新消息 >= refresh_days 天）"""
    with db() as conn:
        # 画像的 total_analyzed_messages 小于成员实际 message_count 超过阈值
        rows = conn.execute(
            """SELECT mp.*, gm.message_count as current_count
               FROM member_portraits mp
               JOIN group_members gm ON mp.member_id = gm.id AND mp.group_id = gm.group_id
               WHERE mp.group_id=? AND (gm.message_count - mp.total_analyzed_messages) >= ?""",
            (group_id, refresh_days * 50)  # 粗略估计：每天至少50条新消息
        ).fetchall()
    return [dict(r) for r in rows]


# ==================== 画像版本历史 ====================

def save_portrait_version(group_id: int, member_id: int, version: int,
                           portrait_json: str, analyzed_msg_count: int = 0,
                           data_start: str = "", data_end: str = "",
                           model_used: str = "", duration_ms: int = 0):
    """保存画像的历史版本"""
    with db() as conn:
        conn.execute(
            """INSERT INTO portrait_versions
               (group_id, member_id, version, portrait_json, analyzed_msg_count,
                data_start_date, data_end_date, model_used, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (group_id, member_id, version, portrait_json, analyzed_msg_count,
             data_start, data_end, model_used, duration_ms)
        )


def get_portrait_versions(group_id: int, member_id: int) -> list[dict]:
    """获取成员的画像版本历史（最新在前）"""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM portrait_versions
               WHERE group_id=? AND member_id=?
               ORDER BY version DESC""",
            (group_id, member_id)
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_portrait_version(group_id: int, member_id: int) -> int:
    """获取成员画像的最新版本号，从未有过则返回 0"""
    with db() as conn:
        row = conn.execute(
            """SELECT MAX(version) as max_v FROM portrait_versions
               WHERE group_id=? AND member_id=?""",
            (group_id, member_id)
        ).fetchone()
    return row["max_v"] or 0


# ==================== 分析日志 ====================

def log_analysis(group_id: int, date: str, analysis_type: str,
                 status: str, model_used: str = "",
                 duration_ms: int = 0, error_msg: str = ""):
    """记录分析任务日志"""
    with db() as conn:
        conn.execute(
            """INSERT INTO analysis_log
               (group_id, date, analysis_type, status, model_used, duration_ms, error_msg)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (group_id, date, analysis_type, status, model_used, duration_ms, error_msg)
        )


# ==================== 任务记录 CRUD ====================

def save_task_record(task_id: str, group_id: int, task_type: str, target: str,
                     status: str, total_duration_ms: int, model_used: str = "",
                     steps_json: str = "", error_summary: str = ""):
    """保存任务执行记录"""
    with db() as conn:
        conn.execute(
            """INSERT INTO task_records (task_id, group_id, task_type, target, status,
               total_duration_ms, model_used, steps_json, error_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, group_id, task_type, target, status,
             total_duration_ms, model_used, steps_json, error_summary)
        )


def get_task_history(group_id: int = None, task_type: str = None,
                     status: str = None, limit: int = 20, offset: int = 0) -> list[dict]:
    """查询任务历史（v1.13.0: 支持 type/status 筛选 + 分页）"""
    with db() as conn:
        where = []
        params = []
        if group_id:
            where.append("group_id=?")
            params.append(group_id)
        if task_type:
            where.append("task_type=?")
            params.append(task_type)
        if status:
            where.append("status=?")
            params.append(status)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"SELECT * FROM task_records {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_task_record(task_id: str) -> dict | None:
    """查询单个任务记录"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM task_records WHERE task_id=?", (task_id,)
        ).fetchone()
    return dict(row) if row else None


# ==================== 周期报告（周报/月报）CRUD ====================

def save_periodic_report(group_id: int, report_type: str, period_key: str,
                          date_start: str, date_end: str, day_count: int,
                          total_messages: int, active_members: int,
                          report_json: str, model_used: str = ""):
    """保存周报/月报（INSERT OR REPLACE）"""
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO periodic_reports
               (group_id, report_type, period_key, date_start, date_end,
                day_count, total_messages, active_members, report_json, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (group_id, report_type, period_key, date_start, date_end,
             day_count, total_messages, active_members, report_json, model_used)
        )


def get_periodic_report(group_id: int, report_type: str,
                        period_key: str) -> dict | None:
    """获取单个周期报告"""
    with db() as conn:
        row = conn.execute(
            """SELECT * FROM periodic_reports
               WHERE group_id=? AND report_type=? AND period_key=?""",
            (group_id, report_type, period_key)
        ).fetchone()
    return dict(row) if row else None


def list_periodic_reports(group_id: int, report_type: str = "") -> list[dict]:
    """列出群的所有周期报告，按 period_key 倒序"""
    with db() as conn:
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
    return [dict(r) for r in rows]


def delete_periodic_report(group_id: int, report_type: str,
                           period_key: str) -> bool:
    """删除周期报告，返回是否成功删除"""
    with db() as conn:
        cur = conn.execute(
            """DELETE FROM periodic_reports
               WHERE group_id=? AND report_type=? AND period_key=?""",
            (group_id, report_type, period_key)
        )
        deleted = cur.rowcount > 0
    return deleted


# ==================== 年度奖项 v0.11 CRUD ====================

def save_annual_awards(group_id: int, year: int, awards: list[dict],
                        ceremony_version: int = 1):
    """保存年度奖项列表。先删旧奖项再批量插入"""
    with db() as conn:
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


def get_annual_awards(group_id: int, year: int) -> list[dict]:
    """获取某群某年的所有奖项"""
    with db() as conn:
        rows = conn.execute(
            """SELECT aa.*, gm.display_name, gm.wxid
               FROM annual_awards aa
               LEFT JOIN group_members gm ON aa.member_id = gm.id
               WHERE aa.group_id=? AND aa.year=?
               ORDER BY aa.id""",
            (group_id, year)
        ).fetchall()
    return [dict(r) for r in rows]


def get_member_awards(group_id: int, member_id: int) -> list[dict]:
    """获取某成员的所有年份奖项"""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM annual_awards
               WHERE group_id=? AND member_id=?
               ORDER BY year DESC, id""",
            (group_id, member_id)
        ).fetchall()
    return [dict(r) for r in rows]


def get_member_awards_batch(group_id: int, member_ids: list[int]) -> dict[int, list[dict]]:
    """批量获取多个成员的奖项，返回 {member_id: [award_dict, ...]}"""
    if not member_ids:
        return {}
    with db() as conn:
        placeholders = ','.join('?' * len(member_ids))
        rows = conn.execute(
            f"""SELECT * FROM annual_awards
                WHERE group_id=? AND member_id IN ({placeholders})
                ORDER BY member_id, year DESC, id""",
            [group_id] + member_ids
        ).fetchall()
    result = defaultdict(list)
    for r in rows:
        result[r["member_id"]].append(dict(r))
    return dict(result)


def delete_annual_awards(group_id: int, year: int) -> bool:
    """删除某群某年的所有奖项"""
    with db() as conn:
        cur = conn.execute(
            "DELETE FROM annual_awards WHERE group_id=? AND year=?",
            (group_id, year)
        )
        deleted = cur.rowcount > 0
    return deleted


# ==================== 群鱼塘 v0.9 CRUD ====================

def upsert_fish(group_id: int, wxid: str, fish_name: str, species: str,
                rarity: str, strength: int, dexterity: int, constitution: int,
                intelligence: int, wisdom: int, charisma: int,
                experience: int = 0, level: int = 1,
                growth: float = 0, happiness: float = 50, hp: int = 20,
                stage: str = "鱼苗", consecutive_days: int = 0,
                last_active_date: str = "", last_fed_date: str = "",
                is_alive: int = 1,
                energy: int = 100, max_energy: int = 100,  # v1.16.0
                personality_traits: str = "[]",  # v1.16.0: JSON array
                emoji_variant: str = "",  # v1.16.0
                max_hp: int = 20) -> int:  # v1.16.3
    """创建或更新鱼（按 group_id + wxid 唯一键）"""
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO fish_pond
               (group_id, wxid, fish_name, species, rarity,
                strength, dexterity, constitution, intelligence, wisdom, charisma,
                experience, level, growth, happiness, hp, stage,
                consecutive_days, last_active_date, last_fed_date, is_alive,
                energy, max_energy, personality_traits, emoji_variant,
                max_hp, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
               energy = excluded.energy,
               max_energy = excluded.max_energy,
               personality_traits = excluded.personality_traits,
               emoji_variant = excluded.emoji_variant,
               max_hp = excluded.max_hp,
               updated_at = datetime('now')""",
            (group_id, wxid, fish_name, species, rarity,
             strength, dexterity, constitution, intelligence, wisdom, charisma,
             experience, level, growth, happiness, hp, stage,
             consecutive_days, last_active_date, last_fed_date, is_alive,
             energy, max_energy, personality_traits, emoji_variant, max_hp)
        )
        fid = cur.lastrowid
    return fid


def get_fish(group_id: int, wxid: str) -> dict | None:
    """获取单条鱼"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM fish_pond WHERE group_id=? AND wxid=?",
            (group_id, wxid)
        ).fetchone()
    return dict(row) if row else None


def get_all_fish(group_id: int) -> list[dict]:
    """获取群所有鱼（存活优先，按成长值降序）"""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM fish_pond WHERE group_id=?
               ORDER BY is_alive DESC, growth DESC""",
            (group_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_alive_fish(group_id: int) -> list[dict]:
    """获取所有存活的鱼"""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM fish_pond WHERE group_id=? AND is_alive=1
               ORDER BY growth DESC""",
            (group_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def mark_fish_dead(group_id: int, wxid: str) -> bool:
    """标记鱼死亡（鲨鱼事件），保留历史数据"""
    with db() as conn:
        conn.execute(
            """UPDATE fish_pond SET is_alive=0, updated_at=datetime('now')
               WHERE group_id=? AND wxid=?""",
            (group_id, wxid)
        )
    return True


def archive_dead_fish(group_id: int, old_wxid: str, grave_wxid: str) -> bool:
    """归档死鱼：重命名 wxid，为新鱼腾出唯一键。保留全部属性/装备/道具。"""
    with db() as conn:
        conn.execute(
            "UPDATE fish_pond SET wxid=? WHERE group_id=? AND wxid=?",
            (grave_wxid, group_id, old_wxid)
        )
        # 同步 fish_events 中的 wxid
        conn.execute(
            "UPDATE fish_events SET wxid=? WHERE group_id=? AND wxid=?",
            (grave_wxid, group_id, old_wxid)
        )
        # 同步 scale_coin_wallet
        conn.execute(
            "UPDATE scale_coin_wallet SET wxid=? WHERE group_id=? AND wxid=?",
            (grave_wxid, group_id, old_wxid)
        )
        # 同步 fish_inventory
        conn.execute(
            "UPDATE fish_inventory SET wxid=? WHERE group_id=? AND wxid=?",
            (grave_wxid, group_id, old_wxid)
        )
        # 同步 member_portraits 不受影响（按 member_id 关联，不按 wxid）
    return True


# v0.13.0: 白名单校验，防止 SQL 注入
_FISH_FIELD_WHITELIST = {
    "fish_name", "species", "rarity",
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
    "experience", "level", "growth", "happiness", "hp", "stage",
    "consecutive_days", "last_active_date", "last_fed_date", "is_alive",
    "equipped_item", "active_consumable",
    "energy", "max_energy", "personality_traits", "emoji_variant",  # v1.16.0
    "max_hp",  # v1.16.3
    "legendary_quest_step",  # v1.16.4
}


def update_fish_field(group_id: int, wxid: str, field: str, value):
    """更新鱼的单字段（白名单校验防注入）"""
    if field not in _FISH_FIELD_WHITELIST:
        raise ValueError(f"非法字段名: {field}")
    with db() as conn:
        conn.execute(
            f"""UPDATE fish_pond SET {field}=?, updated_at=datetime('now')
                WHERE group_id=? AND wxid=?""",
            (value, group_id, wxid)
        )


def update_fish_multi(group_id: int, wxid: str, updates: dict):
    """更新鱼的多个字段"""
    if not updates:
        return
    # v1.2.11: 字段白名单校验，防 SQL 注入
    for k in updates:
        if k not in _FISH_FIELD_WHITELIST:
            raise ValueError(f"非法字段名: {k}")
    with db() as conn:
        sets = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values())
        conn.execute(
            f"UPDATE fish_pond SET {sets}, updated_at=datetime('now') "
            f"WHERE group_id=? AND wxid=?",
            (*values, group_id, wxid)
        )


# v1.16.0: 精力系统 CRUD

def update_fish_energy(group_id: int, wxid: str, amount: int):
    """增减鱼的精力值（正数=消耗，负数=恢复），自动 clamp 到 [0, max_energy]"""
    with db() as conn:
        conn.execute(
            """UPDATE fish_pond SET energy = MAX(0, MIN(max_energy, energy - ?)),
               updated_at = datetime('now')
               WHERE group_id = ? AND wxid = ?""",
            (amount, group_id, wxid)
        )


def get_fish_traits(group_id: int, wxid: str) -> list:
    """获取鱼的性格特性列表（解析 JSON）"""
    fish = get_fish(group_id, wxid)
    if not fish or not fish.get("personality_traits"):
        return []
    import json
    traits_raw = fish["personality_traits"]
    try:
        return json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
    except (json.JSONDecodeError, TypeError):
        return []


def get_total_coins_in_group(group_id: int) -> int:
    """获取群内所有鳞币总和"""
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(balance), 0) FROM scale_coin_wallet WHERE group_id = ?",
            (group_id,)
        ).fetchone()
    return row[0] if row else 0


# ==================== v1.16.1: 鱼塘金库 CRUD ====================

def get_treasury(group_id: int) -> dict:
    """获取金库余额，不存在则返回默认值"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM pond_treasury WHERE group_id = ?", (group_id,)
        ).fetchone()
    if row:
        return dict(row)
    return {"group_id": group_id, "balance": 0, "total_earned": 0, "total_spent": 0}


def add_treasury(group_id: int, amount: int, reason: str, desc: str = ""):
    """金库收支（正=收入，负=支出），自动写流水"""
    with db() as conn:
        conn.execute(
            """INSERT INTO pond_treasury (group_id, balance, total_earned, total_spent)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(group_id) DO UPDATE SET
               balance = CASE WHEN ? >= 0 THEN balance + ? ELSE balance + ? END,
               total_earned = CASE WHEN ? >= 0 THEN total_earned + ? ELSE total_earned END,
               total_spent = CASE WHEN ? < 0 THEN total_spent + ? ELSE total_spent END""",
            (group_id, max(0, amount), max(0, amount), max(0, -amount),
             amount, amount, amount, amount, amount, amount, amount)
        )
        conn.execute(
            """INSERT INTO pond_treasury_log (group_id, amount, reason, description)
               VALUES (?, ?, ?, ?)""",
            (group_id, amount, reason, desc)
        )


def get_treasury_log(group_id: int, limit: int = 20) -> list[dict]:
    """获取金库流水"""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM pond_treasury_log WHERE group_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (group_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


# ==================== v1.16.2: 升级 + 决议 CRUD ====================

def get_upgrades(group_id: int) -> list[dict]:
    """获取鱼塘所有升级状态"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM pond_upgrades WHERE group_id = ?", (group_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def set_upgrade(group_id: int, upgrade_key: str, level: int):
    """设置某升级项的等级"""
    with db() as conn:
        conn.execute(
            """INSERT INTO pond_upgrades (group_id, upgrade_key, level)
               VALUES (?, ?, ?)
               ON CONFLICT(group_id, upgrade_key) DO UPDATE SET level = ?""",
            (group_id, upgrade_key, level, level)
        )


def count_today_decrees(group_id: int, decree_key: str,
                        date_str: str = None) -> int:
    """统计某决议今日已使用次数"""
    from datetime import datetime as dt
    today = date_str or dt.now().strftime("%Y-%m-%d")
    with db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM fish_events
               WHERE group_id=? AND event_type=?
               AND date(created_at)=?""",
            (group_id, f"decree_{decree_key}", today)
        ).fetchone()
    return row["cnt"] if row else 0


# ==================== 鱼塘事件 CRUD ====================

def add_fish_event(group_id: int, wxid: str, event_type: str,
                   event_data: dict = None) -> int:
    """记录鱼塘事件"""
    import json
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO fish_events (group_id, wxid, event_type, event_data)
               VALUES (?, ?, ?, ?)""",
            (group_id, wxid, event_type,
             json.dumps(event_data, ensure_ascii=False) if event_data else "")
        )
        eid = cur.lastrowid
    return eid


def get_fish_events(group_id: int, wxid: str = "", limit: int = 20) -> list[dict]:
    """获取鱼塘事件列表"""
    with db() as conn:
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
    return [dict(r) for r in rows]


# ==================== 鱼际关系 CRUD (v1.16.4) ====================

def upsert_fish_relationship(group_id: int, wxid_a: str, wxid_b: str,
                              relation_type: str, strength: int = 1):
    """创建或更新鱼际关系（强度累加）"""
    # 确保 a < b 避免双向重复
    if wxid_a > wxid_b:
        wxid_a, wxid_b = wxid_b, wxid_a
    with db() as conn:
        existing = conn.execute(
            """SELECT id, strength FROM fish_relationships
               WHERE group_id=? AND fish_wxid_a=? AND fish_wxid_b=? AND relation_type=?""",
            (group_id, wxid_a, wxid_b, relation_type)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE fish_relationships SET strength=?, created_at=CURRENT_TIMESTAMP WHERE id=?",
                (existing["strength"] + strength, existing["id"])
            )
        else:
            conn.execute(
                """INSERT INTO fish_relationships
                   (group_id, fish_wxid_a, fish_wxid_b, relation_type, strength)
                   VALUES (?, ?, ?, ?, ?)""",
                (group_id, wxid_a, wxid_b, relation_type, strength)
            )


def get_fish_relationships(group_id: int, wxid: str) -> list[dict]:
    """获取某鱼的所有关系（含对方鱼信息）"""
    with db() as conn:
        rows = conn.execute(
            """SELECT fr.*, fp.fish_name, fp.species, fp.emoji_variant
               FROM fish_relationships fr
               LEFT JOIN fish_pond fp ON fp.group_id = fr.group_id
                 AND (fp.wxid = CASE WHEN fr.fish_wxid_a = ? THEN fr.fish_wxid_b ELSE fr.fish_wxid_a END)
                 AND fp.is_alive = 1
               WHERE fr.group_id = ?
                 AND (fr.fish_wxid_a = ? OR fr.fish_wxid_b = ?)
               ORDER BY fr.strength DESC""",
            (wxid, group_id, wxid, wxid)
        ).fetchall()
    result = []
    for r in rows:
        # 确定对方 wxid 和方向
        if r["fish_wxid_a"] == wxid:
            other_wxid = r["fish_wxid_b"]
        else:
            other_wxid = r["fish_wxid_a"]
        result.append({
            "relation_type": r["relation_type"],
            "strength": r["strength"],
            "other_wxid": other_wxid,
            "other_name": r["fish_name"] or "?",
            "other_species": r["species"] or "",
            "other_emoji": r["emoji_variant"] or "",
        })
    return result


# ==================== 鳞币 CRUD ====================

def get_coin_wallet(group_id: int, wxid: str) -> dict:
    """获取鳞币钱包，不存在则返回默认值"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM scale_coin_wallet WHERE group_id=? AND wxid=?",
            (group_id, wxid)
        ).fetchone()
    if row:
        return dict(row)
    return {"group_id": group_id, "wxid": wxid, "balance": 0,
            "total_earned": 0, "total_spent": 0}


def ensure_coin_wallet(group_id: int, wxid: str) -> dict:
    """确保钱包存在，不存在则创建"""
    with db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO scale_coin_wallet (group_id, wxid)
               VALUES (?, ?)""",
            (group_id, wxid)
        )
    return get_coin_wallet(group_id, wxid)


def earn_coins(group_id: int, wxid: str, amount: int,
               reason: str, description: str = "") -> dict:
    """获得鳞币（v0.13.1: 加事务保护，v1.2.11: 统一使用 db() contextmanager）"""
    ensure_coin_wallet(group_id, wxid)
    with db() as conn:
        conn.execute("BEGIN")  # 显式事务确保 UPDATE+INSERT 原子性
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
    return get_coin_wallet(group_id, wxid)


def spend_coins(group_id: int, wxid: str, amount: int,
                reason: str, description: str = "") -> dict | None:
    """消费鳞币，余额不足返回 None（v0.13.1: 加事务保护，v1.2.11: 统一使用 db() contextmanager）"""
    wallet = ensure_coin_wallet(group_id, wxid)
    if wallet["balance"] < amount:
        return None
    with db() as conn:
        conn.execute("BEGIN")  # 显式事务确保 UPDATE+INSERT 原子性
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
    return get_coin_wallet(group_id, wxid)


def get_coin_transactions(group_id: int, wxid: str, limit: int = 20) -> list[dict]:
    """获取鳞币流水"""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM scale_coin_transactions
               WHERE group_id=? AND wxid=?
               ORDER BY created_at DESC LIMIT ?""",
            (group_id, wxid, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_coin_leaderboard(group_id: int, limit: int = 10) -> list[dict]:
    """鳞币排行榜"""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM scale_coin_wallet WHERE group_id=?
               ORDER BY balance DESC LIMIT ?""",
            (group_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


# ==================== 道具库存 v0.9.3 CRUD ====================

def get_inventory(group_id: int, wxid: str) -> list[dict]:
    """获取库存"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM fish_inventory WHERE group_id=? AND wxid=? AND quantity > 0",
            (group_id, wxid)
        ).fetchall()
    return [dict(r) for r in rows]


def add_item(group_id: int, wxid: str, item_key: str, qty: int = 1):
    """添加道具到库存"""
    with db() as conn:
        conn.execute(
            """INSERT INTO fish_inventory (group_id, wxid, item_key, quantity)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(group_id, wxid, item_key) DO UPDATE SET
               quantity = quantity + excluded.quantity""",
            (group_id, wxid, item_key, qty)
        )


def remove_item(group_id: int, wxid: str, item_key: str, qty: int = 1) -> bool:
    """从库存移除道具，返回是否成功"""
    with db() as conn:
        row = conn.execute(
            "SELECT quantity FROM fish_inventory WHERE group_id=? AND wxid=? AND item_key=?",
            (group_id, wxid, item_key)
        ).fetchone()
        if not row or row["quantity"] < qty:
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
    return True


# ==================== 黑市 v0.9.3 CRUD ====================

def set_black_market(group_id: int, date: str, items: list[dict]):
    """设置某天黑市商品"""
    with db() as conn:
        conn.execute("DELETE FROM fish_black_market WHERE group_id=? AND date=?",
                     (group_id, date))
        for item in items:
            conn.execute(
                """INSERT INTO fish_black_market (group_id, date, item_key, price, stock, stock_remaining)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (group_id, date, item["key"], item["price"], item["stock"], item["stock"])
            )


def get_black_market(group_id: int, date: str) -> list[dict]:
    """获取某天黑市商品"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM fish_black_market WHERE group_id=? AND date=? AND stock_remaining > 0",
            (group_id, date)
        ).fetchall()
    return [dict(r) for r in rows]


def buy_from_market(group_id: int, wxid: str, date: str,
                    item_key: str) -> dict | None:
    """从黑市购买，返回商品信息或 None"""
    with db() as conn:
        row = conn.execute(
            """SELECT * FROM fish_black_market
               WHERE group_id=? AND date=? AND item_key=? AND stock_remaining > 0""",
            (group_id, date, item_key)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """UPDATE fish_black_market SET stock_remaining = stock_remaining - 1
               WHERE id=?""", (row["id"],)
        )
    return dict(row)


# ==================== 模型配置 CRUD v0.12.0 ====================

def list_model_configs() -> list[dict]:
    """列出所有模型配置，按 model_type + is_default desc 排序"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM model_configs ORDER BY model_type, is_default DESC, id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_model_config(config_id: int) -> dict | None:
    """获取单个模型配置"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM model_configs WHERE id=?", (config_id,)
        ).fetchone()
    return dict(row) if row else None


def create_model_config(name: str, model_type: str, endpoint: str = "",
                        api_key: str = "", model_name: str = "",
                        is_default: bool = False, extra_params: str = "") -> int:
    """创建模型配置，返回新 ID。若 is_default=True，先清除同类型其他默认"""
    with db() as conn:
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
        new_id = cur.lastrowid
    return new_id


def update_model_config(config_id: int, **kwargs) -> bool:
    """部分更新模型配置。自动维护 is_default 唯一性"""
    allowed = {"name", "model_type", "endpoint", "api_key", "model_name",
               "is_default", "extra_params", "is_enabled"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return False

    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM model_configs WHERE id=?", (config_id,)
        ).fetchone()
        if not existing:
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
    return True


def delete_model_config(config_id: int) -> bool:
    """删除模型配置。若删除的是默认，自动提升同类型第一条为默认"""
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM model_configs WHERE id=?", (config_id,)
        ).fetchone()
        if not existing:
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

    return True


def get_default_model(model_type: str) -> dict | None:
    """获取某类型的默认配置（已启用）"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM model_configs WHERE model_type=? AND is_default=1 AND is_enabled=1 "
            "ORDER BY id ASC LIMIT 1",
            (model_type,)
        ).fetchone()
    return dict(row) if row else None


# ==================== 应用设置 CRUD v1.0.2 ====================

def get_app_setting(key: str) -> dict | None:
    """获取单个应用设置"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM app_settings WHERE key=?", (key,)
        ).fetchone()
    return dict(row) if row else None


def get_all_app_settings() -> list[dict]:
    """列出所有应用设置，敏感字段脱敏"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM app_settings ORDER BY key"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("is_sensitive") and d.get("value"):
            from services.model_config import mask_api_key
            d["value"] = mask_api_key(d["value"])
        result.append(d)
    return result


def upsert_app_setting(key: str, value: str) -> bool:
    """插入或更新单个应用设置。v1.2.8: INSERT 时从注册表确定 value_type，避免误写为 'string'"""
    registry = _get_settings_registry()
    type_info = registry.get(key)
    value_type = type_info[1] if type_info else "string"

    with db() as conn:
        conn.execute(
            """INSERT INTO app_settings (key, value, value_type, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               value_type = excluded.value_type,
               updated_at = CURRENT_TIMESTAMP""",
            (key, value, value_type)
        )
    return True


def upsert_app_settings_batch(updates: dict[str, str]) -> bool:
    """批量更新应用设置"""
    if not updates:
        return False
    registry = _get_settings_registry()
    with db() as conn:
        for key, value in updates.items():
            type_info = registry.get(key)
            value_type = type_info[1] if type_info else "string"
            conn.execute(
                """INSERT INTO app_settings (key, value, value_type, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   value_type = excluded.value_type,
                   updated_at = CURRENT_TIMESTAMP""",
                (key, value, value_type)
            )
    return True


def get_stopwords_text() -> str:
    """v1.0.2: 从 DB 获取停用词文本内容"""
    setting = get_app_setting("stopwords_text")
    return setting["value"] if setting else ""


def load_app_settings_to_config():
    """v1.0.2: 从 DB 加载可热更新设置到 config 对象（启动时调用）。

    只更新可热加载的设置；HOST/PORT/DATA_DIR/DATABASE_PATH/LOG_DIR 等
    运行时不可变设置不受影响。
    """
    from config import config

    with db() as conn:
        rows = conn.execute(
            "SELECT key, value, value_type FROM app_settings"
        ).fetchall()

    type_map = {
        "int": int,
        "float": float,
        "bool": lambda v: v.lower() in ("true", "1", "yes"),
        "string": str,
    }

    KEY_ATTR_MAP = {
        "ollama_timeout": "OLLAMA_TIMEOUT",
        "gpu_lock_enabled": "GPU_LOCK_ENABLED",
        "gpu_lock_url": "GPU_LOCK_URL",
        "gpu_lock_who": "GPU_LOCK_WHO",
        "gpu_lock_retry_interval": "GPU_LOCK_RETRY_INTERVAL",
        "gpu_lock_max_retries": "GPU_LOCK_MAX_RETRIES",
        "online_retry_count": "ONLINE_RETRY_COUNT",
        "deepseek_timeout": "DEEPSEEK_TIMEOUT",
        "weekly_temperature": "WEEKLY_TEMPERATURE",
        "monthly_temperature": "MONTHLY_TEMPERATURE",
        "deepseek_max_tokens_weekly": "DEEPSEEK_MAX_TOKENS_WEEKLY",
        "deepseek_max_tokens_monthly": "DEEPSEEK_MAX_TOKENS_MONTHLY",
        "portrait_refresh_days": "PORTRAIT_REFRESH_DAYS",
        # v1.17.0: 本地大模型全局开关 + 管道执行参数
        "local_llm_enabled": "LOCAL_LLM_ENABLED",
        "local_llm_host": "LOCAL_LLM_HOST",
        "local_llm_fallback_model": "LOCAL_LLM_FALLBACK_MODEL",
        "pipeline_max_retries": "PIPELINE_MAX_RETRIES",
        "pipeline_step_timeout": "PIPELINE_STEP_TIMEOUT",
        "pipeline_circuit_breaker_threshold": "PIPELINE_CIRCUIT_BREAKER_THRESHOLD",
        "pipeline_circuit_breaker_cooldown": "PIPELINE_CIRCUIT_BREAKER_COOLDOWN",
        # 周期报告可用性阈值
        "weekly_min_days": "WEEKLY_MIN_DAYS",
        "weekly_min_msgs": "WEEKLY_MIN_MSGS",
        "monthly_min_days": "MONTHLY_MIN_DAYS",
        "monthly_min_msgs": "MONTHLY_MIN_MSGS",
        "annual_min_days": "ANNUAL_MIN_DAYS",
        "annual_min_msgs": "ANNUAL_MIN_MSGS",
        # WeFlow 增量同步
        "weflow_enabled": "WEFLOW_ENABLED",
        "weflow_base_url": "WEFLOW_BASE_URL",
        "weflow_access_token": "WEFLOW_ACCESS_TOKEN",
        "weflow_sync_interval_hours": "WEFLOW_SYNC_INTERVAL_HOURS",
        # v1.16.0: 鱼塘精力系统
        "pond_energy_regen_amount": "POND_ENERGY_REGEN_AMOUNT",
        "pond_touch_daily_limit": "POND_TOUCH_DAILY_LIMIT",
        # v1.16.1: 鱼塘自动化
        "pond_auto_events_enabled": "POND_AUTO_EVENTS_ENABLED",
        "pond_event_interval_minutes": "POND_EVENT_INTERVAL_MINUTES",
        "pond_treasury_tax_rate": "POND_TREASURY_TAX_RATE",
        # v1.16.4: 公告牌 + 创意工坊
        "pond_bulletin_board": "POND_BULLETIN_BOARD",
        "custom_flavor_texts": "CUSTOM_FLAVOR_TEXTS",
        "custom_last_words": "CUSTOM_LAST_WORDS",
        "custom_daily_status": "CUSTOM_DAILY_STATUS",
        # v1.16.5: 作弊模式
        "pond_cheat_mode": "POND_CHEAT_MODE",
        "pond_cheat_weather_override": "POND_CHEAT_WEATHER_OVERRIDE",
        # 日志清理
        "log_retention_days": "LOG_RETENTION_DAYS",
        "log_max_records": "LOG_MAX_RECORDS",
        # v1.18.0: 事件探测
        # v1.18.0 配置项（event_window_size/overlap/ai_concurrency 已在 v1.18.1 废弃）
        "event_active_group_threshold": "EVENT_ACTIVE_GROUP_THRESHOLD",
        "event_active_peak_absolute": "EVENT_ACTIVE_PEAK_ABSOLUTE",
        "event_quiet_peak_multiplier": "EVENT_QUIET_PEAK_MULTIPLIER",
        # v1.18.1: 自适应事件组切分
        "event_min_gap_minutes": "EVENT_MIN_GAP_MINUTES",
        "event_min_group_size": "EVENT_MIN_GROUP_SIZE",
        "event_max_group_size": "EVENT_MAX_GROUP_SIZE",
    }

    for row in rows:
        key = row["key"]
        attr = KEY_ATTR_MAP.get(key)
        if not attr:
            continue
        converter = type_map.get(row["value_type"], str)
        try:
            setattr(config, attr, converter(row["value"]))
        except (ValueError, TypeError):
            logger.warning(f'DB 设置 {key} 值转换失败({row["value"]})，使用默认值')
            pass


# ==================== Personas v1.5.0 ====================

def auto_link_by_wxid() -> int:
    """自动关联：为同一 wxid 出现在多个群的成员创建 persona。

    纯增量操作：已有 persona 的成员跳过，只处理未关联的成员。
    返回新创建的 persona 数量。
    """
    with db() as conn:
        # 找出在多个群出现、且未加入任何 persona 的 wxid
        rows = conn.execute("""
            SELECT gm.wxid, COUNT(DISTINCT gm.group_id) AS group_cnt
            FROM group_members gm
            LEFT JOIN persona_members pm ON gm.id = pm.member_id
            WHERE gm.wxid != ''
              AND gm.wxid NOT LIKE 'fallback_%'
              AND gm.wxid NOT LIKE 'unknown_%'
              AND pm.id IS NULL
            GROUP BY gm.wxid
            HAVING group_cnt >= 2
        """).fetchall()

        created = 0
        for row in rows:
            wxid = row["wxid"]
            # 为该 wxid 创建 persona
            cur = conn.execute(
                "INSERT INTO personas (name) VALUES (?)",
                (wxid,)
            )
            persona_id = cur.lastrowid
            # 关联所有匹配的 member
            conn.execute("""
                INSERT INTO persona_members (persona_id, member_id)
                SELECT ?, gm.id FROM group_members gm
                LEFT JOIN persona_members pm ON gm.id = pm.member_id
                WHERE gm.wxid = ? AND pm.id IS NULL
            """, (persona_id, wxid))
            created += 1

        if created:
            logger.info(f"auto_link_by_wxid: 创建 {created} 个 persona")
        return created


def create_persona(name: str = "") -> int:
    """创建空 persona，返回 persona_id"""
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO personas (name) VALUES (?)", (name,)
        )
        return cur.lastrowid


def link_member_to_persona(persona_id: int, member_id: int) -> bool:
    """将 member 关联到 persona。若 member 已属于其他 persona，先自动解除旧关联。"""
    with db() as conn:
        # 检查 persona 和 member 是否存在
        persona = conn.execute(
            "SELECT id FROM personas WHERE id=?", (persona_id,)
        ).fetchone()
        if not persona:
            return False
        member = conn.execute(
            "SELECT id, display_name FROM group_members WHERE id=?", (member_id,)
        ).fetchone()
        if not member:
            return False
        # 如果已在其他 persona 中则先移除（一个 member 只能属于一个 persona）
        conn.execute(
            "DELETE FROM persona_members WHERE member_id=?", (member_id,)
        )
        # 关联
        conn.execute(
            "INSERT OR IGNORE INTO persona_members (persona_id, member_id) VALUES (?, ?)",
            (persona_id, member_id)
        )
        # 如果 persona 还没有名字，用成员的 display_name
        conn.execute("""
            UPDATE personas SET name = (
                SELECT display_name FROM group_members WHERE id=?
            ) WHERE id=? AND (name IS NULL OR name = '')
        """, (member_id, persona_id))
        return True


def unlink_member_from_persona(member_id: int) -> bool:
    """从 persona 中移除 member"""
    with db() as conn:
        cur = conn.execute(
            "DELETE FROM persona_members WHERE member_id=?", (member_id,)
        )
        return cur.rowcount > 0


def get_persona(persona_id: int) -> dict | None:
    """获取 persona 详情，包含所有关联成员及画像"""
    with db() as conn:
        persona = conn.execute(
            "SELECT * FROM personas WHERE id=?", (persona_id,)
        ).fetchone()
        if not persona:
            return None
        members = conn.execute("""
            SELECT gm.*, cg.name AS group_name, cg.platform,
                   mp.portrait_json, mp.last_updated AS portrait_updated
            FROM persona_members pm
            JOIN group_members gm ON pm.member_id = gm.id
            JOIN chat_groups cg ON gm.group_id = cg.id
            LEFT JOIN member_portraits mp ON mp.group_id = gm.group_id AND mp.member_id = gm.id
            WHERE pm.persona_id = ?
            ORDER BY cg.platform, cg.name
        """, (persona_id,)).fetchall()
        result = dict(persona)
        result["members"] = [dict(m) for m in members]
        # v1.5.2: 解析全面画像
        raw = result.get("comprehensive_portrait_json")
        if raw:
            try:
                result["comprehensive_portrait"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                result["comprehensive_portrait"] = None
        else:
            result["comprehensive_portrait"] = None
        return result


def save_comprehensive_portrait(persona_id: int, portrait_json: str):
    """v1.5.2: 保存全面画像"""
    with db() as conn:
        conn.execute(
            """UPDATE personas SET comprehensive_portrait_json=?,
               comprehensive_portrait_updated=? WHERE id=?""",
            (portrait_json, datetime.now().isoformat(), persona_id)
        )


def get_persona_by_member(member_id: int) -> dict | None:
    """通过 member_id 查找所属 persona"""
    with db() as conn:
        row = conn.execute("""
            SELECT p.* FROM personas p
            JOIN persona_members pm ON p.id = pm.persona_id
            WHERE pm.member_id = ?
        """, (member_id,)).fetchone()
        if not row:
            return None
        return get_persona(row["id"])


def list_personas() -> list[dict]:
    """列出所有 persona，包含成员数量和成员列表"""
    with db() as conn:
        rows = conn.execute("""
            SELECT p.*, COUNT(pm.id) AS member_count
            FROM personas p
            LEFT JOIN persona_members pm ON p.id = pm.persona_id
            GROUP BY p.id
            ORDER BY member_count DESC, p.created_at DESC
        """).fetchall()
        personas = []
        for r in rows:
            p = dict(r)
            # 加载每个 persona 的成员列表
            members = conn.execute("""
                SELECT gm.*, cg.name AS group_name, cg.platform
                FROM persona_members pm
                JOIN group_members gm ON pm.member_id = gm.id
                JOIN chat_groups cg ON gm.group_id = cg.id
                WHERE pm.persona_id = ?
                ORDER BY cg.platform, cg.name
            """, (p["id"],)).fetchall()
            p["members"] = [dict(m) for m in members]
            # v1.5.2: 解析全面画像
            raw = p.get("comprehensive_portrait_json")
            if raw:
                try:
                    p["comprehensive_portrait"] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    p["comprehensive_portrait"] = None
            else:
                p["comprehensive_portrait"] = None
            personas.append(p)
    return personas


def merge_personas(from_id: int, to_id: int) -> bool:
    """原子合并：将 from_id 的所有成员移至 to_id，删除 from。单事务防竞态。"""
    if from_id == to_id:
        return False
    with db() as conn:
        to_exists = conn.execute(
            "SELECT id FROM personas WHERE id=?", (to_id,)
        ).fetchone()
        from_exists = conn.execute(
            "SELECT id FROM personas WHERE id=?", (from_id,)
        ).fetchone()
        if not to_exists or not from_exists:
            return False
        # 获取 from 的所有成员
        members = conn.execute(
            "SELECT member_id FROM persona_members WHERE persona_id=?",
            (from_id,)
        ).fetchall()
        # 逐个重链（先删旧关联，再插新，防 UNIQUE 冲突）
        for m in members:
            conn.execute(
                "DELETE FROM persona_members WHERE member_id=?", (m["member_id"],)
            )
            conn.execute(
                "INSERT OR IGNORE INTO persona_members (persona_id, member_id) VALUES (?, ?)",
                (to_id, m["member_id"])
            )
        conn.execute("DELETE FROM personas WHERE id=?", (from_id,))
    return True


def delete_persona(persona_id: int) -> bool:
    """删除 persona（CASCADE 自动清理 persona_members）"""
    with db() as conn:
        cur = conn.execute("DELETE FROM personas WHERE id=?", (persona_id,))
        return cur.rowcount > 0


def get_cross_group_members(wxid: str) -> list[dict]:
    """获取同一 wxid 在不同群的 member 记录及其画像（用于跨群对比）"""
    with db() as conn:
        rows = conn.execute("""
            SELECT gm.*, cg.name AS group_name, cg.platform,
                   mp.portrait_json, mp.last_updated AS portrait_updated,
                   mp.total_analyzed_messages
            FROM group_members gm
            JOIN chat_groups cg ON gm.group_id = cg.id
            LEFT JOIN member_portraits mp ON mp.group_id = gm.group_id AND mp.member_id = gm.id
            WHERE gm.wxid = ? AND cg.status = 'active'
            ORDER BY cg.platform, cg.name
        """, (wxid,)).fetchall()
    return [dict(r) for r in rows]


def get_cross_group_wxids() -> list[dict]:
    """列出所有在多个群出现的 wxid（用于前端发现可跨群对比的成员）"""
    with db() as conn:
        rows = conn.execute("""
            SELECT gm.wxid, COUNT(DISTINCT gm.group_id) AS group_cnt,
                   GROUP_CONCAT(DISTINCT gm.display_name) AS names,
                   GROUP_CONCAT(DISTINCT cg.name) AS groups
            FROM group_members gm
            JOIN chat_groups cg ON gm.group_id = cg.id
            WHERE gm.wxid != ''
              AND gm.wxid NOT LIKE 'fallback_%'
              AND gm.wxid NOT LIKE 'unknown_%'
              AND cg.status = 'active'
            GROUP BY gm.wxid
            HAVING group_cnt >= 2
            ORDER BY group_cnt DESC
        """).fetchall()
    return [dict(r) for r in rows]

# ==================== Prompt Profiles v1.5.4 ====================

def list_prompt_profiles(analysis_type: str = '') -> list[dict]:
    """列出提示词配置，可按 analysis_type 筛选"""
    with db() as conn:
        if analysis_type:
            rows = conn.execute(
                "SELECT * FROM prompt_profiles WHERE analysis_type=? ORDER BY is_default DESC, id ASC",
                (analysis_type,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM prompt_profiles ORDER BY analysis_type, is_default DESC, id ASC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_prompt_profile(profile_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM prompt_profiles WHERE id=?", (profile_id,)
        ).fetchone()
    return dict(row) if row else None


def create_prompt_profile(name: str, analysis_type: str, system_prompt: str, is_default: bool = False) -> int:
    with db() as conn:
        if is_default:
            conn.execute(
                "UPDATE prompt_profiles SET is_default=0, updated_at=CURRENT_TIMESTAMP WHERE analysis_type=? AND is_default=1",
                (analysis_type,)
            )
        cur = conn.execute(
            "INSERT INTO prompt_profiles (name, analysis_type, system_prompt, is_default) VALUES (?,?,?,?)",
            (name, analysis_type, system_prompt, 1 if is_default else 0)
        )
        return cur.lastrowid


def update_prompt_profile(profile_id: int, **kwargs) -> bool:
    allowed = {"name", "system_prompt", "is_default"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return False
    with db() as conn:
        existing = conn.execute("SELECT * FROM prompt_profiles WHERE id=?", (profile_id,)).fetchone()
        if not existing:
            return False
        if fields.get("is_default"):
            conn.execute(
                "UPDATE prompt_profiles SET is_default=0, updated_at=CURRENT_TIMESTAMP WHERE analysis_type=? AND is_default=1 AND id!=?",
                (existing["analysis_type"], profile_id)
            )
        fields["updated_at"] = datetime.now().isoformat()
        sets = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [profile_id]
        conn.execute(f"UPDATE prompt_profiles SET {sets} WHERE id=?", values)
    return True


def delete_prompt_profile(profile_id: int) -> bool:
    with db() as conn:
        existing = conn.execute("SELECT * FROM prompt_profiles WHERE id=?", (profile_id,)).fetchone()
        if not existing:
            return False
        conn.execute("DELETE FROM prompt_profiles WHERE id=?", (profile_id,))
        if existing["is_default"]:
            first = conn.execute(
                "SELECT id FROM prompt_profiles WHERE analysis_type=? ORDER BY id ASC LIMIT 1",
                (existing["analysis_type"],)
            ).fetchone()
            if first:
                conn.execute("UPDATE prompt_profiles SET is_default=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (first["id"],))
    return True


def get_default_prompt(analysis_type: str) -> str | None:
    """获取某分析类型的默认 system_prompt，无配置时返回 None（调用方用硬编码 fallback）"""
    with db() as conn:
        row = conn.execute(
            "SELECT system_prompt FROM prompt_profiles WHERE analysis_type=? AND is_default=1 LIMIT 1",
            (analysis_type,)
        ).fetchone()
    return row["system_prompt"] if row and row["system_prompt"] else None


# ==================== Event Detection v1.18.0 ====================

def insert_events(events: list[dict]) -> list[int]:
    """批量插入事件，返回新插入的事件 ID 列表"""
    ids = []
    with db() as conn:
        for e in events:
            cur = conn.execute("""
                INSERT INTO events (group_id, title, description, event_type,
                    participant_ids, key_quotes, start_time, end_time,
                    message_start_idx, message_end_idx, message_count,
                    ai_model_used, window_id, report_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                e["group_id"],
                e["title"],
                e.get("description", ""),
                e["event_type"],
                e.get("participant_ids", "[]"),
                e.get("key_quotes", "[]"),
                e["start_time"],
                e["end_time"],
                e.get("message_start_idx", 0),
                e.get("message_end_idx", 0),
                e.get("message_count", 0),
                e.get("ai_model_used", ""),
                e.get("window_id", None),
                e.get("report_json", ""),
            ))
            ids.append(cur.lastrowid)
    return ids


def get_events(group_id: int, event_type: str = "",
               date_from: str = "", date_to: str = "") -> list[dict]:
    """查询事件列表，支持类型和时间范围筛选"""
    with db() as conn:
        sql = "SELECT * FROM events WHERE group_id=?"
        params = [group_id]
        if event_type:
            sql += " AND event_type=?"
            params.append(event_type)
        if date_from:
            sql += " AND start_time >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND end_time <= ?"
            params.append(date_to + "T23:59:59")
        sql += " ORDER BY start_time DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_event(event_id: int) -> dict | None:
    """获取单个事件详情"""
    with db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    return dict(row) if row else None


def delete_events_in_range(group_id: int, date_start: str, date_end: str) -> int:
    """删除指定时间范围内的所有事件，返回删除数量。分析时先删旧再写新。"""
    with db() as conn:
        cur = conn.execute(
            "DELETE FROM events WHERE group_id=? AND start_time >= ? AND end_time <= ?",
            (group_id, date_start, date_end + "T23:59:59")
        )
        return cur.rowcount


def get_events_by_member(group_id: int, member_id: int) -> list[dict]:
    """获取某成员参与的所有事件（participant_ids JSON 数组包含该 member_id）"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE group_id=? AND participant_ids LIKE ? ORDER BY start_time DESC",
            (group_id, f'%{member_id}%')
        ).fetchall()
    # 二次过滤：确保 member_id 在 JSON 数组中（避免 LIKE 误匹配）
    import json
    result = []
    for row in rows:
        d = dict(row)
        try:
            pids = json.loads(d["participant_ids"])
            if member_id in pids:
                result.append(d)
        except (json.JSONDecodeError, KeyError):
            continue
    return result


# ==================== Event Windows v1.18.1 ====================

def insert_windows(windows: list[dict], group_id: int) -> list[int]:
    """批量插入事件窗口，返回新插入的窗口 ID 列表"""
    ids = []
    with db() as conn:
        for w in windows:
            cur = conn.execute("""
                INSERT INTO event_windows (group_id, start_time, end_time,
                    message_count, status, summary_json)
                VALUES (?, ?, ?, ?, 'pending', ?)
            """, (
                group_id,
                w["start_time"],
                w["end_time"],
                w.get("message_count", 0),
                w.get("summary_json", "{}"),
            ))
            ids.append(cur.lastrowid)
    return ids


def get_windows(group_id: int, status: str = "") -> list[dict]:
    """获取事件窗口列表，支持按状态筛选，按 start_time 倒序"""
    with db() as conn:
        sql = "SELECT * FROM event_windows WHERE group_id=?"
        params = [group_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY start_time DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_window(window_id: int) -> dict | None:
    """获取单个事件窗口"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM event_windows WHERE id=?", (window_id,)
        ).fetchone()
    return dict(row) if row else None


def update_window_status(window_id: int, status: str,
                         event_count: int = 0, event_id: int = None):
    """更新事件窗口状态。analyzed 时自动设置 analyzed_at 时间戳。"""
    with db() as conn:
        if status in ("analyzed", "empty"):
            conn.execute("""
                UPDATE event_windows SET status=?, event_count=?,
                    event_id=?, analyzed_at=datetime('now','localtime')
                WHERE id=?
            """, (status, event_count, event_id, window_id))
        else:
            conn.execute("""
                UPDATE event_windows SET status=?, event_count=?, event_id=?
                WHERE id=?
            """, (status, event_count, event_id, window_id))
    return True


def get_pending_windows_count(group_id: int) -> int:
    """获取待处理窗口数量"""
    with db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM event_windows "
            "WHERE group_id=? AND status='pending'",
            (group_id,)
        ).fetchone()
    return row["cnt"] if row else 0


def delete_windows_by_group(group_id: int, only_pending: bool = False):
    """删除群的事件窗口。only_pending=True 时只删除未分析的窗口。"""
    with db() as conn:
        if only_pending:
            conn.execute(
                "DELETE FROM event_windows WHERE group_id=? AND status IN ('pending','empty')",
                (group_id,))
        else:
            conn.execute("DELETE FROM event_windows WHERE group_id=?", (group_id,))


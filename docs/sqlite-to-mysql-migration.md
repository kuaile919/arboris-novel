# SQLite 到 MySQL 迁移（不漏表/不漏字段）

项目已经支持 `DB_PROVIDER=mysql`，并提供了全量迁移脚本：

- `backend/scripts/migrate_sqlite_to_mysql.py`

脚本会完成 4 件事：

1. 自动创建目标 MySQL 数据库。
2. 用应用当前最新 schema 初始化目标库。
3. 从 SQLite 全量复制业务表数据到 MySQL。
4. 生成迁移报告，列出表差异、字段差异、行数对比和错误信息。

## 1. 迁移前准备（宝塔服务器）

1. 停止后端写入，避免迁移过程中源库继续变化。
2. 备份 SQLite：

```bash
sqlite3 /usr/app/arboris-novel/backend/storage/arboris.db ".backup '/tmp/arboris_backup.db'"
```

3. 确认宝塔中已创建以下 MySQL 信息：

```text
Host: 123.207.213.21
Port: 3306
User: arboris-novel
Database: arboris-novel
```

4. 确认数据库账号已授权，并且如果你从本地机器执行迁移，服务器安全组、防火墙、宝塔数据库权限都已放通 `3306`。

## 2. 执行迁移

在项目根目录执行：

```bash
cd /usr/app/arboris-novel

export MYSQL_PASSWORD='你的密码'

python backend/scripts/migrate_sqlite_to_mysql.py \
  --sqlite-path backend/storage/arboris.db \
  --mysql-host 123.207.213.21 \
  --mysql-port 3306 \
  --mysql-user arboris-novel \
  --mysql-db arboris-novel \
  --truncate-target
```

说明：

- 密码不要写入仓库，使用 `MYSQL_PASSWORD` 环境变量或运行时传入 `--mysql-password`。
- `--mysql-host` 必须填写裸 IP 或域名，例如 `123.207.213.21`，不要写成 `http://123.207.213.21/`。
- 如果目标库已经由宝塔提前创建，可以追加 `--skip-create-db`，避免脚本和初始化流程再次执行 `CREATE DATABASE`。
- 如果迁移脚本就是在同一台宝塔服务器上执行，也可以把 `--mysql-host` 改成 `127.0.0.1`。
- `--truncate-target` 适合首次全量迁移，会先清空目标表再导入，避免主键冲突。
- 如果目标库已有重要数据，先不要加 `--truncate-target`，先查看报告再决定。

## 3. 默认参数

脚本默认会优先读取环境变量：

```env
MYSQL_HOST=123.207.213.21
MYSQL_PORT=3306
MYSQL_USER=arboris-novel
MYSQL_DATABASE=arboris-novel
```

如果没有设置环境变量，脚本也会回退到上述默认值。密码仍然必须通过 `MYSQL_PASSWORD` 或 `--mysql-password` 提供。

## 4. 查看迁移报告

默认报告路径：

- `backend/storage/logs/sqlite_to_mysql_report.json`

重点检查这些字段：

- `source_only_tables`: 只在 SQLite 存在的表
- `target_only_tables`: 只在 MySQL 存在的表
- `table_results[].source_only_columns`: SQLite 有但 MySQL 没有的字段
- `table_results[].target_only_columns`: MySQL 有但 SQLite 没有的字段
- `table_results[].source_rows / target_rows / copied_rows`
- `errors`

## 5. 切换应用到 MySQL

在后端 `.env` 或宝塔环境变量中设置：

```env
DB_PROVIDER=mysql
MYSQL_HOST=123.207.213.21
MYSQL_PORT=3306
MYSQL_USER=arboris-novel
MYSQL_PASSWORD=你的密码
MYSQL_DATABASE=arboris-novel
```

然后重启后端服务。

## 6. 验证

1. 登录系统，检查已有项目、章节、配置是否完整。
2. 新建项目并写入一章，确认写入 MySQL 正常。
3. 检查后台关键配置项和管理账号是否可用。

## 7. 注意事项

1. 该脚本只迁移主业务库 `arboris.db`。
2. 向量库 `rag_vectors.db` 仍然保持 `libsql/SQLite` 路线，不在本次迁移范围内。
3. 如果报告中出现 `source_only_columns`，说明 SQLite 中存在 MySQL 还没有的字段，需要补齐后再复查。

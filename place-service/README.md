# 私有地点服务

该服务是旅行 Agent 的第一层地点检索，EdgeOne Makers 通过 HTTPS + Bearer Token 调用；未命中时才使用腾讯地图 WebService API。

## 数据范围

- 中国主体数据：从 OpenStreetMap 分省 PBF 中只保留具名城市/乡镇、景点、古迹、自然地标和交通枢纽。餐馆、酒店、商店等高频变化商业 POI 交给腾讯地图 WebService，避免自有库迅速过期并显著降低磁盘占用。
- 国外著名地点：补充 GeoNames 中人口较高的城市以及重要自然、人文地标；不足部分由腾讯海外地点搜索补足。
- 数据保留 `source`、`source_region`、`source_updated_at` 和紧凑别名，不保存完整 OSM 原始标签。

数据库结构已针对中文/英文模糊检索和空间查询建立索引。批量导入器应使用 staging 表后执行 UPSERT，避免更新期间出现半成品数据。

## 启动

```bash
cp .env.example .env
# 使用密码生成器替换两个占位值
docker compose up -d --build
curl http://127.0.0.1:8091/healthz
```

## 导入数据

### 中国低磁盘导入（推荐）

导入器会逐个下载分省 PBF，完成数据库写入后立即删除当前文件。默认列表使用包含京津的河北包和包含港澳的广东包，避免重叠下载；失败时保留当前下载，重跑可继续使用。

```bash
docker compose --profile tools run --rm importer import_china_regions.py --resume
```

首次只验证北京或浙江时，可以限制地区：

```bash
docker compose --profile tools run --rm importer import_china_regions.py --regions beijing zhejiang
```

`--resume` 会在持久化工作卷记录每个已完成分区，SSH 中断或单省失败后重跑时会跳过已完成分区。每个分区默认重试三次；某省最终失败后会继续处理后续省份，全部结束后以非零状态列出失败分区。需要定期全量刷新时，不传 `--resume` 即可。每次分区导入都有独立运行标识；整区成功后会清理上次导入中已经从 OSM 删除的旧地点。不要并发导入同一地区。

### 手动文件与国外地标

把手动下载的 OSM PBF 或 GeoNames 压缩包放入 `place-service/data/`，再运行：

```bash
docker compose --profile tools run --rm importer import_osm.py /data/beijing-latest.osm.pbf --region beijing --country-code cn
docker compose --profile tools run --rm importer import_geonames.py /data/allCountries.zip
```

GeoNames 导入器补充人口不少于 5 万的全球城市与重要自然/人文地标。重复导入使用稳定来源 ID UPSERT，可用于月度刷新。

### 从旧结构迁移

如果 Docker 卷曾使用过包含完整 `tags` 的旧表，先执行一次：

```bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /migrations/001_compact_places.sql'
```

迁移会删除旧 OSM 商业 POI、移除完整原始标签并创建紧凑别名索引。删除空间会被后续导入复用；只有磁盘空间充足且能够接受锁表维护窗口时，才单独执行 `VACUUM FULL places` 收缩物理文件。

## 容量口径

`china-latest.osm.pbf` 是压缩的全量 OSM 原始包，不等于本服务的数据库大小。本导入器只保存具名 POI，并为名称、城市分类和空间字段建立索引，因此最终占用取决于当次 OSM 的 POI 数量与标签长度。部署前至少按以下三部分分别预留：原始 PBF、导入过程的临时空间、PostGIS 表与索引。

导入后使用仓库根目录命令查看真实值：

```powershell
npm run stats:places
```

低磁盘模式的原始文件峰值约等于当前最大省级包加 Osmium 位置索引，而不是 1.5 GB 全国包。建议首次执行前仍保留至少 8 GB 可用空间；如果不足，先只导入常用省份。最终是否够用必须以服务器上的 `pg_database_size`、剩余磁盘和单省导入峰值为准。

上线展示 OSM 派生数据时必须按 ODbL 要求提供 OpenStreetMap 贡献者署名，并保留数据来源字段。

生产环境不要直接暴露 PostgreSQL 或 8091 端口。应通过 Caddy/Nginx 提供有效 HTTPS 域名，仅转发 `/v1/places/search` 和 `/healthz`，并在防火墙中关闭数据库公网入口。

在 EdgeOne 项目环境中配置：

```text
PLACE_API_BASE_URL=https://places.example.com
PLACE_API_TOKEN=<与服务端一致的随机令牌>
TENCENT_MAP_SERVER_KEY=<仅启用 WebService API 的服务端密钥>
```

当前旅行 Agent 在未配置 `PLACE_API_BASE_URL` 时使用
`https://94-16-110-28.sslip.io` 作为生产默认回源；迁移到正式域名后应通过环境变量覆盖。

`VITE_TENCENT_MAP_KEY` 只用于浏览器 JS 地图渲染，不能替代 `TENCENT_MAP_SERVER_KEY`。

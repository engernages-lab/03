# V1.1-C.2.2.2 · 03 Railway 部署记录（Phase 3）

- **日期**：2026-11-27

---

## 1. 部署目标确认（部署前）

```text
$ railway status --json
project:  pocketscore-ai       (286a8f6c-86ff-45f0-97e2-28ba955799d4)
services: ['pocketscore-api']  (28d3b430-6b62-4492-b49a-1f29ef2026c2)

$ railway environment list --json
      production 29acdce7-7a32-4f99-b2bf-1e18997ad5a3
LINKED staging   72f62640-3e69-46c7-adb5-81c4fa50a4a1
```

✅ 目标是 **staging**（已 link），production 环境内没有任何服务。
✅ 未触碰 production、未删除 Volume、未清空数据库。

## 2. Volume 确认

| 项 | 值 |
| --- | --- |
| Volume 名 | `pocketscore-api-volume` |
| 挂载点 | `/data`（`RAILWAY_VOLUME_MOUNT_PATH=/data`） |
| 容器内有效路径 | `/data/pocketscore.db` + `/data/storage/` |
| 上限 / 已用 | 500 MB / ≈36 MB（部署前） |
| 是否重建 | ❌ 否（四次部署前后同一卷） |

持久化的真实证明不是"卷存在"，而是重启/重新部署后数据一致 —— 见 `09-persistence-before-after.md`。

## 3. 部署执行

```bash
railway up --ci --service pocketscore-api
```

| 项 | 值 |
| --- | --- |
| 分支 / 提交 | `pocketscore-v1.1-b` / `b1d3ee1`（工作区干净） |
| 构建方式 | Dockerfile（`backend/Dockerfile`，context=仓库根） |
| 上传快照 | 1.8 MB |
| 构建开始 | 2026-11-27T10:44Z 左右 |
| 部署完成 | 2026-11-27T10:46:17Z |
| Deployment ID | `3359dd35-7bd5-4bbe-9849-19181db3318b` |
| 状态 | **SUCCESS** |
| 镜像 | `production-dpiad.railway-registry.com/28d3b430-...` |
| 日志证据 | `artifacts/railway-build.log` |

健康检查：`Path: /health`，`Retry window: 3m0s`，
第 1 次探测 `service unavailable`（模型启动中），随后 `Deploy complete`。

## 4. 本阶段全部部署/重启活动

| # | 动作 | 结果 | ID / 时间（UTC） |
| --- | --- | --- | --- |
| 1 | `railway up`（Phase 3 部署） | ✅ SUCCESS | `3359dd35` @ 10:46:17 |
| 2 | `railway restart`（Phase 10 进程重启） | ✅ 31.4 s 后 `/ready` 200 | 同部署实例 |
| 3 | `railway up`（Phase 12 可选重新部署） | ✅ SUCCESS | `492d9fa7` @ 11:00:25 |

日志：`artifacts/railway-build.log`、`artifacts/railway-redeploy.log`

## 5. 域名

```text
https://pocketscore-api-staging.up.railway.app
```

由 `railway domain` 输出（ID `cfb0dd91-4d8d-4fb7-931f-bf319c5a4852`），非编造。
所有 HTTP 证据均来自该域名。

## 6. 部署边界声明

| 项 | 状态 |
| --- | --- |
| 是否部署到 staging | ✅ 是 |
| 是否部署到 production | ❌ 否 |
| 是否修改 Railway 项目/服务名称 | ❌ 否 |
| 是否删除卷 | ❌ 否 |
| 是否修改环境变量 | ❌ 本阶段未新增/删除（沿用 C.2.2.1 的 15 项） |
| 是否合并 main | ❌ 否 |

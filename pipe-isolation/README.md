# 工艺管网隔离方案演示（Pipe Isolation Training Demo）

在模拟管网中找到**隔离目标设备所需关闭的阀门（候选隔离集合）**，并保证**指定的必要供给点仍可达**。

- **前端**：Angular 18 + Cytoscape.js 展示有向拓扑、阀门开闭/锁定、候选方案与残余路径
- **后端**：FastAPI + NetworkX，枚举极小 s–t 割并按保供约束过滤
- **存储**：PostgreSQL 保存管段连接、阀门状态、场景与必要供给点（本地可用 SQLite 跑测试）
- **不连接任何真实控制系统**；结果仅用于给定拓扑/阀门模型下的培训演示

> ⚠ **安全声明**：本系统仅做演示，输出不构成检修隔离依据，不代表满足真实检修
> 安全条件（未考虑双阀+放空、盲板、挂牌上锁、残压、介质倒流等）。

---

## 1. 模型约定

### 管段方向
管网是**有向图**，边方向即介质流向；“仍连通”按有向可达判定。
*不模拟停输后的物理倒流。*

### 管段与阀门
每个管段（segment）上至多一个阀门（valve）：

| 状态 | 图上处理 |
|---|---|
| 阀门开启、可操作 | 边可切断（容量 1），可进入关闭集合 |
| 阀门开启、**锁定**（用户锁定不可操作） | 边不可切断（容量 ∞） |
| 阀门**已关闭** | 边直接从图中移除（排液阀 V10 初始即关闭） |
| 管段无阀门 | 边不可切断（容量 ∞） |

管段类型：`main` 主管 / `bypass` 旁路 / `branch` 支路 / `outlet` 设备下游。

### 演示拓扑

```
                SP1(必要供给点)
                 ↑ V8
  SRC →V0→ A →V1→ N →V2→ B
                        ├─V3→ T(目标设备) ─V4→┐
                        ├─V5→ E ─V6→ T        │  (V6 旁路跨接到设备入口)
                        │     └─V7(绕回)→ C ←─┘
                        │               ├─V9→ SP2(必要供给点)
                        │               ├─V10(常闭)→ DRAIN
                        │               └─V11→ SINK
```

旁路 V5–V6 汇入设备入口，V7 **绕回下游 C**：隔离 T 时关闭 V3 与 V6，
介质仍经 `B→V5→E→V7→C` 供到 SP2。

## 2. 求解逻辑

1. 按当前阀态构造有向图（已关闭阀删边、锁定阀/无阀段不可切）。
2. 递归枚举 `SRC → T` 的所有**极小割**（任取一条路径，必须切断其上某个
   可操作阀，DFS + 去重，规模上限 `MAX_PLAN_SIZE`）。
3. 对每个候选割检查必要供给点可达性：
   - 全部可达 → **可行方案**；
   - 有断供 → 记入 `rejected_plans` 并标明断了哪些供给点。
4. 无可行方案时：在“不得断供”前提下贪心关闭所有能关的阀，再求一条
   `SRC → T` 的**残余路径**返回前端高亮（`reason=locked_path` 表示残余路径
   由被锁定阀门维持；`supply_conflict` 表示任何切法都必然断供）。

## 3. 快速开始

### 后端（本地，无需 PostgreSQL 即可跑通）

```bash
cd backend
pip install -r requirements.txt

# 方式 A：SQLite（零依赖，演示/测试）
USE_SQLITE=1 DATABASE_URL="sqlite:///./demo.db" uvicorn app.main:app --reload --port 8000

# 方式 B：PostgreSQL（见 deploy/docker-compose.yml）
# DATABASE_URL="postgresql+psycopg2://isolation:isolation@localhost:5432/isolation" \
#   uvicorn app.main:app --reload
```

启动时自动建表并幂等写入种子数据；接口文档：http://localhost:8000/docs

### 前端

```bash
cd frontend
npm install
npm start          # http://localhost:4200 ，/api 代理到 8000
```

### Docker Compose（PostgreSQL + 后端）

```bash
docker compose -f deploy/docker-compose.yml up --build
# initdb/01_init.sql 自动建表；后端启动时 upsert 种子数据
```

## 4. HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/topology` | 节点/管段/阀门/场景（含坐标、阀态） |
| POST | `/api/isolation` | 入参 `{scenario_id, locked_valve_ids}`，返回候选方案、被否决切法、残余路径 |
| PATCH | `/api/valves/{id}` | 修改阀门 `is_open` / `is_locked`（写库） |
| POST | `/api/reset` | 恢复演示初始阀态 |
| GET | `/api/health` | 健康检查 + 安全声明 |

前端“单击阀门”的锁定是**会话内临时锁定**（随计算请求提交，不写库）；
右侧阀门面板的“开/关”写库，便于演示已关闭阀导致的断边。

## 5. 三个验收样例

### 样例一：旁路绕回（默认场景）

`POST /api/isolation {"scenario_id":"eq_t"}`

```json
{
  "feasible": true,
  "plans": [{"valve_ids": ["V3", "V6"], "closes_bypass": true}],
  "rejected_plans": [
    {"valve_ids": ["V0"], "lost_required_supply_ids": ["SP1", "SP2"]},
    {"valve_ids": ["V1"], "lost_required_supply_ids": ["SP1", "SP2"]},
    {"valve_ids": ["V2"], "lost_required_supply_ids": ["SP2"]},
    {"valve_ids": ["V3", "V5"], "lost_required_supply_ids": ["SP2"]}
  ]
}
```

- 关 **V3**（设备进口）+ **V6**（旁路跨接）后，T 与 SRC 完全断开；
- SP1 经 `N→V8` 保持供给；**SP2 经旁路绕回 `B→V5→E→V7→C→V9` 保持供给**；
- `{V3,V5}` 看似更“靠源”，但 V5 一关绕回也断了 → SP2 断供，被否决。

### 样例二：锁定不可操作阀门后重算

`POST /api/isolation {"scenario_id":"eq_t","locked_valve_ids":["V6"]}`

```json
{
  "feasible": false,
  "reason": "locked_path",
  "locked_valve_ids": ["V6"],
  "residual_path_node_ids": ["SRC","A","N","B","E","T"],
  "residual_segment_ids": ["s0","s1","s2","s5","s6"]
}
```

前端沿 `SRC → A → N → B → E → T`（橙色）高亮**仍然连通的一条路径**，
路径上的 `s6` 即被锁定的旁路跨接阀 V6——这是无法隔离的直接原因。
同时锁定 V3 时残余路径改走主路 `…→B→T`（s3）。

### 样例三：不应断供的支路

样例一的 `rejected_plans` 即对此的显式回答：根部阀 V0/V1 会同时断掉
SP1、SP2；上游 V2 会断 SP2（SP1 在 N 之前仍通）。每个被否决方案都带
`lost_required_supply_ids`，页面“被否决的切法”折叠区可展开核对。
另：排液阀 V10 初始关闭，其管段 `s10` 不进入图（已关闭即断开）。

## 6. 测试

```bash
cd backend
USE_SQLITE=1 pytest -q
# 14 passed：求解器样例 9 项 + API 端到端 5 项（SQLite 临时库）
```

覆盖内容：默认 {V3,V6} 方案及保供验证、{V3,V5} 否决、锁定 V6 / V3+V6
残余路径、已关闭 V10 断边、V6 关闭后只需 V3 的空增量方案、API 锁阀持久化
与 reset、未知阀门 400。

## 7. 目录

```
pipe-isolation/
├── backend/
│   ├── app/
│   │   ├── solver.py       # NetworkX 纯算法：极小割枚举 + 保供过滤 + 残余路径
│   │   ├── seed.py         # 演示拓扑（方向、阀门、旁路、初始关闭阀）
│   │   ├── database.py     # SQLAlchemy 模型（PG/SQLite 双驱动）
│   │   ├── repository.py   # 装配/阀态读写
│   │   ├── seed_db.py      # 幂等种子
│   │   ├── schemas.py      # Pydantic + 安全声明
│   │   └── main.py         # FastAPI
│   └── tests/
├── frontend/
│   └── src/app/
│       ├── components/topology/  # Cytoscape 视图
│       ├── models/ services/
│       └── app.component.ts      # 方案/锁定/残余路径面板
└── deploy/
    ├── docker-compose.yml
    └── initdb/01_init.sql
```

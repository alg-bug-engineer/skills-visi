# 高德地图路口渠化下钻 Demo — 设计

日期：2026-06-28
状态：已确认，待实现

## 目标

单独生成一个基于高德地图（AMap JS API v2.0）的页面，能为路口（示例：奥体西路 × 经十路）生成详细渠化信息：

- 在保留高德底图道路与标注的前提下，叠加车道级渠化（车道面、车道分隔线、停止线、转向箭头、人行横道）。
- 支持随地图缩放自动「下钻」到渠化层级。
- 原生支持鼠标拖拽与滚轮缩放。

## 关键决策（已与用户确认）

| 维度 | 选择 |
|------|------|
| 交付形态 | 独立 HTML+JS Demo，浏览器直接打开，零构建 |
| 渠化数据来源 | **真实数据**：PostgreSQL 查询 inter_id=011wwe28ctu00001 内置 |
| 渲染方式 | AMap 原生矢量覆盖物（Polygon / Polyline / Marker） |
| 下钻触发 | 随缩放自动分级（LOD） |
| 算法参考 | 移植 `docs/channelizationLayer.js`（gatherArms / parseLaneInfo / boxR / 转向箭头 / 斑马线 / 转角圆弧） |

## 真实数据来源（v2）

奥体西路与经十路路口 `inter_id=011wwe28ctu00001`，由项目 PostgreSQL 实查并内置：

- 中心点 `road6.dim_inter_info.geom_center` → `POINT(117.111376 36.659469)`
- 渠化 `road6.dwd_tfc_rltn_wide_inter_ft_link`：10 条进/出口 link 的 `lane_info`（车道功能码 B左/C直/D右/A掉头，组合如 `AB`/`CD`）、`lane_num`/`c_lane_num`、`dir4_label`
- 几何 `road6.dim_link_info.geom`：每条 link 真实道路中心线经纬度序列（用于求臂朝外方位角，使渠化贴合真实路网）

真实进口车道：东进口 `B|B|B|C|C|C|C|C|C|C`(10道)、西进口 `B|B|C|C|C|C|C|D|D`(9道)、北进口 `B|B|C|C|D`(5道)、南进口 `AB|B|C|CD`(4道)。

**右行修正**：原 channelizationLayer.js 为独立示意图（进口置 +X）。本实现叠加真实地图，依据真实 geom 校正为「进口在朝外左侧、出口在右侧」，与实际车道侧别一致（已数值验证东进口落北侧）。

## 架构

单文件 `channelization-amap-demo.html`：

```
├─ <head>  高德 JS API + _AMapSecurityConfig
├─ 顶部 HUD  路口名 / 当前层级(路网|轮廓|渠化) / zoom
└─ <script>
   ├─ SAMPLE  内置渠化数据
   ├─ ChannelizationMap 类
   │   ├─ metersToLngLat(center, du, dv, bearing)  局部米 → 经纬度
   │   ├─ buildArm(arm)   逐臂生成覆盖物，按 LOD 分组入 layers
   │   ├─ render()        一次性创建所有覆盖物
   │   └─ applyLOD(zoom)  按 zoom 切换各层 show/hide
   └─ 初始化 → render → 绑定 zoomend/moveend
```

## 渲染分层（LOD）

所有覆盖物预创建，缩放时只切 `show()/hide()`，不重建，保证流畅：

- **L0 路网层**（zoom < 16）：高德底图 + 路口高亮圈。
- **L1 轮廓层**（16 ≤ zoom < 18）：真实道路中心线 + 进出口道整体路面多边形。
- **L2 渠化层**（zoom ≥ 18）：逐车道分隔线、停止线、转向箭头、人行横道、车道功能着色、转角圆弧。

底图始终 `showLabel: true`，任何层级都保留道路信息（路口大，细节阈值取 18）。

## 几何生成算法（移植自 channelizationLayer.js）

每条臂在「臂局部坐标系」绘制后投影回经纬度：

- `armAngleFromLink`：用真实 `path` 取贴近路口的两点求朝外方位角，使渠化与实际路网对齐。
- `gatherArms`：进/出口 link 按方位角（<25°）归组为臂，取最宽 link（合并主辅路）。
- `calcBoxR`：按各臂半宽 + 斑马线净空求路口框半径，保证相邻臂斑马线不重叠。
- 局部系：原点 = 路口中心，`+u` 沿臂朝外，`+v` 朝外时右手侧。**进口道占 -v（左侧）、出口道占 +v（右侧）**（右行修正）。`LANE_W = 3.3m`。
- **停止线**：进口道末端（靠路口侧）粗实线。
- **车道分隔线**：相邻车道虚线；进出口分界为黄色双实线。
- **转向箭头**：每条进口车道在停止线后放一个 Marker，按功能用对应图标，随臂方向旋转。
- **人行横道**：路口四周沿臂法向画斑马线条带（短 Polygon 组）。
- **车道面**：每条车道一个细长 Polygon，按功能淡着色（左=蓝、直=灰、右=绿、混合=青）。

`metersToLngLat`：等距圆柱近似 + cosLat 修正，把局部米偏移转经纬度，缩放时坐标恒定贴合底图。

## LOD 切换

`map.on('zoomend')` 读 `map.getZoom()` → `applyLOD()` 切换层显隐并更新 HUD 文案。

## 文件位置

`channelization-amap-demo.html`（项目根目录）。

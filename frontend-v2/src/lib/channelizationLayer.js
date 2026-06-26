/**
 * channelizationLayer.js  —  v3
 *
 * 改进点：
 *   1. 斑马线条纹平行于路臂方向（沿 Z 轴排列）
 *   2. 方向箭头更大，位置靠近停车线
 *   3. 相邻路臂角点用白色贝塞尔曲线相连
 *   4. 支持模拟车辆排队（可选 queueData 参数）
 *
 * 坐标约定（臂局部空间）：
 *   +Z  = 向路口外部（臂延伸方向）
 *   +X  = 俯视看臂时的右手侧
 *   进口道（-Z 行进）：在 +X 侧
 *   出口道（+Z 行进）：在 -X 侧
 */

import * as THREE from 'three';

// ── 几何参数 ──────────────────────────────────────────────────────────────────
const LANE_W  = 2.8;
const ARM_LEN = 72;
const BASE_Y  = 0.6;
const MARK_Y  = BASE_Y + 0.12;
const LINE_Y  = BASE_Y + 0.25;

// ── 颜色 ──────────────────────────────────────────────────────────────────────
const C_ROAD    = 0x2c2c2c;
const C_CENTER  = 0x1e1e1e;
const C_DIVIDER = 0xffcc00;
const C_MARKING = 0xcccccc;
const C_CURB    = 0x33aa55;
const C_STOP    = 0xff4444;
const C_ARROW   = 0xeeeeee;

// ── 投影 ──────────────────────────────────────────────────────────────────────
const CENTER_LON = 117.096, CENTER_LAT = 36.662, MPU = 10;
function project(lon, lat) {
  const x =  (lon - CENTER_LON) * Math.cos(CENTER_LAT * Math.PI / 180) * (Math.PI / 180) * 6371000 / MPU;
  const z = -(lat - CENTER_LAT) * (Math.PI / 180) * 6371000 / MPU;
  return [x, z];
}

// ── 方位角 → rotation.y ───────────────────────────────────────────────────────
function bearingToRotY(bearing) {
  return Math.PI - bearing * Math.PI / 180;
}

// ── 角度差（0-180）────────────────────────────────────────────────────────────
function angleDiff(a, b) {
  let d = Math.abs((a - b + 360) % 360);
  return d > 180 ? 360 - d : d;
}

// ── lane_info 解析 ────────────────────────────────────────────────────────────
function parseLaneInfo(lk) {
  if (lk.lane_info && lk.lane_info !== 'null') {
    return lk.lane_info.split('|').filter(s => s.length > 0);
  }
  return Array(lk.c_lane_num || lk.lane_num || 1).fill(null);
}

// ── geom 坐标 → 路臂方位角 ────────────────────────────────────────────────────
function geoBearing(lon1, lat1, lon2, lat2) {
  const dLat = lat2 - lat1;
  const dLon = (lon2 - lon1) * Math.cos((lat1 + lat2) * Math.PI / 360);
  return (Math.atan2(dLon, dLat) * 180 / Math.PI + 360) % 360;
}

function parseGeomPts(geom) {
  const inner = geom.slice(geom.indexOf('(') + 1, geom.lastIndexOf(')'));
  return inner.split(',').map(s => {
    const [lon, lat] = s.trim().split(/\s+/).map(Number);
    return [lon, lat];
  });
}

function getLinkArmAngle(lk, isIncoming) {
  try {
    const pts = parseGeomPts(lk.geom);
    if (pts.length >= 2) {
      const [p0, p1] = isIncoming
        ? [pts[pts.length - 1], pts[pts.length - 2]]
        : [pts[0], pts[1]];
      return geoBearing(p0[0], p0[1], p1[0], p1[1]);
    }
  } catch (_) { /* fall through */ }
  return isIncoming ? ((lk.t_angle + 180) % 360) : lk.f_angle;
}

// ── 将进/出路段归组为"臂" ─────────────────────────────────────────────────────
function gatherArms(inLinks, outLinks) {
  const arms = [];
  for (const lk of inLinks) {
    const angle = getLinkArmAngle(lk, true);
    let found = arms.find(a => angleDiff(a.angle, angle) < 22);
    if (!found) { found = { angle, inLink: null, outLink: null }; arms.push(found); }
    if (!found.inLink || parseLaneInfo(lk).length > parseLaneInfo(found.inLink).length) {
      found.inLink = lk;
      found.angle  = angle;
    }
  }
  for (const lk of outLinks) {
    const angle = getLinkArmAngle(lk, false);
    let found = arms.find(a => angleDiff(a.angle, angle) < 22);
    if (!found) { found = { angle, inLink: null, outLink: null }; arms.push(found); }
    if (!found.outLink || (lk.lane_num || 0) > (found.outLink.lane_num || 0)) {
      found.outLink = lk;
    }
  }
  return arms;
}

// ── 动态 BOX_R ────────────────────────────────────────────────────────────────
// 斑马线参数（需与 buildArm 中保持一致）
const CW_GAP = 2.0;   // 停车线到斑马线的间距（路口内侧）
const CW_LEN = 7.0;   // 斑马线沿行车方向的长度
// 斑马线不重叠的几何条件：
//   两相邻路臂的斑马线不交叉，需要 boxR > 该臂半宽 + CW_GAP + CW_LEN
// 即 boxR 必须足够大，让每条臂的斑马线区域不伸入相邻臂的"领地"
const CW_CLEARANCE = CW_GAP + CW_LEN + 1.5; // 额外 1.5 安全余量

function calcBoxR(arms) {
  if (arms.length < 2) return 20;
  const sorted = [...arms].sort((a, b) => a.angle - b.angle);
  let maxR = 20;

  // ① 相邻路臂不交叠（原有逻辑）
  for (let i = 0; i < sorted.length; i++) {
    const a1 = sorted[i], a2 = sorted[(i + 1) % sorted.length];
    let dAngle = a2.angle - a1.angle;
    if (dAngle < 0) dAngle += 360;
    if (dAngle < 1) continue;
    const w1half = ((a1.inLink ? parseLaneInfo(a1.inLink).length : 0) + (a1.outLink?.lane_num || 0)) * LANE_W / 2;
    const w2half = ((a2.inLink ? parseLaneInfo(a2.inLink).length : 0) + (a2.outLink?.lane_num || 0)) * LANE_W / 2;
    const sinHalf = Math.sin(dAngle * Math.PI / 360);
    if (sinHalf < 0.01) continue;
    maxR = Math.max(maxR, (w1half + w2half) / sinHalf * 0.55);
  }

  // ② 斑马线不交叠：boxR > 每条臂的半宽 + 斑马线净空
  for (const arm of arms) {
    const nI = arm.inLink  ? parseLaneInfo(arm.inLink).length : 0;
    const nO = arm.outLink ? (arm.outLink.c_lane_num || arm.outLink.lane_num || 0) : 0;
    const halfW = (nI + nO) * LANE_W / 2;
    maxR = Math.max(maxR, halfW + CW_CLEARANCE);
  }

  return Math.min(Math.max(maxR, 20), 150);
}

// ── 几何辅助 ──────────────────────────────────────────────────────────────────
function hPlane(w, d, color, y = BASE_Y, opacity = 1) {
  const m = new THREE.Mesh(
    new THREE.PlaneGeometry(w, d),
    new THREE.MeshBasicMaterial({
      color, side: THREE.DoubleSide,
      depthWrite: opacity >= 1,
      transparent: opacity < 1, opacity,
    }),
  );
  m.rotation.x   = -Math.PI / 2;
  m.position.y   = y;
  m.renderOrder  = 10;
  return m;
}

function lineMat(color) {
  return new THREE.LineBasicMaterial({ color, depthWrite: false });
}

function xLine(x0, x1, z, color, y = LINE_Y) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute([x0,y,z, x1,y,z], 3));
  const l = new THREE.Line(g, lineMat(color));
  l.renderOrder = 10;
  return l;
}

function zLine(x, z0, z1, color, y = LINE_Y) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute([x,y,z0, x,y,z1], 3));
  const l = new THREE.Line(g, lineMat(color));
  l.renderOrder = 10;
  return l;
}

function zDash(x, z0, z1, color, dashLen = 2.8, gapLen = 2.2) {
  const pts = [];
  let z = z0, on = true;
  while (z < z1) {
    const end = Math.min(z + (on ? dashLen : gapLen), z1);
    if (on) pts.push(x, LINE_Y, z, x, LINE_Y, end);
    z = end; on = !on;
  }
  if (pts.length < 6) return null;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  const l = new THREE.LineSegments(g, lineMat(color));
  l.renderOrder = 10;
  return l;
}

// ── 方向箭头（进口道局部坐标，驾驶员行进方向 -Z）─────────────────────────────
// cx = 车道中心 x（+X 侧）；arrowZ = 箭头中心 z 位置
// 左 = -X（驾驶员左）；右 = +X（驾驶员右）
/**
 * 实心填充路面转向箭头（三角形网格，模拟真实路面标线）
 *   cx      — 车道中心 X
 *   arrowZ  — 箭头中心 Z（靠近停车线）
 */
function makeArrow(laneCode, cx, arrowZ) {
  const mov = (laneCode || '').toUpperCase().replace(/[FGLRTZ]/g, '');
  if (!mov) return null;

  const hasC = mov.includes('C');
  const hasB = mov.includes('B') || mov.includes('A');
  const hasD = mov.includes('D') || mov.includes('E');

  const sw  = LANE_W * 0.14;   // 杆宽
  const H   = LANE_W * 0.55;   // 箭头总高
  const hw  = LANE_W * 0.18;   // 直行箭头头部半宽
  const ah  = H * 0.38;        // 直行箭头头部高度
  const bl  = LANE_W * 0.23;   // 转向分支长度
  const bah = sw  * 1.50;      // 转向箭头头部半宽
  const bal = sw  * 1.40;      // 转向箭头头部长度
  const Y   = LINE_Y + 0.06;

  const tris = [];

  /* 辅助：填充矩形（两个三角形）*/
  function rect(x0, x1, z0, z1) {
    tris.push(
      x0, Y, z0,  x1, Y, z0,  x0, Y, z1,
      x1, Y, z0,  x1, Y, z1,  x0, Y, z1,
    );
  }
  /* 辅助：三角形 */
  function tri(ax, az, bx, bz, dx, dz) {
    tris.push(ax, Y, az, bx, Y, bz, dx, Y, dz);
  }

  const baseZ  = arrowZ + H * 0.50;   // 杆尾（远离路口）
  const tipZ   = arrowZ - H * 0.50;   // 箭头尖（靠近路口）
  const neckZ  = tipZ + ah;            // 头部与杆的交界
  const forkZ  = arrowZ + H * (hasC ? 0.10 : 0.20);  // 转向分叉位置

  // ── 直行杆 + 箭头头部 ──────────────────────────────────────────────────────
  if (hasC) {
    rect(cx - sw / 2, cx + sw / 2, neckZ, baseZ);        // 杆身
    tri(cx - hw, neckZ, cx + hw, neckZ, cx, tipZ);       // 等腰三角箭头
  } else {
    // 无直行：短杆延伸到分叉处
    rect(cx - sw / 2, cx + sw / 2, forkZ, baseZ);
  }

  // ── 左转分支 ──────────────────────────────────────────────────────────────
  if (hasB) {
    rect(cx - bl, cx,  forkZ - sw / 2, forkZ + sw / 2); // 横向杆
    tri(                                                   // 向左箭头
      cx - bl,       forkZ - bah,
      cx - bl - bal, forkZ,
      cx - bl,       forkZ + bah,
    );
  }

  // ── 右转分支 ──────────────────────────────────────────────────────────────
  if (hasD) {
    rect(cx, cx + bl,  forkZ - sw / 2, forkZ + sw / 2); // 横向杆
    tri(                                                   // 向右箭头
      cx + bl,       forkZ - bah,
      cx + bl + bal, forkZ,
      cx + bl,       forkZ + bah,
    );
  }

  if (tris.length < 9) return null;

  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(tris), 3));
  return new THREE.Mesh(
    geom,
    new THREE.MeshBasicMaterial({ color: C_ARROW, side: THREE.DoubleSide }),
  );
}

// ── 将臂局部坐标转换到路口世界坐标（XZ 平面）────────────────────────────────
// rotation.y = π - θ_rad; wx = lz*sin(θ) - lx*cos(θ); wz = -lx*sin(θ) - lz*cos(θ)
function armToWorld(armAngle, lx, lz) {
  const t = armAngle * Math.PI / 180;
  return {
    x: lz * Math.sin(t) - lx * Math.cos(t),
    z: -lx * Math.sin(t) - lz * Math.cos(t),
  };
}

// ── 两条 2D 射线交点（XZ 平面）───────────────────────────────────────────────
// 射线1：p1 + t*d1；射线2：p2 + s*d2；返回交点或 null
function lineIntersect2D(p1x, p1z, d1x, d1z, p2x, p2z, d2x, d2z) {
  // d1x*t - d2x*s = p2x - p1x
  // d1z*t - d2z*s = p2z - p1z
  const det = d1x * (-d2z) - (-d2x) * d1z;
  if (Math.abs(det) < 1e-6) return null;
  const dx = p2x - p1x, dz = p2z - p1z;
  const t = (dx * (-d2z) + d2x * dz) / det;
  const s = (d1x * dz  - d1z * dx)   / det;
  if (t < 0 || s < 0) return null;        // 交点在射线背面则无效
  return { x: p1x + t * d1x, z: p1z + t * d1z };
}

// ── 相邻路臂角点白色凹形贝塞尔曲线（模拟转弯半径）───────────────────────────
// 控制点取两条路缘向路口内侧延伸后的交点，使曲线向内凹（符合真实路口转角）
function buildCenterCurves(arms, boxR) {
  const group = new THREE.Group();
  if (arms.length < 2) return group;

  const sorted = [...arms].sort((a, b) => a.angle - b.angle);

  for (let i = 0; i < sorted.length; i++) {
    const arm1 = sorted[i];
    const arm2 = sorted[(i + 1) % sorted.length];

    const nOut1 = arm1.outLink ? (arm1.outLink.c_lane_num || arm1.outLink.lane_num || 0) : 0;
    const nIn2  = arm2.inLink  ? parseLaneInfo(arm2.inLink).length : 0;

    const p1 = armToWorld(arm1.angle, -nOut1 * LANE_W, boxR);  // arm1 出口侧角点
    const p2 = armToWorld(arm2.angle,  nIn2  * LANE_W, boxR);  // arm2 进口侧角点

    // 路缘向路口内侧方向 = 路臂反方向（-sin, +cos in XZ）
    const t1 = arm1.angle * Math.PI / 180;
    const t2 = arm2.angle * Math.PI / 180;
    const d1x = -Math.sin(t1), d1z = Math.cos(t1);  // arm1 内侧方向
    const d2x = -Math.sin(t2), d2z = Math.cos(t2);  // arm2 内侧方向

    // 求两条内侧延伸线的交点作为贝塞尔控制点（凹曲线）
    let cpX, cpZ;
    const cp = lineIntersect2D(p1.x, p1.z, d1x, d1z, p2.x, p2.z, d2x, d2z);
    if (cp) {
      cpX = cp.x;
      cpZ = cp.z;
    } else {
      // 退化情况（两臂平行）：取中点略向内偏
      const midX = (p1.x + p2.x) / 2, midZ = (p1.z + p2.z) / 2;
      const midLen = Math.sqrt(midX * midX + midZ * midZ);
      const scale  = midLen > 0.5 ? (midLen * 0.55) / midLen : 0.55;
      cpX = midX * scale;
      cpZ = midZ * scale;
    }

    // 二次贝塞尔曲线（20 段）
    const pts = [];
    const N = 20;
    for (let k = 0; k <= N; k++) {
      const t  = k / N, it = 1 - t;
      pts.push(
        it * it * p1.x + 2 * it * t * cpX + t * t * p2.x,
        LINE_Y + 0.08,
        it * it * p1.z + 2 * it * t * cpZ + t * t * p2.z,
      );
    }

    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    const bl = new THREE.Line(geom, lineMat(0xffffff));
    bl.renderOrder = 10;
    group.add(bl);
  }

  return group;
}

// ── 3D 小汽车模型 ─────────────────────────────────────────────────────────────
// 车身 + 车顶舱体，坐标原点在车底中心，车头朝 -Z（驶向路口方向）
function createCarMesh(carLen, carW, bodyColor) {
  const g = new THREE.Group();

  // 车身（宽扁盒）
  const bh = 0.40;
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(carW * 0.84, bh, carLen * 0.86),
    new THREE.MeshBasicMaterial({ color: bodyColor }),
  );
  body.position.y = bh / 2;
  g.add(body);

  // 车顶舱（稍窄、稍矮，偏后放置）
  const ch = 0.26;
  const cabinColor = new THREE.Color(bodyColor).multiplyScalar(0.68).getHex();
  const cabin = new THREE.Mesh(
    new THREE.BoxGeometry(carW * 0.60, ch, carLen * 0.52),
    new THREE.MeshBasicMaterial({ color: cabinColor }),
  );
  cabin.position.y  = bh + ch / 2;
  cabin.position.z  = carLen * 0.04;  // 稍偏后（远离车头）
  g.add(cabin);

  return g;
}

// ── 车辆排队模拟 ───────────────────────────────────────────────────────────────
// queueInfo: { queueM: number, satPct: number }
// 车辆数 = round(queueM / 8)，每条车道各差 ±1 辆形成参差感
function buildQueueCars(arm, boxR, queueInfo) {
  const g = new THREE.Group();
  const inLanes = arm.inLink ? parseLaneInfo(arm.inLink) : [];
  const nIn = inLanes.length;
  if (nIn === 0) return g;

  const { queueM = 0, satPct = 0 } = queueInfo;
  if (queueM <= 0) return g;

  // 颜色依据饱和度
  const bodyColor =
    satPct >= 85 ? 0xdd2233 :
    satPct >= 70 ? 0xdd6600 :
    satPct >= 50 ? 0xccaa00 :
                   0x338844;

  // 总车辆数 = round(queueM / 8)；每辆约占 8m = 0.8 Three.js 单位
  const nCarsBase = Math.max(1, Math.round(queueM / 8));
  const carLen    = 0.54;   // 车身长度（Three.js 单位）
  const carGap    = 0.26;   // 车间距
  const carStep   = carLen + carGap;   // ≈ 0.8 单位 / 辆
  const carW      = LANE_W * 0.70;
  const startZ    = boxR + 0.9;        // 停车线后方出发点

  for (let lane = 0; lane < nIn; lane++) {
    const cx = (lane + 0.5) * LANE_W;
    const code = (inLanes[lane] || '').toUpperCase();

    // 按车道功能确定排队系数（空车道视为直行）：
    //   纯左转(B)/纯右转(D) → 40%；组合转向(BC/CD) → 65%；其余（含空车道）→ 100%
    const isOnlyLeft  = /^[BAZ]*B[BAZ]*$/.test(code) && !code.includes('C') && !code.includes('D');
    const isOnlyRight = /^[DEZ]*D[DEZ]*$/.test(code) && !code.includes('C') && !code.includes('B');
    const isMixed     = (code.includes('B') || code.includes('D')) && code.includes('C');
    const ratio = isOnlyLeft || isOnlyRight ? 0.40 : isMixed ? 0.65 : 1.0;

    // 整体 ×2；每条车道再做 -1 / 0 / +1 差异
    const laneVar   = (lane % 3) - 1;
    const nCarsLane = Math.max(0, Math.round(nCarsBase * ratio * 2) + laneVar);

    // 车道小偏移，让排队不整齐划一
    const laneOffset = (lane % 2) * (carStep * 0.22);

    for (let c = 0; c < nCarsLane; c++) {
      const zCenter = startZ + carLen / 2 + c * carStep + laneOffset;
      if (zCenter > boxR + ARM_LEN * 0.94) break;

      const car = createCarMesh(carLen, carW, bodyColor);
      // 车底放在路面标线层上方
      car.position.set(cx, MARK_Y + 0.02, zCenter);
      g.add(car);
    }
  }

  g.rotation.y = bearingToRotY(arm.angle);
  return g;
}

// ── 构建单条路臂 ──────────────────────────────────────────────────────────────
function buildArm(arm, boxR) {
  const g = new THREE.Group();

  const inLink  = arm.inLink;
  const outLink = arm.outLink;
  const inLanes = inLink  ? parseLaneInfo(inLink)                          : [];
  const nIn     = inLanes.length;
  const nOut    = outLink ? (outLink.c_lane_num || outLink.lane_num || 0) : 0;

  if (nIn + nOut === 0) return g;

  const xIn    =  nIn  * LANE_W;
  const xOut   = -nOut * LANE_W;
  const totalW = (nIn + nOut) * LANE_W;
  const xCenter = (xOut + xIn) / 2;

  const z0   = boxR;
  const z1   = boxR + ARM_LEN;
  const zMid = z0 + ARM_LEN / 2;

  // ── 路面 ──────────────────────────────────────────────────────────────────
  const road = hPlane(totalW, ARM_LEN, C_ROAD);
  road.position.set(xCenter, BASE_Y, z0 + ARM_LEN / 2);
  g.add(road);

  // ── 缘石线 ────────────────────────────────────────────────────────────────
  if (nIn  > 0) g.add(zLine( xIn,  z0, z1, C_CURB));
  if (nOut > 0) g.add(zLine( xOut, z0, z1, C_CURB));

  // ── 中心分隔线 ────────────────────────────────────────────────────────────
  if (nIn > 0 && nOut > 0) g.add(zLine(0, z0, z1, C_DIVIDER));

  // ── 进口道车道虚线 ────────────────────────────────────────────────────────
  for (let i = 1; i < nIn; i++) {
    const d = zDash(i * LANE_W, z0, z1, C_MARKING);
    if (d) g.add(d);
  }
  // ── 出口道车道虚线 ────────────────────────────────────────────────────────
  for (let j = 1; j < nOut; j++) {
    const d = zDash(-j * LANE_W, z0, z1, C_MARKING);
    if (d) g.add(d);
  }

  // ── 停车线（进口道内侧，路口边缘处）────────────────────────────────────
  if (nIn > 0) {
    const sw = nIn * LANE_W;
    const sp = hPlane(sw, 0.9, C_STOP, MARK_Y);
    sp.position.set(xIn - sw / 2, MARK_Y, z0 + 0.45);
    g.add(sp);
    g.add(xLine(0, xIn, z0, C_STOP, MARK_Y + 0.06));
  }

  // ── 斑马线（停车线前方，即路口内侧）────────────────────────────────────
  // 正确交通布局：驾驶员行进方向 → 停车线 → 斑马线 → 路口中心
  // boxR 已由 calcBoxR 保证足够大，使相邻路臂的斑马线在路口中心盒内不交叠
  // 条纹以道路宽度中心对称排列
  if (nIn > 0) {
    const cwZ1 = z0 - CW_GAP;           // 靠停车线侧
    const cwZ0 = cwZ1 - CW_LEN;         // 靠路口中心侧
    const cwZc = (cwZ0 + cwZ1) / 2;

    const stripeW   = 1.1;
    const stripeGap = 1.6;
    const pitch     = stripeW + stripeGap;
    const nStripes  = Math.max(1, Math.floor((totalW + stripeGap) / pitch));
    const usedW     = nStripes * stripeW + (nStripes - 1) * stripeGap;
    const startX    = xCenter - usedW / 2;

    for (let i = 0; i < nStripes; i++) {
      const stripe = hPlane(stripeW, CW_LEN, 0xdddddd, MARK_Y);
      stripe.position.set(startX + i * pitch + stripeW / 2, MARK_Y, cwZc);
      g.add(stripe);
    }
  }

  // ── 进口道方向箭头（更大，靠近停车线）──────────────────────────────────
  const arrowZ = z0 + ARM_LEN * 0.30;  // 靠近停车线
  inLanes.forEach((code, i) => {
    const cx = (i + 0.5) * LANE_W;
    const arrow = makeArrow(code, cx, arrowZ);
    if (arrow) g.add(arrow);
  });

  g.rotation.y = bearingToRotY(arm.angle);
  return g;
}

// ── 公开 API ──────────────────────────────────────────────────────────────────

/**
 * 创建路口渠化图
 * @param {object}   interItem  - intersection_links.json 中的一个路口对象
 * @param {Array}    [queueData] - 可选排队数据
 *   每项格式：{ armAngle: number, queueM: number, satPct: number }
 *   armAngle: 与路臂方向角匹配（地理方位角，度），不匹配则模拟少量
 */
export function createChannelizationLayer(interItem, queueData = null, options = {}) {
  const group = new THREE.Group();
  group.name        = 'channelization';
  group.renderOrder = 10;

  const info     = interItem.intersection_info;
  const [cx, cz] = project(info.longitude, info.latitude);

  const sl       = interItem.surrounding_links;
  const inLinks  = sl['进入路口的路段']  || [];
  const outLinks = sl['离开路口的路段'] || [];

  const arms = gatherArms(inLinks, outLinks);
  const boxR = calcBoxR(arms);

  // ── 路臂几何 ──────────────────────────────────────────────────────────────
  for (const arm of arms) {
    group.add(buildArm(arm, boxR));
  }

  // ── 角点曲线 ──────────────────────────────────────────────────────────────
  group.add(buildCenterCurves(arms, boxR));

  // ── 车辆排队 ──────────────────────────────────────────────────────────────
  for (const arm of arms) {
    if (!arm.inLink) continue;
    // 从 queueData 中查找最匹配的臂数据（角度差 < 30°）
    let qInfo = null;
    if (queueData) {
      const match = queueData.reduce((best, q) => {
        const d = angleDiff(arm.angle, q.armAngle);
        return d < (best?.d ?? 999) ? { ...q, d } : best;
      }, null);
      if (match && match.d < 30) qInfo = match;
    }
    if (!qInfo) qInfo = { queueM: 0, satPct: 0 };
    if (qInfo.queueM > 0) {
      group.add(buildQueueCars(arm, boxR, qInfo));
    }
  }

  if (options.centerAtOrigin) {
    group.position.set(0, 0, 0);
  } else {
    group.position.set(cx, 0, cz);
  }
  group.traverse(o => { o.frustumCulled = false; });

  // 存储路臂数据，供高亮叠加层使用
  group.userData.arms = arms;
  group.userData.boxR = boxR;

  return group;
}

/** 根据渠化图包围盒计算居中俯视视角参数 */
export function getChannelizationView(group) {
  const box = new THREE.Box3().setFromObject(group);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const span = Math.max(size.x, size.z, 60);
  return {
    center,
    height: span * 1.08,
    minDistance: span * 0.35,
    maxDistance: span * 2.8,
  };
}

/** 释放 GPU 资源 */
export function disposeChannelizationLayer(group) {
  if (!group) return;
  group.traverse(o => {
    o.geometry?.dispose();
    if (Array.isArray(o.material)) o.material.forEach(m => m.dispose());
    else o.material?.dispose();
  });
}

// ── 检查结果高亮叠加 ──────────────────────────────────────────────────────────

/** 清除检查高亮叠加层 */
export function clearCheckHighlight(channelGroup) {
  if (!channelGroup) return;
  const existing = channelGroup.getObjectByName('check-highlight');
  if (existing) {
    existing.traverse(o => {
      o.geometry?.dispose();
      if (Array.isArray(o.material)) o.material.forEach(m => { m.map?.dispose(); m.dispose(); });
      else { o.material?.map?.dispose(); o.material?.dispose(); }
    });
    channelGroup.remove(existing);
  }
}

/** 生成带文字的 CanvasTexture 标签 */
function _makeTextTex(line1, line2, colorHex) {
  const W = 320, H = 88;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(0,4,14,0.82)';
  ctx.beginPath(); ctx.roundRect(4, 4, W - 8, H - 8, 10); ctx.fill();
  ctx.strokeStyle = colorHex; ctx.lineWidth = 2.5; ctx.stroke();
  ctx.fillStyle = colorHex;
  ctx.font = 'bold 22px "Microsoft YaHei", sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(line1, W / 2, H * 0.36);
  ctx.fillStyle = 'rgba(220,240,255,0.8)';
  ctx.font = '16px "Microsoft YaHei", sans-serif';
  ctx.fillText(line2, W / 2, H * 0.72);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** 从指标ID和证据对象生成人类可读的标注文字 */
function _metricLabel(indicatorId, evidence) {
  const id = indicatorId || '';
  const ev = evidence || {};
  if (id.includes('saturation')) {
    const v = ev.saturation_max ?? ev.max_turn_saturation;
    return v != null ? `饱和度 ${Number(v).toFixed(3)}` : '饱和度指标';
  }
  if (id.includes('unbalance') || id.includes('imbalance')) {
    const v = ev.unbalance_index ?? ev.turn_imbalance_ratio;
    return v != null ? `失衡指数 ${Number(v).toFixed(3)}` : '流量失衡';
  }
  if (id.includes('green') || id.includes('signal')) {
    const v = ev.avg_green_ratio;
    return v != null ? `绿信比 ${(Number(v) * 100).toFixed(1)}%` : '信控指标';
  }
  if (id.includes('jam') || id.includes('delay') || id.includes('congestion') || id.includes('nearby')) {
    const v = ev.avg_jam_delay_index ?? ev.avg_delay_dur;
    return v != null ? `延误/拥堵 ${Number(v).toFixed(2)}` : '拥堵指标';
  }
  if (id.includes('capacity')) return '通行能力';
  if (id.includes('device')) return '设备覆盖';
  // fallback: 取证据首个有效值
  const firstKey = Object.keys(ev).find(k => !['expression', 'business_metric', 'frequency', 'common_periods', 'value'].includes(k) && ev[k] != null);
  if (firstKey) return `${firstKey}: ${ev[firstKey]}`;
  return null;
}

/**
 * 在渠化图路臂上叠加检查项高亮效果
 * - 在各路臂路面叠加半透明彩色平面
 * - 饱和度/通行能力类：显示密集车流色带
 * - 信控类：显示绿/红信比色带
 * - 浮空文字标注关键指标值
 *
 * @param {THREE.Group} channelGroup
 * @param {string} indicatorId
 * @param {string} verdict  'fail' | 'warn' | 'pass' | 'partial'
 * @param {object} evidence
 */
export function applyCheckHighlight(channelGroup, indicatorId, verdict, evidence) {
  clearCheckHighlight(channelGroup);
  const arms = channelGroup.userData.arms;
  const boxR = channelGroup.userData.boxR;
  if (!arms?.length) return;

  const id  = indicatorId || '';
  const ev  = evidence    || {};
  const isSat  = id.includes('saturation') || id.includes('capacity') || id.includes('demand');
  const isImb  = id.includes('unbalance')  || id.includes('imbalance');
  const isSig  = id.includes('signal')     || id.includes('green');
  const isCong = id.includes('jam')        || id.includes('congestion') || id.includes('nearby') || id.includes('delay');

  const colorHex = verdict === 'fail'    ? '#ff3311' :
                   verdict === 'warn'    ? '#ff8800' :
                   verdict === 'partial' ? '#8888cc' :
                                          '#00cc66';
  const colorNum = verdict === 'fail'    ? 0xff3311 :
                   verdict === 'warn'    ? 0xff8800 :
                   verdict === 'partial' ? 0x8888cc :
                                          0x00cc66;
  const baseAlpha = verdict === 'fail' ? 0.42 : verdict === 'warn' ? 0.30 : 0.18;

  const hlGroup = new THREE.Group();
  hlGroup.name = 'check-highlight';

  for (const arm of arms) {
    const inLanes = arm.inLink ? parseLaneInfo(arm.inLink) : [];
    const nIn  = inLanes.length;
    const nOut = arm.outLink ? (arm.outLink.c_lane_num || arm.outLink.lane_num || 0) : 0;
    if (nIn + nOut === 0) continue;

    const totalW  = (nIn + nOut) * LANE_W;
    const xCenter = (nIn * LANE_W - nOut * LANE_W) / 2;
    const armGrp  = new THREE.Group();
    armGrp.rotation.y = bearingToRotY(arm.angle);

    // ── 路面彩色底层叠加 ──────────────────────────────────────────────────
    const overlay = new THREE.Mesh(
      new THREE.PlaneGeometry(totalW, ARM_LEN),
      new THREE.MeshBasicMaterial({
        color: colorNum, transparent: true, opacity: baseAlpha,
        side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      })
    );
    overlay.rotation.x = -Math.PI / 2;
    overlay.position.set(xCenter, BASE_Y + 0.6, boxR + ARM_LEN / 2);
    overlay.renderOrder = 15;
    armGrp.add(overlay);

    // ── 饱和度/拥堵：车流密度色带（从停车线向外填充，代表排队长度） ──────
    if ((isSat || isCong) && nIn > 0) {
      const satVal  = Math.min(ev.saturation_max ?? ev.max_turn_saturation ?? ev.avg_jam_delay_index ?? 0.9, 1.8);
      const fillRatio = Math.min(satVal / 1.0, 1.0);
      const fillLen = ARM_LEN * 0.88 * fillRatio;

      if (fillLen > 1) {
        const flowColor = satVal >= 1.0 ? 0xff1100 : satVal >= 0.85 ? 0xff5500 : 0xffaa00;
        const flowBar = new THREE.Mesh(
          new THREE.PlaneGeometry(nIn * LANE_W * 0.88, fillLen),
          new THREE.MeshBasicMaterial({
            color: flowColor, transparent: true, opacity: 0.55,
            side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
          })
        );
        flowBar.rotation.x = -Math.PI / 2;
        flowBar.position.set(nIn * LANE_W / 2, BASE_Y + 1.0, boxR + fillLen / 2 + 0.4);
        flowBar.renderOrder = 16;
        armGrp.add(flowBar);

        // 排队末端粗横线
        const endLine = new THREE.Mesh(
          new THREE.PlaneGeometry(nIn * LANE_W * 0.88, 1.2),
          new THREE.MeshBasicMaterial({
            color: 0xff2200, transparent: true, opacity: 0.92,
            side: THREE.DoubleSide, depthWrite: false,
          })
        );
        endLine.rotation.x = -Math.PI / 2;
        endLine.position.set(nIn * LANE_W / 2, BASE_Y + 1.3, boxR + fillLen);
        endLine.renderOrder = 17;
        armGrp.add(endLine);
      }
    }

    // ── 信控：停车线处绿/红信比色带 ─────────────────────────────────────
    if (isSig && nIn > 0) {
      const ratio  = Math.min(ev.avg_green_ratio ?? 0.5, 1.0);
      const greenW = nIn * LANE_W * ratio;
      const redW   = nIn * LANE_W * (1 - ratio);

      if (greenW > 0.2) {
        const gBar = new THREE.Mesh(
          new THREE.PlaneGeometry(greenW, 3.0),
          new THREE.MeshBasicMaterial({
            color: 0x00ee44, transparent: true, opacity: 0.80,
            side: THREE.DoubleSide, depthWrite: false,
          })
        );
        gBar.rotation.x = -Math.PI / 2;
        gBar.position.set(greenW / 2, BASE_Y + 1.5, boxR + 1.5);
        gBar.renderOrder = 17;
        armGrp.add(gBar);
      }
      if (redW > 0.2) {
        const rBar = new THREE.Mesh(
          new THREE.PlaneGeometry(redW, 3.0),
          new THREE.MeshBasicMaterial({
            color: 0xff2200, transparent: true, opacity: 0.80,
            side: THREE.DoubleSide, depthWrite: false,
          })
        );
        rBar.rotation.x = -Math.PI / 2;
        rBar.position.set(greenW + redW / 2, BASE_Y + 1.5, boxR + 1.5);
        rBar.renderOrder = 17;
        armGrp.add(rBar);
      }
    }

    // ── 失衡：进/出口道色带宽度差异化 ───────────────────────────────────
    if (isImb && nIn > 0 && nOut > 0) {
      const idx = ev.unbalance_index ?? ev.turn_imbalance_ratio ?? 0.2;
      const scale = Math.min(Number(idx) / 0.5, 1.0);
      const inW  = nIn  * LANE_W * (0.7 + scale * 0.25);
      const outW = nOut * LANE_W * (0.7 - scale * 0.20);

      if (inW > 0.1) {
        const inBar = new THREE.Mesh(
          new THREE.PlaneGeometry(inW, ARM_LEN * 0.65),
          new THREE.MeshBasicMaterial({
            color: 0xff4400, transparent: true, opacity: 0.40,
            side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
          })
        );
        inBar.rotation.x = -Math.PI / 2;
        inBar.position.set(inW / 2, BASE_Y + 0.9, boxR + ARM_LEN * 0.33);
        inBar.renderOrder = 16;
        armGrp.add(inBar);
      }
    }

    hlGroup.add(armGrp);
  }

  // ── 浮空文字标注 ──────────────────────────────────────────────────────────
  const metricText = _metricLabel(id, ev);
  if (metricText && verdict !== 'partial') {
    const verdictText = verdict === 'fail'    ? '⚠ 异常超阈值' :
                        verdict === 'warn'    ? '⚠ 告警' :
                        verdict === 'partial' ? '○ 数据缺失' :
                                               '✓ 正常';
    const tex = _makeTextTex(metricText, verdictText, colorHex);
    const sp  = new THREE.Sprite(new THREE.SpriteMaterial({
      map: tex, transparent: true, depthWrite: false,
    }));
    const box    = new THREE.Box3().setFromObject(channelGroup);
    const center = box.getCenter(new THREE.Vector3());
    const size   = box.getSize(new THREE.Vector3());
    sp.position.set(0, size.y + 18, 0);
    sp.scale.set(40, 12, 1);
    sp.renderOrder = 50;
    hlGroup.add(sp);
  }

  channelGroup.add(hlGroup);
}

const _DIR_BEARING = { '北': 0, '东': 90, '南': 180, '西': 270 };

function _armMatchesDir(armAngle, dir) {
  const target = _DIR_BEARING[dir];
  if (target == null) return false;
  const d = Math.abs(((armAngle - target + 540) % 360) - 180);
  return d <= 28;
}

/**
 * 强调指定进口道的转向箭头（如西左转）
 * @param {THREE.Group} channelGroup
 * @param {{ dir: string, turnCode: string, label?: string, saturation?: number }} spec
 */
export function applyTurnHighlight(channelGroup, spec) {
  clearCheckHighlight(channelGroup);
  const arms = channelGroup.userData.arms;
  const boxR = channelGroup.userData.boxR;
  if (!arms?.length || !spec?.dir || !spec?.turnCode) return;

  const hlGroup = new THREE.Group();
  hlGroup.name = 'check-highlight';

  for (const arm of arms) {
    if (!_armMatchesDir(arm.angle, spec.dir)) continue;
    const inLanes = arm.inLink ? parseLaneInfo(arm.inLink) : [];
    const laneIdx = inLanes.findIndex(code => code === spec.turnCode);
    if (laneIdx < 0) continue;

    const nIn = inLanes.length;
    const armGrp = new THREE.Group();
    armGrp.rotation.y = bearingToRotY(arm.angle);

    const laneX = (laneIdx + 0.5) * LANE_W;
    const sat = spec.saturation != null ? Number(spec.saturation) : 1.0;
    const flowColor = sat >= 1.0 ? 0xff1100 : sat >= 0.85 ? 0xff5500 : 0xffaa00;
    const laneBar = new THREE.Mesh(
      new THREE.PlaneGeometry(LANE_W * 0.92, ARM_LEN * 0.75),
      new THREE.MeshBasicMaterial({
        color: flowColor, transparent: true, opacity: 0.72,
        side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      })
    );
    laneBar.rotation.x = -Math.PI / 2;
    laneBar.position.set(laneX, BASE_Y + 1.4, boxR + ARM_LEN * 0.38);
    laneBar.renderOrder = 20;
    armGrp.add(laneBar);

    const ring = new THREE.Mesh(
      new THREE.RingGeometry(LANE_W * 0.28, LANE_W * 0.42, 24),
      new THREE.MeshBasicMaterial({
        color: 0xffdd00, transparent: true, opacity: 0.95,
        side: THREE.DoubleSide, depthWrite: false,
      })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(laneX, BASE_Y + 1.6, boxR + ARM_LEN * 0.28);
    ring.renderOrder = 21;
    armGrp.add(ring);

    hlGroup.add(armGrp);

    const label = spec.label || `${spec.dir}向转向`;
    const satText = spec.saturation != null ? `饱和度 ${(spec.saturation * 100).toFixed(0)}%` : '重点关注';
    const tex = _makeTextTex(label, satText, '#ffcc00');
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
    const size = new THREE.Box3().setFromObject(channelGroup).getSize(new THREE.Vector3());
    sp.position.set(0, size.y + 16, 0);
    sp.scale.set(38, 11, 1);
    sp.renderOrder = 50;
    hlGroup.add(sp);
    break;
  }

  channelGroup.add(hlGroup);
}

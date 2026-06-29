<script setup lang="ts">
import { computed } from 'vue'
import type { ScanRecord } from '../types/scan'
import { bandColor, isOversaturated } from '../utils/scanColors'

const props = defineProps<{ record: ScanRecord | null }>()

const oversat = computed(() => (props.record ? isOversaturated(props.record) : false))

function fmt(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined ? '—' : v.toFixed(digits)
}
</script>

<template>
  <div class="panel" v-if="record">
    <header class="head">
      <div class="title">{{ record.inter_name }}</div>
      <div class="sub">{{ record.period }} · {{ record.scene_type || '未知场景' }} · {{ record.pressure_level || '—' }}</div>
      <span class="band" :style="{ background: bandColor(record.problem_band) }">{{ record.problem_band }}</span>
    </header>

    <div v-if="oversat" class="warn">⚠ 过饱和：工程可解 / 配时无效 —— 需求超通行能力，单纯调配时救不了，避免无效投入。</div>

    <section>
      <h4>运行指标</h4>
      <div class="metrics">
        <div><span>饱和度</span><b>{{ fmt(record.metrics.saturation_max) }}</b></div>
        <div><span>失衡系数</span><b>{{ fmt(record.metrics.unbalance_index) }}</b></div>
        <div><span>绿灯利用率</span><b>{{ fmt(record.metrics.green_utilization) }}</b></div>
      </div>
    </section>

    <section v-if="record.top_issues?.length">
      <h4>信控诊断</h4>
      <div class="tags">
        <span v-for="t in record.top_issues" :key="t" class="tag">{{ t }}</span>
      </div>
      <p class="summary">{{ record.governance_summary }}</p>
    </section>

    <section v-if="record.governance_actions?.length">
      <h4>治理建议</h4>
      <ul class="actions">
        <li v-for="a in record.governance_actions" :key="a.category">
          <b>【{{ a.label }}】</b>{{ a.governance }}
        </li>
      </ul>
    </section>

    <section v-if="record.problem_band === '配时可解'">
      <h4>试点理由</h4>
      <p class="pilot">
        信控改善上限 <b>{{ record.control_improvement_ceiling }}</b>，严重度 {{ record.severity }}，
        试点推荐分 <b>{{ record.pilot_score ?? '—' }}</b> —— 配时优化可见效，建议纳入试点。
      </p>
    </section>

    <section v-if="record.data_quality_tags?.length" class="quality">
      数据质量标注：{{ record.data_quality_tags.join('、') }}
    </section>
  </div>
  <div class="panel empty" v-else>点击地图上的路口查看完整认知 + 信控诊断 + 治理建议</div>
</template>

<style scoped>
.panel {
  padding: 16px;
  overflow-y: auto;
  height: 100%;
  font-size: 13px;
}
.panel.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8b97a7;
  text-align: center;
}
.head .title {
  font-size: 17px;
  font-weight: 700;
}
.head .sub {
  color: #8b97a7;
  margin: 4px 0 8px;
}
.band {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  color: #fff;
}
.warn {
  background: rgba(192, 57, 43, 0.18);
  border: 1px solid rgba(192, 57, 43, 0.5);
  color: #ff9b8e;
  padding: 10px;
  border-radius: 8px;
  margin: 12px 0;
  line-height: 1.6;
}
section {
  margin-top: 16px;
}
h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #9fb0c3;
}
.metrics {
  display: flex;
  gap: 10px;
}
.metrics div {
  flex: 1;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 10px;
  text-align: center;
}
.metrics span {
  display: block;
  color: #8b97a7;
  font-size: 11px;
}
.metrics b {
  font-size: 18px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  background: rgba(47, 155, 255, 0.18);
  color: #7fc0ff;
  padding: 2px 10px;
  border-radius: 10px;
}
.summary,
.pilot {
  line-height: 1.7;
  color: #c4cfdc;
}
.actions {
  margin: 0;
  padding-left: 4px;
  list-style: none;
  line-height: 1.7;
}
.quality {
  color: #8b97a7;
  font-size: 12px;
  border-top: 1px dashed rgba(255, 255, 255, 0.12);
  padding-top: 10px;
}
</style>

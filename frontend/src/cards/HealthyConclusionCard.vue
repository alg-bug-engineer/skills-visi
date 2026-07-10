<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { ratio } from '@/utils/format'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const metrics = computed(() => store.diagnosis?.metrics ?? null)
const saturation = computed(() => metrics.value?.saturation ?? metrics.value?.saturation_rate ?? null)
</script>

<template>
  <BaseCard title="运行状态结论" :act="3" tone="protected" data-testid="healthy-conclusion-card">
    <div class="verdict">
      <span class="verdict__k">核验结论</span>
      <span class="verdict__v">路口运行平稳，无需干预</span>
    </div>

    <ul class="grid" data-testid="healthy-metrics">
      <li><span>排队比</span><b class="ok">{{ ratio(metrics?.queue_ratio) }}</b></li>
      <li><span>饱和度</span><b class="ok">{{ ratio(saturation) }}</b></li>
      <li><span>绿灯利用率</span><b>{{ ratio(metrics?.green_utilization) }}</b></li>
      <li><span>服务水平</span><b class="ok">{{ metrics?.los ?? '—' }}</b></li>
    </ul>

    <dl class="triad">
      <div>
        <dt>诊断</dt>
        <dd>排队与饱和度均在正常区间，无溢出、无过饱和，指标稳定。</dd>
      </div>
      <div>
        <dt>策略</dt>
        <dd>维持现状（不下发新方案），保留当前配时，避免无谓扰动。</dd>
      </div>
      <div>
        <dt>处置</dt>
        <dd>转入持续监测：排队比 ≥ 0.8 或饱和度 ≥ 0.9 时自动触发治理闭环。</dd>
      </div>
    </dl>

    <p class="foot">本次为例行健康核验，可沉淀为路口体检记录，供后续对比。</p>
  </BaseCard>
</template>

<style scoped>
.verdict {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--protected);
  background: var(--protected-dim);
}
.verdict__k {
  font-size: 11px;
  color: var(--text-mute);
}
.verdict__v {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}
.grid {
  list-style: none;
  margin: 0 0 10px;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px 12px;
}
.grid li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 3px;
}
.grid span {
  font-size: 11.5px;
  color: var(--text-dim);
}
.grid b {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.grid b.ok {
  color: var(--protected);
}
.triad {
  margin: 0 0 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.triad > div {
  display: flex;
  gap: 8px;
}
.triad dt {
  flex: 0 0 40px;
  font-size: 11px;
  font-weight: 700;
  color: var(--protected);
  padding-top: 1px;
}
.triad dd {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-dim);
}
.foot {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid rgba(146, 161, 181, 0.35);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
  color: var(--text-mute);
}
</style>

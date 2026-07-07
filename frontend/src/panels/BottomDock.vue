<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { DEMO_INPUT } from '@/api/endpoints'
import PlanDrawer from './PlanDrawer.vue'

const store = usePresentationStore()
const { dock, userInput, acts, currentAct, signal, status } = storeToRefs(store)

const examples = [
  DEMO_INPUT,
  '经十路与舜耕路口，晚高峰南向北左转排队严重，能不能加绿？',
]

const progress = computed(() =>
  acts.value.length ? Math.round(((currentAct.value + 1) / acts.value.length) * 100) : 0,
)
const signalText = computed(
  () => ({ idle: '待命', connecting: '连接中', open: '实时', closed: '已断开', error: '异常' })[signal.value],
)
</script>

<template>
  <div class="dock" :class="`dock--${dock}`" data-testid="bottom-dock">
    <!-- 输入态 -->
    <div v-if="dock === 'input'" class="composer">
      <div class="composer__title">
        <h1>排队溢出 · 智能决策控制台</h1>
        <p>用一句话描述路口问题，智能体将逐幕推演诊断到方案。</p>
      </div>
      <div class="composer__row">
        <textarea
          v-model="userInput"
          rows="2"
          placeholder="例如：转山西路与经十路交叉口，六点十分到六点半，东向西排队溢出到上游…"
          @keydown.enter.exact.prevent="store.startRun()"
        />
        <button class="run" :disabled="status === 'submitting' || !userInput.trim()" @click="store.startRun()">
          {{ status === 'submitting' ? '推演中…' : '开始推演' }}
        </button>
      </div>
      <div class="chips">
        <button v-for="(e, i) in examples" :key="i" class="chip" @click="userInput = e">{{ e }}</button>
      </div>
    </div>

    <!-- 运行态：流水线进度 -->
    <div v-else-if="dock === 'running'" class="pipeline">
      <span class="signal" :class="`signal--${signal}`"><i />{{ signalText }}</span>
      <span v-if="store.waiting" class="computing" data-testid="computing">
        <span class="computing__spin" />正在{{ store.computingLabel }}推演…
      </span>
      <ol class="nodes">
        <li
          v-for="(a, i) in acts"
          :key="a.id"
          :class="{ on: i === currentAct, past: i < currentAct }"
        >
          <span class="nodes__dot" />
          <span class="nodes__label">{{ a.pipelineNode }}</span>
        </li>
      </ol>
      <div class="bar"><span :style="{ width: progress + '%' }" /></div>
    </div>

    <!-- 方案态：抽屉 -->
    <PlanDrawer v-else />
  </div>
</template>

<style scoped>
.dock {
  transition: height 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.dock--input {
  height: auto;
}
.dock--running {
  height: auto;
}
.dock--plan {
  height: 46vh;
}

/* 输入态 */
.composer {
  padding: 4px 4px 2px;
}
.composer__title h1 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 22px;
  letter-spacing: 2px;
  color: var(--text);
}
.composer__title p {
  margin: 4px 0 12px;
  font-size: 13px;
  color: var(--text-dim);
}
.composer__row {
  display: flex;
  gap: 10px;
}
.composer__row textarea {
  flex: 1;
  resize: none;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--panel-border);
  background: rgba(0, 0, 0, 0.35);
  color: var(--text);
  font-size: 14px;
  font-family: var(--font-body);
}
.composer__row textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-dim);
}
.run {
  flex: 0 0 auto;
  padding: 0 26px;
  border-radius: var(--radius-sm);
  border: none;
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: var(--bg);
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: var(--glow-primary);
}
.run:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.chip {
  max-width: 100%;
  padding: 5px 12px;
  border-radius: 20px;
  border: 1px solid var(--panel-border);
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chip:hover {
  color: var(--primary);
  border-color: var(--primary);
}

/* 运行态 */
.pipeline {
  display: flex;
  align-items: center;
  gap: 16px;
}
.signal {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
  flex: 0 0 auto;
}
.signal i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-mute);
}
.signal--open i {
  background: var(--protected);
  box-shadow: var(--glow-protected);
  animation: pulse 1.4s infinite;
}
.signal--connecting i {
  background: var(--evidence);
  animation: pulse 1s infinite;
}
.signal--error i,
.signal--closed i {
  background: var(--alarm);
}
@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}
.computing {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--evidence);
  flex: 0 0 auto;
}
.computing__spin {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--evidence-dim);
  border-top-color: var(--evidence);
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.nodes {
  display: flex;
  align-items: center;
  gap: 4px;
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  overflow-x: auto;
}
.nodes li {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-mute);
  flex: 0 0 auto;
}
.nodes li::after {
  content: '';
  width: 18px;
  height: 1px;
  background: var(--panel-border);
}
.nodes li:last-child::after {
  display: none;
}
.nodes__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 1px solid var(--text-mute);
}
.nodes li.on {
  color: var(--primary);
}
.nodes li.on .nodes__dot {
  background: var(--primary);
  border-color: var(--primary);
  box-shadow: var(--glow-primary);
}
.nodes li.past {
  color: var(--protected);
}
.nodes li.past .nodes__dot {
  background: var(--protected);
  border-color: var(--protected);
}
.bar {
  flex: 0 0 90px;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.bar span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--primary), var(--protected));
  transition: width 0.5s;
}
</style>

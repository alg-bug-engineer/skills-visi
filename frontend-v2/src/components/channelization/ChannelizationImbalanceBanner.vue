<script setup lang="ts">
defineProps<{
  value: number
}>()
</script>

<template>
  <div class="imbalance-banner" role="status">
    <span class="imb-icon" aria-hidden="true">⚖️</span>
    <span>
      进口失衡系数 <strong>{{ value.toFixed(2) }}</strong>
      — 数值越大，各方向流量越不均衡
    </span>
  </div>
</template>

<style scoped>
.imbalance-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  background: rgba(255, 152, 0, 0.12);
  border: 1px solid rgba(255, 152, 0, 0.25);
  font-size: 11px;
  color: rgba(255, 224, 178, 0.95);
}

.imbalance-banner strong {
  font-family: ui-monospace, monospace;
  color: #ffcc80;
}

.imb-icon {
  font-size: 14px;
  flex-shrink: 0;
}
</style>

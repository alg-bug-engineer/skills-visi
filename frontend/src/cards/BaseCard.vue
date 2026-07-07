<script setup lang="ts">
defineProps<{ title: string; tone?: 'primary' | 'alarm' | 'evidence' | 'protected'; act?: number }>()
</script>

<template>
  <section class="card us-panel" :class="`t-${tone ?? 'primary'}`" data-testid="insight-card">
    <header class="card__hd">
      <span v-if="act != null" class="card__act">幕{{ act }}</span>
      <h3>{{ title }}</h3>
    </header>
    <div class="card__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.card {
  padding: 14px;
  border-left: 3px solid var(--primary);
}
.card.t-alarm {
  border-left-color: var(--alarm);
}
.card.t-evidence {
  border-left-color: var(--evidence);
}
.card.t-protected {
  border-left-color: var(--protected);
}
.card__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.card__act {
  font-family: var(--font-display);
  font-size: 11px;
  color: var(--bg);
  background: var(--primary);
  padding: 1px 6px;
  border-radius: 4px;
}
.t-alarm .card__act {
  background: var(--alarm);
}
.t-evidence .card__act {
  background: var(--evidence);
}
.t-protected .card__act {
  background: var(--protected);
}
.card__hd h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.card__body {
  font-size: 13px;
  color: var(--text-dim);
}
</style>

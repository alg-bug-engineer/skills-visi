<script setup lang="ts">
defineProps<{ title: string; tone?: 'primary' | 'alarm' | 'evidence' | 'protected'; act?: number }>()
</script>

<template>
  <section class="card us-panel" :class="`t-${tone ?? 'primary'}`" data-testid="insight-card">
    <header class="card__hd">
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
  border-radius: 0;
  border: 1px solid rgba(146, 161, 181, 0.45);
  background: rgba(8, 16, 29, 0.76);
  box-shadow: none;
}
.card__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
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

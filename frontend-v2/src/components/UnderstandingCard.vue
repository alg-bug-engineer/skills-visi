<script setup lang="ts">
defineProps<{
  title: string
  fields: Array<{ key: string; label: string; value: string }>
  visible: boolean
}>()
</script>

<template>
  <Transition name="fade">
    <article v-if="visible" class="understanding-card">
      <h3>{{ title }}</h3>
      <dl>
        <div v-for="f in fields" :key="f.key" class="field-row">
          <dt>{{ f.label }}</dt>
          <dd>{{ f.value }}</dd>
        </div>
      </dl>
    </article>
  </Transition>
</template>

<style scoped>
.understanding-card {
  position: absolute;
  left: 20px;
  top: 64px;
  z-index: 7;
  width: min(300px, 38vw);
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(17, 24, 39, 0.92);
  border: 1px solid rgba(66, 153, 225, 0.45);
  color: #e2e8f0;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}

.understanding-card h3 {
  margin: 0 0 10px;
  font-size: 13px;
  color: #90cdf4;
}

.field-row {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

dt {
  color: #a0aec0;
}

dd {
  margin: 0;
  color: #f7fafc;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>

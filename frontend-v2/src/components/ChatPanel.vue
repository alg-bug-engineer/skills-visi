<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { ChatMessage } from '../types/api'
import { DEFAULT_PROMPT } from '../constants'

defineProps<{
  messages: ChatMessage[]
  loading: boolean
  sessionId: string | null
}>()

const emit = defineEmits<{
  send: [content: string]
  newSession: []
}>()

const input = ref('')
const listRef = ref<HTMLElement | null>(null)

async function submit() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  emit('send', text)
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight, behavior: 'smooth' })
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}

const replyTypeLabel: Record<string, string> = {
  follow_up: '追问',
  diagnosis: '诊断',
  skill_created: 'Skill 已固化',
  skill_updated: 'Skill 已更新',
  text: '回复',
  error: '错误',
}
</script>

<template>
  <section class="chat-panel">
    <header class="chat-header">
      <div>
        <h1>交通智能体</h1>
        <p class="subtitle">拥堵诊断 · 对话式交互 · 实时展示执行过程</p>
      </div>
      <div class="header-actions">
        <span v-if="sessionId" class="session-badge">会话 {{ sessionId.slice(0, 8) }}…</span>
        <button type="button" class="btn-secondary" :disabled="loading" @click="emit('newSession')">
          新会话
        </button>
      </div>
    </header>

    <div ref="listRef" class="message-list">
      <div v-if="!messages.length" class="welcome">
        <p>请描述路口拥堵情况，例如：</p>
        <button
          type="button"
          class="example-chip"
          @click="emit('send', DEFAULT_PROMPT)"
        >
          {{ DEFAULT_PROMPT }}
        </button>
      </div>

      <article
        v-for="msg in messages"
        :key="msg.id"
        :class="['message', `role-${msg.role}`]"
      >
        <div class="bubble">
          <span v-if="msg.replyType" class="reply-tag">{{ replyTypeLabel[msg.replyType] ?? msg.replyType }}</span>
          <div class="content" v-text="msg.content" />
        </div>
      </article>

      <div v-if="loading" class="message role-assistant">
        <div class="bubble typing">
          <span /><span /><span />
        </div>
      </div>
    </div>

    <footer class="composer">
      <textarea
        v-model="input"
        rows="2"
        placeholder="输入路口问题…（Enter 发送，Shift+Enter 换行）"
        :disabled="loading"
        @keydown="onKeydown"
      />
      <button type="button" class="btn-primary" :disabled="loading || !input.trim()" @click="submit">
        发送
      </button>
    </footer>
  </section>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f8fafc;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 24px;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
}

.chat-header h1 {
  margin: 0;
  font-size: 20px;
  color: #0f172a;
}

.subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #64748b;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.session-badge {
  font-size: 12px;
  color: #64748b;
  padding: 4px 8px;
  background: #f1f5f9;
  border-radius: 6px;
  font-family: ui-monospace, monospace;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.welcome {
  text-align: center;
  color: #64748b;
  padding: 40px 20px;
}

.example-chip {
  margin-top: 12px;
  padding: 10px 16px;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  font-size: 14px;
  max-width: 480px;
}

.example-chip:hover {
  border-color: #0891b2;
  color: #0e7490;
}

.message {
  display: flex;
}

.message.role-user {
  justify-content: flex-end;
}

.message.role-assistant,
.message.role-system {
  justify-content: flex-start;
}

.bubble {
  max-width: min(640px, 85%);
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.role-user .bubble {
  background: #0891b2;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.role-assistant .bubble,
.role-system .bubble {
  background: #fff;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  border-bottom-left-radius: 4px;
}

.reply-tag {
  display: inline-block;
  margin-bottom: 6px;
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 4px;
  background: #ecfeff;
  color: #0e7490;
}

.typing {
  display: flex;
  gap: 4px;
  padding: 16px;
}

.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  animation: bounce 1.2s infinite;
}

.typing span:nth-child(2) {
  animation-delay: 0.15s;
}
.typing span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  40% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

.composer {
  display: flex;
  gap: 12px;
  padding: 16px 24px 20px;
  border-top: 1px solid #e2e8f0;
  background: #fff;
}

.composer textarea {
  flex: 1;
  resize: none;
  padding: 12px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
}

.composer textarea:focus {
  outline: none;
  border-color: #0891b2;
  box-shadow: 0 0 0 3px rgba(8, 145, 178, 0.15);
}

.btn-primary,
.btn-secondary {
  padding: 10px 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
}

.btn-primary {
  background: #0891b2;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #0e7490;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f1f5f9;
  color: #334155;
  border: 1px solid #e2e8f0;
}

.btn-secondary:hover:not(:disabled) {
  background: #e2e8f0;
}
</style>

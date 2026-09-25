<template>
  <section class="page" data-module="permit">
    <header class="page-head">
      <div>
        <h2>受限空间作业管理</h2>
        <p class="page-desc">维护作业许可单，围绕许可编号、作业类型、作业地点、监护人做登记、筛选与状态流转；签发与驳回按角色权限和归属班组受控。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记作业许可单</button>
        <button class="btn" type="button" @click="exportRows">导出受限空间作业清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>许可编号</span>
        <input v-model="keyword" placeholder="按许可编号检索" />
      </label>
      <label class="filter-item">
        <span>许可状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="filter-bar identity-bar">
      <span class="identity-title">当前操作身份</span>
      <label class="filter-item">
        <span>角色</span>
        <select v-model="session.role">
          <option v-for="role in roleOptions" :key="role" :value="role">{{ role }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>归属班组</span>
        <select v-model="session.team">
          <option v-for="team in teamOptions" :key="team" :value="team">{{ team }}</option>
        </select>
      </label>
      <span class="identity-hint">签发许可、驳回申请仅安全员与值班管理员可执行；非值班管理员只能操作本班组归属的许可单。</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayCell(row, column) }}</td>
          <td class="row-actions">
            <template v-if="actionsFor(row).length">
              <button
                v-for="action in actionsFor(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="action-done">流程已终结</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyHint }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条受限空间作业记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { OPERATOR_ROLES, OPERATOR_TEAMS, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/permit'
const columns = ["许可编号", "作业类型", "作业地点", "归属班组", "监护人", "安全措施", "许可时间", "有效期至", "许可状态"]
const statuses = ["待申请", "已受理", "已许可", "已驳回", "已过期"]
const roleOptions = OPERATOR_ROLES
const teamOptions = OPERATOR_TEAMS
// 状态机与后端保持一致：终结态的许可单不再暴露任何动作，驳回后不能再次签发
const STATUS_ACTIONS: Record<string, string[]> = {
  '待申请': ['提交申请', '驳回申请'],
  '已受理': ['签发许可', '驳回申请'],
}

const session = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '待受理许可', value: 0 },
  { label: '有效许可', value: 0 },
  { label: '即将到期许可', value: 0 },
])
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')

const hasFilter = computed(() => Boolean(keyword.value.trim() || statusFilter.value))
const emptyHint = computed(() =>
  hasFilter.value
    ? '当前筛选条件下没有匹配的作业许可单，可调整条件或重置后再试'
    : '暂无受限空间作业数据，可先登记作业许可单',
)

function displayCell(row: Row, column: string): string {
  if (column === '许可状态') {
    return String(row['许可状态'] ?? row.status ?? '—')
  }
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function actionsFor(row: Row): string[] {
  return STATUS_ACTIONS[String(row.status ?? '')] ?? []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '作业许可单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action },
        operator: { name: session.operator, role: session.role, team: session.team },
      }),
    })
    const payload = (await response.json().catch(() => null)) as
      | { ok: boolean; message?: string }
      | null
    if (!response.ok) {
      const detail = payload && 'message' in payload ? payload.message : null
      throw new Error(detail ?? '受限空间作业动作未生效，请稍后重试')
    }
    if (!payload?.ok) {
      errorMessage.value = payload?.message ?? '受限空间作业动作未生效'
      return
    }
    noticeMessage.value = payload.message ?? `作业许可单已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '受限空间作业操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok) {
      throw new Error('作业许可单列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      const summary = await summaryResponse.json()
      stats.value = [
        { label: '待受理许可', value: summary['待处理'] ?? 0 },
        { label: '有效许可', value: summary['已许可'] ?? 0 },
        { label: '即将到期许可', value: summary['即将到期'] ?? 0 },
      ]
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '受限空间作业列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.identity-bar {
  align-items: center;
  margin-bottom: 12px;
}
.identity-title {
  font-size: 12px;
  color: var(--muted);
}
.identity-hint {
  font-size: 12px;
  color: var(--muted);
}
.action-done {
  color: var(--muted);
  font-size: 12px;
}
.notice-text {
  color: #176a3c;
}
</style>

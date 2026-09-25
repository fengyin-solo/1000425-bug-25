<template>
  <section class="page" data-module="permit">
    <header class="page-head">
      <div>
        <h2>受限空间作业管理</h2>
        <p class="page-desc">维护作业许可单：申请人提交、监护人签字、签发人按归属班组签发或驳回；被驳回的许可单终态归档，不能重复签发。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记作业许可单</button>
        <button class="btn" type="button" @click="exportRows">导出受限空间作业清单</button>
      </div>
    </header>

    <div class="identity-bar">
      <span>当前身份（签发与驳回按此校验）：</span>
      <select v-model="session.role" aria-label="当前角色">
        <option v-for="r in ROLES" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="session.team" aria-label="当前班组">
        <option v-for="t in TEAMS" :key="t" :value="t">{{ t }}</option>
      </select>
      <input v-model="session.operator" placeholder="操作人姓名" aria-label="操作人姓名" />
      <span class="identity-hint">申请人提交申请 · 监护人签字确认 · 签发人签发/驳回；仅归属本班组的许可单可操作</span>
    </div>

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
          <option v-for="s in filterStatuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="row-actions">
            <template v-if="availableActions(row).length">
              <button
                v-for="action in availableActions(row)"
                :key="action.name"
                class="link"
                type="button"
                :title="action.reason"
                @click="runAction(action.name, row)"
              >
                {{ action.name }}
              </button>
            </template>
            <span v-else class="muted-text">{{ blockedReason(row) }}</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条受限空间作业记录{{ hasFilter ? '（当前筛选条件下）' : '' }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记作业许可单</h3>
        <p class="muted-text">归属班组只能选择受控班组；同一许可编号被驳回后不可重复登记。</p>
        <label v-for="field in createFields" :key="field.key" class="modal-field">
          <span>{{ field.label }}<em v-if="field.required">*</em></span>
          <select v-if="field.key === '归属班组'" v-model="createForm[field.key]">
            <option value="" disabled>请选择受控班组</option>
            <option v-for="t in TEAMS" :key="t" :value="t">{{ t }}</option>
          </select>
          <input v-else v-model="createForm[field.key]" :placeholder="`请输入${field.label}`" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="creating = false">取消</button>
          <button class="btn primary" type="submit">提交登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { ROLES, TEAMS, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/permit'
const columns = ['许可编号', '作业类型', '作业地点', '归属班组', '监护人', '监护人签字', '许可时间', '有效期至', '许可状态']
const ACTIONS = ['提交申请', '监护人签字', '签发许可', '驳回申请']
const filterStatuses = ['待处理', '待申请', '已受理', '已许可', '已驳回', '已过期']

const session = useSessionStore()

const createFields = [
  { key: '许可编号', label: '许可编号', required: true },
  { key: '作业类型', label: '作业类型', required: true },
  { key: '作业地点', label: '作业地点', required: true },
  { key: '归属班组', label: '归属班组', required: true },
  { key: '监护人', label: '监护人', required: false },
  { key: '安全措施', label: '安全措施', required: false },
  { key: '有效期至', label: '有效期至（YYYY-MM-DD）', required: false },
] as const

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const stats = ref([
  { label: '待处理许可', value: 0 },
  { label: '有效许可', value: 0 },
  { label: '即将到期许可', value: 0 },
])

const creating = ref(false)
const createError = ref('')
const emptyForm = () => ({
  许可编号: '',
  作业类型: '',
  作业地点: '',
  归属班组: '',
  监护人: '',
  安全措施: '',
  有效期至: '',
})
const createForm = reactive(emptyForm())

const hasFilter = computed(() => Boolean(keyword.value.trim() || statusFilter.value))
const emptyText = computed(() =>
  hasFilter.value
    ? '当前筛选条件下没有匹配的作业许可单，请调整许可编号或状态后重试'
    : '暂无受限空间作业数据，可点击右上角「登记作业许可单」先录入一条许可单',
)

function displayValue(row: Row, column: string): string {
  if (column === '许可状态') {
    return String(row.status ?? '—')
  }
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function actionReason(action: string, row: Row): string {
  const status = String(row.status ?? '')
  const owned = String(row['归属班组'] ?? '') === session.team
  if (!owned) {
    return `归属班组为「${row['归属班组'] ?? '未填写'}」，当前班组「${session.team}」无权操作`
  }
  if (action === '提交申请') {
    if (session.role !== '申请人') return '仅申请人角色可提交申请'
    if (status !== '待申请') return `当前为「${status}」，无需重复提交`
  }
  if (action === '监护人签字') {
    if (session.role !== '监护人') return '仅监护人角色可签字确认'
    if (status !== '已受理') return '受理后的许可单才能签字'
    if (row['监护人签字']) return '监护人已签字'
  }
  if (action === '签发许可') {
    if (session.role !== '签发人') return '仅签发人角色可签发'
    if (status !== '已受理') return '只有已受理的许可单可签发'
    if (!row['监护人签字']) return '监护人尚未签字，不能签发'
  }
  if (action === '驳回申请') {
    if (session.role !== '签发人') return '仅签发人角色可驳回'
    if (status !== '待申请' && status !== '已受理') return `当前为「${status}」终态，不能再驳回`
  }
  return ''
}

function availableActions(row: Row): { name: string; reason: string }[] {
  return ACTIONS
    .map((name) => ({ name, reason: actionReason(name, row) }))
    .filter((item) => item.reason === '')
}

function blockedReason(row: Row): string {
  const status = String(row.status ?? '')
  if (['已驳回', '已许可', '已过期'].includes(status)) {
    return `「${status}」终态，无待执行动作`
  }
  if (String(row['归属班组'] ?? '') !== session.team) {
    return '非本班组归属，无权操作'
  }
  return '当前角色在此状态下无可执行动作'
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
  createError.value = ''
  Object.assign(createForm, emptyForm())
  creating.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      createError.value = payload?.detail || payload?.message || '作业许可单登记失败'
      return
    }
    creating.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '作业许可单登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          action,
          operator: session.operator,
          role: session.role,
          team: session.team,
        },
      }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      // 后端按角色/归属/前置状态/监护人签字给出的中文校验原因，原样透出给用户
      throw new Error(payload?.detail || payload?.message || '受限空间作业动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '受限空间作业操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) {
    query.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  const suffix = query.toString()
  try {
    const response = await request(`${ENDPOINT}${suffix ? `?${suffix}` : ''}`)
    if (!response.ok) {
      throw new Error('作业许可单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    rows.value = []
    total.value = 0
    errorMessage.value = error instanceof Error ? error.message : '受限空间作业列表读取失败'
  }
}

async function loadSummary() {
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    const source: Record<string, number> = payload?.stats ?? {}
    stats.value = stats.value.map((item) => ({ ...item, value: source[item.label] ?? 0 }))
  } catch {
    // 统计加载失败不影响列表使用，卡片保持 0
  }
}

onMounted(() => {
  void reload()
  void loadSummary()
})
</script>

<style scoped>
.identity-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.identity-bar select,
.identity-bar input {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.identity-hint {
  color: var(--muted);
  font-size: 12px;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 460px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal-card h3 {
  margin: 0 0 4px;
}
.modal-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 10px;
  font-size: 13px;
}
.modal-field em {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.modal-field input,
.modal-field select {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>

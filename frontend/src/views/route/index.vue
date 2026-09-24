<template>
  <section class="page" data-module="route">
    <header class="page-head">
      <div>
        <h2>线路管理</h2>
        <p class="page-desc">维护配送线路：站点调整先存草稿，启用后正式生效；列表途经站点数量与详情同源。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出线路管理清单</button>
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
        <span>线路编码</span>
        <input v-model="keyword" placeholder="按线路编码检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
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
          <td>
            <router-link class="link" :to="`/route/${row.id}`">{{ row['线路编码'] ?? '—' }}</router-link>
          </td>
          <td>{{ row['线路名称'] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td>{{ row['起点冷库'] ?? '—' }}</td>
          <td>{{ row['终点冷库'] ?? '—' }}</td>
          <td>
            {{ row['途经站点'] ?? '—' }}
            <span class="count-tag">{{ row['途经站点数量'] }} 站</span>
            <span v-if="row.has_draft_changes" class="draft-tag" title="有未启用的草稿改动">草稿待启用</span>
          </td>
          <td>
            <button
              v-if="canAction('启用线路', row)"
              class="link"
              type="button"
              @click="runAction('启用线路', row)"
            >
              {{ row.status === '已停用' ? '启用（恢复上次排列）' : '启用线路' }}
            </button>
            <button
              v-if="canAction('停用线路', row)"
              class="link"
              type="button"
              @click="runAction('停用线路', row)"
            >
              停用线路
            </button>
            <router-link class="link" :to="`/route/${row.id}`">调整站点</router-link>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无线路管理数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条线路记录</span>
      <span v-if="message" :class="actionOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Version = { 起点冷库: string; 终点冷库: string; 途经站点: string[] }

type Row = {
  id: number
  status: string
  has_draft_changes: boolean
  途经站点数量: number
  途经站点: string
  [key: string]: string | number | boolean | null | Version | Version[]
}

const ENDPOINT = '/api/route'
const columns = ['线路编码', '线路名称', '状态', '起点冷库', '终点冷库', '途经站点']
const statuses = ['草稿', '已启用', '已停用']

const rows = ref<Row[]>([])
const total = ref(0)
const message = ref('')
const actionOk = ref(true)
const keyword = ref('')
const statusFilter = ref('')

const stats = computed(() => {
  const active = rows.value.filter((row) => row.status === '已启用').length
  const disabled = rows.value.filter((row) => row.status === '已停用').length
  return [
    { label: '已启用线路', value: active },
    { label: '草稿待启用', value: rows.value.filter((row) => row.has_draft_changes).length },
    { label: '已停用线路', value: disabled },
  ]
})

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function canAction(action: '启用线路' | '停用线路', row: Row): boolean {
  if (action === '启用线路') return row.status !== '已启用'
  return row.status === '已启用'
}

async function runAction(action: '启用线路' | '停用线路', row: Row) {
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    actionOk.value = payload.ok
    message.value = payload.message || (payload.ok ? '操作已生效' : '操作未生效')
    await reload()
  } catch (error) {
    actionOk.value = false
    message.value = error instanceof Error ? error.message : '线路操作失败'
  }
}

async function reload() {
  message.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('配送线路列表读取失败')
    }
    const payload = (await response.json()) as { items: Row[]; total: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    actionOk.value = false
    message.value = error instanceof Error ? error.message : '线路管理列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.count-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 10px;
  background: #eef4ff;
  color: var(--brand);
  font-size: 12px;
}
.draft-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 10px;
  background: #fff7e6;
  color: #b54708;
  font-size: 12px;
}
.ok-text {
  color: #067647;
}
select {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
</style>

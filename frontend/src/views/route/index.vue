<template>
  <section class="page" data-module="route">
    <header class="page-head">
      <div>
        <h2>线路管理</h2>
        <p class="page-desc">维护配送线路，途经站点调整先存草稿，启用后才正式生效；停用再启用上一次的站点排列。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记配送线路</button>
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
        <input v-model="filters.keyword" placeholder="按线路编码检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['线路编码'] ?? '—' }}</td>
          <td>{{ row['线路名称'] ?? '—' }}</td>
          <td>{{ row['起点冷库'] ?? '—' }}</td>
          <td>{{ row['终点冷库'] ?? '—' }}</td>
          <!-- 途经站点数量与详情页同一份口径，避免列表与详情对不上 -->
          <td>{{ stationCount(row) }} 个</td>
          <td>{{ row['预计时长'] ?? '—' }}</td>
          <td>{{ row['线路里程'] ?? '—' }}</td>
          <td>
            <span :class="['status-tag', statusClass(row.status)]">{{ row.status }}</span>
            <span v-if="row.draft" class="draft-mark" title="该线路保留了一份草稿，进入详情可继续调整">有草稿</span>
            <p v-if="row.notice" class="cell-notice" :title="row.notice">{{ row.notice }}</p>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">线路详情</button>
            <button
              v-for="action in availableActions(row.status)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无线路数据，可先登记配送线路</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条线路记录</span>
      <span v-if="messageText" :class="messageOk ? 'ok-text' : 'error-text'">{{ messageText }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import type { RouteEntry } from './types'

const ENDPOINT = '/api/route'
const columns = ['线路编码', '线路名称', '起点冷库', '终点冷库', '途经站点', '预计时长', '线路里程']
const statuses = ['草稿', '已启用', '已停用']
const stats = [
  { label: '启用线路', value: 0 },
  { label: '平均配送时长', value: 0 },
  { label: '停用线路', value: 0 },
]

const router = useRouter()
const rows = ref<RouteEntry[]>([])
const total = ref(0)
const messageText = ref('')
const messageOk = ref(true)
const filters = ref<Record<string, string>>({})

function stationCount(row: RouteEntry): number {
  return Number(row['站点数'] ?? 0)
}

function statusClass(status: string): string {
  if (status === '已启用') return 'status-on'
  if (status === '已停用') return 'status-off'
  return 'status-draft'
}

// 列表只放行最直接的动作；停用后再调整可以先「启用线路」恢复，或进详情操作
function availableActions(status: string): string[] {
  if (status === '草稿') return ['启用线路']
  if (status === '已启用') return ['调整站点', '停用线路']
  return ['启用线路']
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  messageText.value = '配送线路登记入口尚未接入审批流'
  messageOk.value = false
}

function openDetail(row: RouteEntry) {
  void router.push(`/route/${row.id}`)
}

async function runAction(action: string, row: RouteEntry) {
  messageText.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '线路动作未生效，请稍后重试')
    }
    messageText.value = payload.message
    messageOk.value = true
    await reload()
  } catch (error) {
    messageText.value = error instanceof Error ? error.message : '线路操作失败'
    messageOk.value = false
  }
}

async function reload() {
  messageText.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('配送线路列表读取失败')
    }
    const payload = (await response.json()) as { items?: RouteEntry[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    messageText.value = error instanceof Error ? error.message : '线路列表读取失败'
    messageOk.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.status-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.status-draft {
  background: #fffaeb;
  color: #b54708;
  border: 1px solid #fedf89;
}
.status-on {
  background: #ecfdf3;
  color: #027a48;
  border: 1px solid #abefc6;
}
.status-off {
  background: #f2f4f7;
  color: #475467;
  border: 1px solid #d0d5dd;
}
.draft-mark {
  margin-left: 6px;
  font-size: 12px;
  color: #b54708;
}
.cell-notice {
  margin: 4px 0 0;
  font-size: 12px;
  color: #b42318;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ok-text {
  color: #027a48;
}
</style>

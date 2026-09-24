<template>
  <section class="page route-detail" data-module="route-detail">
    <header class="page-head">
      <div>
        <button class="btn ghost back-btn" type="button" @click="goBack">← 返回线路列表</button>
        <h2>{{ form['线路名称'] || '线路详情' }}（{{ form['线路编码'] }}）</h2>
        <p class="page-desc">
          当前状态：<span :class="['status-tag', statusClass(entry?.status)]">{{ entry?.status ?? '—' }}</span>
          <span v-if="entry?.draft" class="draft-mark">· 存在未发布草稿（{{ entry.draft['站点数'] }} 个站点）</span>
        </p>
      </div>
    </header>

    <div v-if="noticeText" class="notice-banner" :class="{ 'notice-warn': !noticeOk }">
      {{ noticeText }}
    </div>

    <div v-if="loading" class="loading-state">线路详情加载中…</div>

    <template v-else-if="entry">
      <form class="detail-card" @submit.prevent="saveDraft">
        <h3>草稿站点排列</h3>
        <p class="card-hint">
          <template v-if="editing">改动随时「保存草稿」，刷新页面或返回列表再进来都不会丢；点「启用线路」后草稿才正式生效。</template>
          <template v-else>当前不是草稿状态，排列为只读；需要改动时请执行「调整站点」，系统会先复制一份草稿。</template>
        </p>

        <div class="form-grid">
          <label class="form-item">
            <span>线路编码</span>
            <input v-model="form['线路编码']" disabled />
          </label>
          <label class="form-item">
            <span>线路名称</span>
            <input v-model="form['线路名称']" :disabled="!editing" placeholder="给线路起个名字" />
          </label>
          <label class="form-item">
            <span>起点冷库</span>
            <input v-model="form['起点冷库']" :disabled="!editing" placeholder="如：华东一号冷库" />
          </label>
          <label class="form-item">
            <span>终点冷库</span>
            <input v-model="form['终点冷库']" :disabled="!editing" placeholder="如：滨江中转站" />
          </label>
          <label class="form-item">
            <span>预计时长</span>
            <input v-model="form['预计时长']" :disabled="!editing" placeholder="如：2小时10分" />
          </label>
          <label class="form-item">
            <span>线路里程</span>
            <input v-model="form['线路里程']" :disabled="!editing" placeholder="如：38公里" />
          </label>
        </div>

        <fieldset class="station-editor" :disabled="!editing">
          <legend>途经站点（按配送先后排序，共 {{ stations.length }} 个）</legend>
          <div v-for="(station, index) in stations" :key="`${index}-${station}`" class="station-row">
            <span class="station-index">{{ index + 1 }}</span>
            <input v-model="stations[index]" :placeholder="`第 ${index + 1} 个站点`" />
            <button class="btn" type="button" :disabled="!editing || index === 0" @click="moveStation(index, -1)">上移</button>
            <button class="btn" type="button" :disabled="!editing || index === stations.length - 1" @click="moveStation(index, 1)">下移</button>
            <button class="btn danger" type="button" :disabled="!editing" @click="removeStation(index)">删除</button>
          </div>
          <div v-if="!stations.length" class="empty-stations">还没有途经站点，请在下方新增；空草稿无法启用。</div>
          <div class="station-add">
            <input v-model="newStation" placeholder="输入站点名称后追加" @keyup.enter.prevent="addStation" />
            <button class="btn" type="button" :disabled="!editing" @click="addStation">追加站点</button>
          </div>
        </fieldset>

        <div class="detail-actions">
          <button v-if="editing" class="btn primary" type="submit" :disabled="saving">保存草稿</button>
          <button v-if="entry.status === '草稿'" class="btn primary" type="button" :disabled="busy" @click="doAction('启用线路')">启用线路（正式生效）</button>
          <button v-if="entry.status === '草稿' && entry.active" class="btn danger" type="button" :disabled="busy" @click="recycleDraft">回收草稿</button>
          <button v-if="entry.status === '已启用'" class="btn" type="button" :disabled="busy" @click="doAction('调整站点')">调整站点</button>
          <button v-if="entry.status === '已启用'" class="btn" type="button" :disabled="busy" @click="doAction('停用线路')">停用线路</button>
          <template v-if="entry.status === '已停用'">
            <button class="btn primary" type="button" :disabled="busy" @click="doAction('启用线路')">启用线路（恢复上一次排列）</button>
            <button class="btn" type="button" :disabled="busy" @click="doAction('调整站点')">调整站点</button>
          </template>
        </div>
        <p v-if="busy" class="action-hint">操作提交中…</p>
      </form>

      <div class="version-row">
        <article class="version-card">
          <h3>上一次已启用版本</h3>
          <p v-if="!entry.active" class="card-hint">该线路还从未启用过，暂无正式版本。</p>
          <template v-else>
            <p class="card-hint">共 {{ entry.active['站点数'] }} 个站点{{ entry.status === '已停用' ? '（停用时保留）' : '' }}</p>
            <ol class="station-plan">
              <li v-for="station in entry.active['途经站点']" :key="station">{{ station }}</li>
            </ol>
            <dl class="meta-list">
              <div><dt>起点冷库</dt><dd>{{ entry.active['起点冷库'] || '—' }}</dd></div>
              <div><dt>终点冷库</dt><dd>{{ entry.active['终点冷库'] || '—' }}</dd></div>
            </dl>
          </template>
        </article>

        <article class="version-card">
          <h3>当前草稿版本</h3>
          <p v-if="!entry.draft" class="card-hint">没有保留中的草稿；「调整站点」后会生成一份。</p>
          <template v-else>
            <p class="card-hint">
              共 {{ entry.draft['站点数'] }} 个站点
              <span v-if="entry.draft_source">（由「{{ entry.draft_source }}」时复制）</span>
            </p>
            <ol class="station-plan">
              <li v-for="station in entry.draft['途经站点']" :key="station">{{ station }}</li>
            </ol>
            <dl class="meta-list">
              <div><dt>起点冷库</dt><dd>{{ entry.draft['起点冷库'] || '—' }}</dd></div>
              <div><dt>终点冷库</dt><dd>{{ entry.draft['终点冷库'] || '—' }}</dd></div>
            </dl>
          </template>
        </article>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import type { RouteActionResult, RouteEntry } from './types'

const ENDPOINT = '/api/route'
const router = useRouter()
const route = useRoute()

const entry = ref<RouteEntry | null>(null)
const loading = ref(true)
const busy = ref(false)
const saving = ref(false)
const noticeText = ref('')
const noticeOk = ref(true)
const newStation = ref('')

const form = reactive<Record<string, string>>({
  线路编码: '',
  线路名称: '',
  起点冷库: '',
  终点冷库: '',
  预计时长: '',
  线路里程: '',
})
const stations = ref<string[]>([])

const editing = computed(() => entry.value?.status === '草稿')
const entryId = computed(() => Number(route.params.id))

function statusClass(status?: string): string {
  if (status === '已启用') return 'status-on'
  if (status === '已停用') return 'status-off'
  return 'status-draft'
}

function goBack() {
  void router.push('/route')
}

function hydrate(next: RouteEntry) {
  entry.value = next
  form['线路编码'] = next['线路编码'] ?? ''
  form['线路名称'] = next['线路名称'] ?? ''
  form['起点冷库'] = next['起点冷库'] ?? ''
  form['终点冷库'] = next['终点冷库'] ?? ''
  form['预计时长'] = next['预计时长'] ?? ''
  form['线路里程'] = next['线路里程'] ?? ''
  stations.value = [...(next['途经站点'] ?? [])]
  noticeText.value = next.notice ?? ''
  noticeOk.value = !next.notice
}

async function loadEntry() {
  loading.value = true
  try {
    const response = await request(`${ENDPOINT}/${entryId.value}`)
    if (!response.ok) {
      throw new Error('线路详情读取失败')
    }
    hydrate((await response.json()) as RouteEntry)
  } catch (error) {
    noticeText.value = error instanceof Error ? error.message : '线路详情读取失败'
    noticeOk.value = false
  } finally {
    loading.value = false
  }
}

function addStation() {
  const name = newStation.value.trim()
  if (!name) return
  stations.value.push(name)
  newStation.value = ''
}

function removeStation(index: number) {
  stations.value.splice(index, 1)
}

function moveStation(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= stations.value.length) return
  const list = stations.value
  ;[list[index], list[target]] = [list[target], list[index]]
}

function draftPayload() {
  return {
    线路名称: form['线路名称'],
    起点冷库: form['起点冷库'],
    终点冷库: form['终点冷库'],
    预计时长: form['预计时长'],
    线路里程: form['线路里程'],
    途经站点: stations.value.map((item) => item.trim()).filter(Boolean),
  }
}

async function saveDraft() {
  saving.value = true
  try {
    const response = await request(`${ENDPOINT}/${entryId.value}/draft`, {
      method: 'PUT',
      body: JSON.stringify({ values: draftPayload() }),
    })
    const payload = (await response.json()) as RouteActionResult
    if (!response.ok || !payload.ok || !payload.entry) {
      throw new Error(payload.message || '草稿保存失败')
    }
    hydrate(payload.entry)
    noticeText.value = payload.message
    noticeOk.value = true
  } catch (error) {
    noticeText.value = error instanceof Error ? error.message : '草稿保存失败'
    noticeOk.value = false
  } finally {
    saving.value = false
  }
}

async function doAction(action: string) {
  busy.value = true
  try {
    // 草稿状态下先把页面上未保存的改动落库，避免点启用时丢掉刚排好的站点
    if (action === '启用线路' && editing.value) {
      const saveResponse = await request(`${ENDPOINT}/${entryId.value}/draft`, {
        method: 'PUT',
        body: JSON.stringify({ values: draftPayload() }),
      })
      const saved = (await saveResponse.json()) as RouteActionResult
      if (!saveResponse.ok || !saved.ok || !saved.entry) {
        throw new Error(saved.message || '草稿保存失败，未能启用')
      }
      hydrate(saved.entry)
    }
    const response = await request(`${ENDPOINT}/${entryId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as RouteActionResult
    if (!response.ok || !payload.ok || !payload.entry) {
      throw new Error(payload.message || '线路动作未生效')
    }
    hydrate(payload.entry)
    noticeText.value = payload.message
    noticeOk.value = true
  } catch (error) {
    noticeText.value = error instanceof Error ? error.message : '线路操作失败'
    noticeOk.value = false
  } finally {
    busy.value = false
  }
}

async function recycleDraft() {
  busy.value = true
  try {
    const response = await request(`${ENDPOINT}/${entryId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action: '回收草稿' }),
    })
    const payload = (await response.json()) as RouteActionResult
    if (!response.ok || !payload.ok || !payload.entry) {
      throw new Error(payload.message || '草稿回收失败')
    }
    hydrate(payload.entry)
    noticeText.value = payload.message
    noticeOk.value = true
  } catch (error) {
    noticeText.value = error instanceof Error ? error.message : '草稿回收失败'
    noticeOk.value = false
  } finally {
    busy.value = false
  }
}

onMounted(loadEntry)
</script>

<style scoped>
.back-btn {
  margin-bottom: 8px;
  padding-left: 0;
}
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
  color: #b54708;
  font-size: 13px;
}
.notice-banner {
  margin: 8px 0 12px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  background: #ecfdf3;
  border: 1px solid #abefc6;
  color: #027a48;
}
.notice-banner.notice-warn {
  background: #fef3f2;
  border-color: #fecdca;
  color: #b42318;
}
.loading-state {
  padding: 24px;
  text-align: center;
  color: var(--muted);
}
.detail-card,
.version-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.detail-card h3,
.version-card h3 {
  margin: 0 0 6px;
  font-size: 15px;
}
.card-hint {
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 12px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 14px;
  margin-bottom: 12px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 2px;
}
.form-item input {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.station-editor {
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 12px;
}
.station-editor legend {
  padding: 0 6px;
  font-size: 13px;
  color: var(--muted);
}
.station-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.station-index {
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: #f2f4f7;
  font-size: 12px;
  color: #475467;
  flex: none;
}
.station-row input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.station-add {
  display: flex;
  gap: 8px;
}
.station-add input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.empty-stations {
  color: #b42318;
  font-size: 13px;
  padding: 4px 0 8px;
}
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.btn.danger {
  border-color: #fecdca;
  color: #b42318;
}
.action-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted);
}
.version-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.station-plan {
  margin: 0 0 10px;
  padding-left: 22px;
  font-size: 13px;
}
.station-plan li {
  padding: 2px 0;
}
.meta-list {
  margin: 0;
  font-size: 13px;
}
.meta-list div {
  display: flex;
  gap: 8px;
}
.meta-list dt {
  color: var(--muted);
  width: 64px;
}
.meta-list dd {
  margin: 0;
}
</style>

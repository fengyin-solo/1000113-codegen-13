<template>
  <section class="page" data-module="route-detail">
    <header class="page-head">
      <div>
        <h2>线路详情 · {{ entry?.['线路编码'] ?? '…' }}</h2>
        <p class="page-desc">
          <router-link class="link" to="/route">← 返回线路列表</router-link>
          <span v-if="entry" class="status-chip">{{ entry.status }}</span>
          <span v-if="entry?.has_draft_changes" class="draft-tag">草稿有未启用改动</span>
        </p>
      </div>
    </header>

    <div v-if="notice" class="notice-bar" :class="noticeKind">{{ notice }}</div>
    <p v-else-if="entry" class="hint-text">
      途经站点、起点冷库、终点冷库的调整只保存为草稿，刷新或返回列表再进入都不会丢失；点「启用线路」后才正式生效。
    </p>

    <div v-if="entry" class="detail-grid">
      <article class="panel">
        <h3>草稿编辑（当前工作版本 · {{ draftSites.length }} 站）</h3>
        <label class="form-item">
          <span>起点冷库 *</span>
          <input v-model="draftStart" placeholder="请输入起点冷库" />
        </label>
        <label class="form-item">
          <span>终点冷库</span>
          <input v-model="draftEnd" placeholder="请输入终点冷库" />
        </label>

        <div class="form-item">
          <span>途经站点 *（按配送顺序排列，支持顿号/逗号批量粘贴）</span>
          <textarea
            v-model="stationText"
            rows="3"
            placeholder="例如：中央冷库、滨河中转站、城东菜场、城东配送中心"
          ></textarea>
        </div>

        <ol v-if="draftSites.length" class="site-list">
          <li v-for="(site, index) in draftSites" :key="`${site}-${index}`">
            <span class="site-index">{{ index + 1 }}</span>
            <span class="site-name">{{ site }}</span>
            <span class="site-ops">
              <button class="link" type="button" :disabled="index === 0" @click="moveSite(index, -1)">上移</button>
              <button
                class="link"
                type="button"
                :disabled="index === draftSites.length - 1"
                @click="moveSite(index, 1)"
              >
                下移
              </button>
              <button class="link danger" type="button" @click="removeSite(index)">删除</button>
            </span>
          </li>
        </ol>

        <div class="panel-actions">
          <button class="btn primary" type="button" @click="saveDraft">保存草稿</button>
          <button
            v-if="entry.active_version"
            class="btn"
            type="button"
            :disabled="!hasLocalChanges"
            title="放弃当前草稿，沿用上一次已启用的排列"
            @click="discardDraft"
          >
            回收草稿
          </button>
        </div>
        <p v-if="!hasLocalChanges" class="hint-text">草稿与已保存内容一致。</p>
      </article>

      <article class="panel">
        <h3>版本对照</h3>
        <section class="version-block">
          <h4>草稿版本（{{ entry.draft_version.途经站点.length }} 站）</h4>
          <p class="version-line">{{ versionText(entry.draft_version) }}</p>
        </section>
        <section v-if="entry.active_version" class="version-block">
          <h4>
            上一次已启用版本（{{ entry.active_version.途经站点.length }} 站）
            <span v-if="entry.status === '已停用'" class="muted">停用后再启用将恢复此排列</span>
          </h4>
          <p class="version-line">{{ versionText(entry.active_version) }}</p>
        </section>
        <section v-else class="version-block">
          <h4 class="muted">尚无已启用版本</h4>
          <p class="hint-text">该线路还没启用过，启用后草稿会成为第一份正式版本。</p>
        </section>
        <section v-if="entry.retained_draft" class="version-block">
          <h4>启用前保留的草稿（{{ entry.retained_draft.途经站点.length }} 站）</h4>
          <p class="version-line muted">{{ versionText(entry.retained_draft) }}</p>
          <p class="hint-text">再启用时恢复的是上一次生效排列；这份草稿只保留备查，不会自动生效。</p>
        </section>

        <div class="panel-actions">
          <button v-if="entry.status !== '已启用'" class="btn primary" type="button" @click="activate">
            {{ entry.status === '已停用' ? '启用（恢复上次排列）' : '启用线路' }}
          </button>
          <button v-if="entry.status === '已启用'" class="btn" type="button" @click="disable">停用线路</button>
        </div>
      </article>
    </div>

    <footer class="page-foot">
      <span v-if="message" :class="actionOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

const props = defineProps<{ id: string }>()

type Version = { 起点冷库: string; 终点冷库: string; 途经站点: string[] }

type Entry = {
  id: number
  status: string
  notice: string
  has_draft_changes: boolean
  draft_version: Version
  active_version: Version | null
  retained_draft: Version | null
  [key: string]: string | number | boolean | null | Version
}

const ENDPOINT = `/api/route/${props.id}`

const entry = ref<Entry | null>(null)
const draftStart = ref('')
const draftEnd = ref('')
const draftSites = ref<string[]>([])
const message = ref('')
const actionOk = ref(true)
const loadedDraftKey = ref('')

const SITE_RE = /[、，,;；\n]+/

const stationText = computed<string>({
  get: () => draftSites.value.join('、'),
  set: (text: string) => {
    draftSites.value = text
      .split(SITE_RE)
      .map((item) => item.trim())
      .filter(Boolean)
  },
})

const currentDraftKey = computed(() =>
  JSON.stringify([draftStart.value.trim(), draftEnd.value.trim(), draftSites.value]),
)
const hasLocalChanges = computed(() => currentDraftKey.value !== loadedDraftKey.value)

const notice = computed(() => entry.value?.notice || '')
const noticeKind = computed(() => (notice.value.includes('回收') ? 'notice-warn' : 'notice-info'))

function versionText(version: Version): string {
  return `${version.起点冷库 || '—'} → ${version.途经站点.join('、') || '—'} → ${version.终点冷库 || '—'}`
}

function moveSite(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= draftSites.value.length) return
  const sites = [...draftSites.value]
  const [item] = sites.splice(index, 1)
  sites.splice(target, 0, item)
  draftSites.value = sites
}

function removeSite(index: number) {
  draftSites.value = draftSites.value.filter((_, current) => current !== index)
}

function hydrateEditor(data: Entry) {
  draftStart.value = data.draft_version.起点冷库
  draftEnd.value = data.draft_version.终点冷库
  draftSites.value = [...data.draft_version.途经站点]
  loadedDraftKey.value = currentDraftKey.value
}

async function load() {
  try {
    const response = await request(ENDPOINT)
    if (!response.ok) {
      throw new Error('线路详情读取失败')
    }
    entry.value = (await response.json()) as Entry
    hydrateEditor(entry.value)
  } catch (error) {
    actionOk.value = false
    message.value = error instanceof Error ? error.message : '线路详情读取失败'
  }
}

async function postAction(values: Record<string, string>): Promise<boolean> {
  message.value = ''
  try {
    const response = await request(ENDPOINT + '/actions', {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    actionOk.value = payload.ok
    message.value = payload.message
    if (payload.ok) await load()
    return payload.ok
  } catch (error) {
    actionOk.value = false
    message.value = error instanceof Error ? error.message : '线路操作失败'
    return false
  }
}

function saveDraft() {
  void submitDraft()
}

async function submitDraft(): Promise<boolean> {
  return postAction({
    action: '调整站点',
    起点冷库: draftStart.value,
    终点冷库: draftEnd.value,
    途经站点: draftSites.value.join('、'),
  })
}

function discardDraft() {
  void postAction({ action: '回收草稿' })
}

async function activate() {
  // 启用前先把未保存的编辑存成草稿，避免页面上的改动在启用时被忽略
  if (hasLocalChanges.value) {
    const ok = await submitDraft()
    if (!ok) return
  }
  await postAction({ action: '启用线路' })
}

function disable() {
  void postAction({ action: '停用线路' })
}

onMounted(load)
</script>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 12px;
}
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}
.panel h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.form-item {
  display: block;
  margin-bottom: 10px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item input,
.form-item textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.site-list {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
}
.site-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 6px;
  font-size: 13px;
}
.site-index {
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  border-radius: 50%;
  background: #eef4ff;
  color: var(--brand);
  font-size: 12px;
}
.site-name {
  flex: 1;
}
.site-ops {
  display: flex;
  gap: 8px;
}
.link:disabled {
  color: var(--muted);
  cursor: not-allowed;
}
.link.danger {
  color: #b42318;
}
.panel-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.version-block {
  border-left: 3px solid var(--border);
  padding: 2px 0 2px 10px;
  margin-bottom: 12px;
}
.version-block h4 {
  margin: 0 0 4px;
  font-size: 13px;
}
.version-line {
  margin: 0;
  font-size: 13px;
}
.muted,
.hint-text {
  color: var(--muted);
  font-size: 12px;
}
.status-chip {
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 10px;
  background: #eef4ff;
  color: var(--brand);
  font-size: 12px;
}
.draft-tag {
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 10px;
  background: #fff7e6;
  color: #b54708;
  font-size: 12px;
}
.notice-bar {
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
  margin-bottom: 12px;
}
.notice-info {
  background: #eef4ff;
  color: #1d4ed8;
}
.notice-warn {
  background: #fff7e6;
  color: #b54708;
}
.ok-text {
  color: #067647;
}
</style>

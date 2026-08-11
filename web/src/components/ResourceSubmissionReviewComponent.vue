<template>
  <section class="submission-review">
    <header class="review-header">
      <div>
        <div class="section-title">资源投稿审核</div>
        <p>审核本部门用户从 openZetcX 提交的 Agent、Skill 和 MCP。批准后资源将公开给全公司使用。</p>
      </div>
      <div class="header-actions">
        <a-select v-model:value="resourceType" style="width: 132px">
          <a-select-option value="all">全部类型 {{ items.length }}</a-select-option>
          <a-select-option value="agent">Agent {{ typeCounts.agent }}</a-select-option>
          <a-select-option value="skill">Skill {{ typeCounts.skill }}</a-select-option>
          <a-select-option value="mcp">MCP {{ typeCounts.mcp }}</a-select-option>
        </a-select>
        <a-select v-model:value="status" style="width: 120px" @change="loadItems">
          <a-select-option value="pending">待审核</a-select-option>
          <a-select-option value="approved">已通过</a-select-option>
          <a-select-option value="rejected">已驳回</a-select-option>
        </a-select>
        <a-button :loading="loading" @click="loadItems">刷新</a-button>
      </div>
    </header>

    <a-alert
      type="warning"
      show-icon
      message="安全提示"
      description="MCP 的环境变量和请求头密钥不会随投稿上传。批准公开后，使用者仍需自行配置凭据。"
    />

    <div v-if="loading" class="review-empty"><a-spin /> 正在加载审核队列…</div>
    <a-empty v-else-if="!filteredItems.length" :description="emptyDescription" />
    <div v-else class="submission-list">
      <article v-for="item in filteredItems" :key="item.submission_id" class="submission-card">
        <div class="card-topline">
          <div class="resource-heading">
            <span class="resource-type" :data-type="item.resource_type">{{ typeLabel(item.resource_type) }}</span>
            <strong>{{ item.name }}</strong>
            <code>{{ item.slug }}</code>
          </div>
          <a-tag :color="statusColor(item.status)">{{ statusLabel(item.status) }}</a-tag>
        </div>
        <p class="description">{{ item.description || '暂无描述' }}</p>
        <dl class="metadata">
          <div><dt>投稿人</dt><dd>{{ item.submitted_by_uid }}</dd></div>
          <div><dt>部门 ID</dt><dd>{{ item.department_id }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ item.created_at || '-' }}</dd></div>
          <div v-if="item.package_filename"><dt>资源包</dt><dd>{{ item.package_filename }}</dd></div>
        </dl>
        <details>
          <summary>查看投稿清单</summary>
          <pre>{{ JSON.stringify(item.manifest, null, 2) }}</pre>
        </details>
        <p v-if="item.review_comment" class="review-comment">审核意见：{{ item.review_comment }}</p>
        <div v-if="item.status === 'pending'" class="review-actions">
          <a-input v-model:value="comments[item.submission_id]" placeholder="审核意见（驳回时必填）" />
          <a-button
            danger
            :loading="busy === `reject:${item.submission_id}`"
            @click="rejectItem(item)"
          >驳回</a-button>
          <a-button
            type="primary"
            :loading="busy === `approve:${item.submission_id}`"
            @click="approveItem(item)"
          >批准并公开</a-button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { resourceSubmissionApi } from '@/apis/resource_submission_api'

const items = ref([])
const loading = ref(false)
const busy = ref('')
const status = ref('pending')
const resourceType = ref('all')
const comments = reactive({})

const typeCounts = computed(() => {
  const counts = { agent: 0, skill: 0, mcp: 0 }
  for (const item of items.value) {
    if (Object.hasOwn(counts, item.resource_type)) counts[item.resource_type] += 1
  }
  return counts
})
const filteredItems = computed(() => (
  resourceType.value === 'all'
    ? items.value
    : items.value.filter(item => item.resource_type === resourceType.value)
))
const emptyDescription = computed(() => (
  resourceType.value === 'all'
    ? '当前没有符合条件的投稿'
    : `当前没有待处理的 ${typeLabel(resourceType.value)} 投稿`
))

const typeLabel = (type) => ({ agent: 'Agent', skill: 'Skill', mcp: 'MCP' }[type] || type)
const statusLabel = (value) => ({ pending: '待审核', reviewing: '发布中', approved: '已通过', rejected: '已驳回' }[value] || value)
const statusColor = (value) => ({ pending: 'orange', reviewing: 'blue', approved: 'green', rejected: 'red' }[value] || 'default')

async function loadItems() {
  loading.value = true
  try {
    const response = await resourceSubmissionApi.getReviewQueue(status.value)
    items.value = Array.isArray(response?.data) ? response.data : []
  } catch (error) {
    message.error(error.message || '审核队列加载失败')
  } finally {
    loading.value = false
  }
}

function approveItem(item) {
  Modal.confirm({
    title: `批准公开“${item.name}”？`,
    content: '批准后该资源会立即进入全公司公共资源市场。',
    okText: '批准并公开',
    cancelText: '取消',
    async onOk() {
      busy.value = `approve:${item.submission_id}`
      try {
        await resourceSubmissionApi.approve(item.submission_id, comments[item.submission_id] || '')
        message.success('资源已批准并公开')
        await loadItems()
      } catch (error) {
        message.error(error.message || '资源批准失败')
      } finally {
        busy.value = ''
      }
    }
  })
}

async function rejectItem(item) {
  const comment = String(comments[item.submission_id] || '').trim()
  if (!comment) {
    message.warning('驳回时请填写审核意见')
    return
  }
  busy.value = `reject:${item.submission_id}`
  try {
    await resourceSubmissionApi.reject(item.submission_id, comment)
    message.success('投稿已驳回')
    await loadItems()
  } catch (error) {
    message.error(error.message || '投稿驳回失败')
  } finally {
    busy.value = ''
  }
}

onMounted(loadItems)
</script>

<style scoped>
.submission-review { display: flex; flex-direction: column; gap: 16px; }
.review-header { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }
.section-title { font-size: 22px; font-weight: 700; color: var(--gray-900); }
.review-header p { margin: 6px 0 0; color: var(--gray-500); line-height: 1.6; }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; }
.review-empty { padding: 56px; text-align: center; color: var(--gray-500); }
.submission-list { display: flex; flex-direction: column; gap: 12px; }
.submission-card { border: 1px solid var(--gray-200); border-radius: 12px; padding: 16px; background: var(--gray-0, #fff); }
.card-topline, .resource-heading, .review-actions { display: flex; align-items: center; gap: 10px; }
.card-topline { justify-content: space-between; }
.resource-type { padding: 3px 8px; border-radius: 6px; background: #e8f7fa; color: #087c92; font-size: 12px; font-weight: 700; }
.resource-type[data-type='skill'] { background: #f0edff; color: #6154c8; }
.resource-type[data-type='mcp'] { background: #fff3dd; color: #9a6200; }
.resource-heading code { color: var(--gray-500); }
.description { color: var(--gray-600); margin: 10px 0; }
.metadata { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 18px; margin: 0 0 10px; }
.metadata div { display: flex; gap: 8px; }
.metadata dt { color: var(--gray-500); }
.metadata dd { margin: 0; color: var(--gray-800); }
details summary { cursor: pointer; color: #1689a3; }
pre { max-height: 220px; overflow: auto; background: var(--gray-50); padding: 12px; border-radius: 8px; white-space: pre-wrap; }
.review-comment { border-left: 3px solid var(--gray-300); padding-left: 10px; color: var(--gray-600); }
.review-actions { margin-top: 14px; }
.review-actions :deep(.ant-input) { flex: 1; }
@media (max-width: 720px) {
  .review-header, .review-actions { flex-direction: column; align-items: stretch; }
  .metadata { grid-template-columns: 1fr; }
}
</style>

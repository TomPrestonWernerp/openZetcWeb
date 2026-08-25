<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '@/components/shared/PageHeader.vue'
import ModelProviderManagePanel from '@/components/model-management/ModelProviderManagePanel.vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeTab = ref('providers')
const providerPanelRef = ref(null)

const modelManageTabs = [{ key: 'providers', label: '模型供应商' }]
const activeLoading = computed(() => providerPanelRef.value?.loading || false)
const activeStats = computed(() => providerPanelRef.value?.stats || {})

watch(
  () => route.query.tab,
  (tab) => {
    if (tab === 'providers') return
    router.replace({ query: { ...route.query, tab: 'providers' } })
  },
  { immediate: true }
)
</script>

<template>
  <div class="model-manage-view">
    <PageHeader
      v-model:active-key="activeTab"
      title="智能体管理"
      :tabs="modelManageTabs"
      :loading="activeLoading"
      :show-border="true"
      aria-label="智能体管理视图切换"
    >
      <template #info>
        <div class="summary-strip">
          <span>{{ activeStats.total || 0 }} 个供应商</span>
          <span>{{ activeStats.enabled || 0 }} 个启用</span>
          <span v-if="activeStats.warning > 0" class="warning-count">
            {{ activeStats.warning }} 个凭证缺失
          </span>
          <span>{{ activeStats.models || 0 }} 个模型</span>
        </div>
      </template>
    </PageHeader>

    <div class="model-manage-content">
      <div v-if="userStore.isAdmin" class="tab-panel">
        <ModelProviderManagePanel ref="providerPanelRef" />
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.model-manage-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--gray-0);
  color: var(--gray-1000);
}

.model-manage-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;

  .tab-panel {
    height: 100%;
    min-height: 0;
    overflow-y: auto;
  }
}

.summary-strip {
  display: flex;
  gap: 8px;

  span {
    padding: 6px 10px;
    border: 1px solid var(--gray-100);
    border-radius: 7px;
    background: var(--gray-10);
    color: var(--gray-700);
    font-size: 12px;
    line-height: 18px;
  }

  .warning-count {
    background: var(--color-warning-50);
    border-color: var(--color-warning-100);
    color: var(--color-warning-700);
  }
}
</style>

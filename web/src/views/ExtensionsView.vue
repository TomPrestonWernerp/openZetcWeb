<template>
  <div class="extensions-view extension-page-root">
    <PageHeader
      v-if="!isDetailPage"
      title="知识库"
      :loading="activeChildLoading"
      :show-border="true"
      aria-label="知识库"
    />

    <div v-if="!isDetailPage" class="extensions-content">
      <div class="tab-panel">
        <DataBaseView ref="knowledgeRef" embedded />
      </div>
    </div>

    <router-view v-else />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/shared/PageHeader.vue'
import DataBaseView from '@/views/DataBaseView.vue'

const route = useRoute()
const knowledgeRef = ref(null)

const isDetailPage = computed(() => {
  return route.path.startsWith('/extensions/knowledgebase/')
})

const activeChildLoading = computed(() => knowledgeRef.value?.loading || false)
</script>

<style scoped lang="less">
@import '@/assets/css/extensions.less';

.extensions-view {
  .extensions-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;

    .tab-panel {
      height: 100%;
      min-height: 0;
      overflow-y: auto;
    }
  }
}
</style>

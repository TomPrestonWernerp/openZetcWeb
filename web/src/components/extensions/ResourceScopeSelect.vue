<template>
  <a-select v-model:value="model" style="width: 120px" placeholder="全部范围" allow-clear>
    <a-select-option value="">全部范围</a-select-option>
    <a-select-option v-for="option in RESOURCE_SCOPE_OPTIONS" :key="option.value" :value="option.value">
      {{ option.label }}
    </a-select-option>
  </a-select>
</template>

<script setup>
import { RESOURCE_SCOPE_OPTIONS } from '@/utils/resourceScope'

const model = defineModel({ type: String, default: '' })
</script>

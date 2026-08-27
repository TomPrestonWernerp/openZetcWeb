<template>
  <div class="infrastructure-settings">
    <div class="section-heading">
      <div>
        <h3>存储与数据库</h3>
        <p>默认连接 Docker 中的本机服务，也可以切换到兼容协议的第三方托管服务。</p>
      </div>
    </div>

    <a-alert
      type="warning"
      show-icon
      message="切换连接不会自动迁移已有对象、向量和图谱数据；请先完成迁移或重建索引。"
      class="migration-alert"
    />

    <a-alert
      v-if="loadError"
      type="error"
      show-icon
      message="数据库配置读取失败"
      :description="loadError"
      class="migration-alert"
    >
      <template #action>
        <a-button size="small" @click="loadConfig()">重新加载</a-button>
      </template>
    </a-alert>

    <a-spin :spinning="loading">
      <div class="config-list">
        <section v-for="section in sections" :key="section.key" class="config-card">
          <div class="card-header">
            <div class="card-title">
              <component :is="section.icon" :size="20" />
              <div>
                <h4>{{ section.title }}</h4>
                <p>{{ section.description }}</p>
              </div>
            </div>
            <a-space>
              <a-tag v-if="selectedSource(section.key)?.is_active" color="processing">
                当前激活
              </a-tag>
              <a-tag v-if="status[section.key]" :color="status[section.key].color">
                {{ status[section.key].text }}
              </a-tag>
            </a-space>
          </div>

          <div class="source-manager">
            <div class="source-select">
              <label class="required-label">配置来源</label>
              <a-select
                v-model:value="selectedIds[section.key]"
                class="full-width"
                placeholder="选择已保存的配置来源"
                @change="loadSelectedSource(section.key)"
              >
                <a-select-option
                  v-for="source in sources[section.key]"
                  :key="source.id"
                  :value="source.id"
                >
                  {{ source.config_name }} · {{ providerLabel(section, source.provider) }}
                  {{ source.is_active ? '（当前激活）' : '' }}
                </a-select-option>
              </a-select>
            </div>
            <a-space class="source-buttons">
              <a-button @click="createSource(section.key)">新增来源</a-button>
              <a-button
                :disabled="!selectedIds[section.key] || selectedSource(section.key)?.is_active"
                :loading="activating[section.key]"
                @click="activateSource(section.key)"
              >
                激活当前
              </a-button>
              <a-button
                danger
                :disabled="!selectedIds[section.key] || selectedSource(section.key)?.is_active"
                :loading="deleting[section.key]"
                @click="confirmDeleteSource(section.key)"
              >
                删除
              </a-button>
            </a-space>
          </div>

          <a-alert
            v-if="selectedSource(section.key)?.requires_secret_reentry"
            type="error"
            show-icon
            message="该配置来源的敏感字段无法解密"
            :description="secretRecoveryMessage(section.key)"
            class="source-recovery-alert"
          />

          <div class="form-grid">
            <div class="form-item wide-field">
              <label class="required-label">配置名称</label>
              <a-input
                v-model:value="configNames[section.key]"
                maxlength="100"
                placeholder="例如：本机默认、生产环境阿里云、灾备 Milvus"
              />
            </div>

            <div class="form-item provider-field">
              <label class="required-label">服务供应商</label>
              <a-select
                v-model:value="forms[section.key].provider"
                class="full-width"
                @change="applyProviderPreset(section.key, $event)"
              >
                <a-select-option
                  v-for="provider in section.providers"
                  :key="provider.value"
                  :value="provider.value"
                >
                  {{ provider.label }}
                </a-select-option>
              </a-select>
            </div>

            <div
              v-for="field in section.fields"
              :key="field.key"
              class="form-item"
              :class="{ 'wide-field': field.wide, 'switch-field': field.type === 'switch' }"
            >
              <label :class="{ 'required-label': isFieldRequired(section.key, field) }">
                {{ fieldLabel(section.key, field) }}
              </label>
              <a-switch
                v-if="field.type === 'switch'"
                v-model:checked="forms[section.key][field.key]"
              />
              <a-input
                v-else-if="field.type === 'password'"
                v-model:value="forms[section.key][field.key]"
                :type="secretInputType(section.key, field.key)"
                :placeholder="passwordPlaceholder(section.key, field)"
                autocomplete="new-password"
                @update:value="handlePasswordInput(section.key, field.key)"
              >
                <template #suffix>
                  <EyeOff
                    v-if="visibleSecrets[section.key][field.key]"
                    :size="17"
                    class="secret-eye"
                    @click.prevent.stop="toggleSecretVisibility(section.key, field.key)"
                  />
                  <Eye
                    v-else
                    :size="17"
                    class="secret-eye"
                    @click.prevent.stop="toggleSecretVisibility(section.key, field.key)"
                  />
                </template>
              </a-input>
              <a-input
                v-else
                v-model:value="forms[section.key][field.key]"
                :placeholder="field.placeholder"
              />
              <span v-if="field.help" class="field-help">{{ field.help }}</span>
            </div>
          </div>

          <div class="card-actions">
            <span class="save-hint">保存不会自动激活；测试连接只验证当前表单</span>
            <a-button
              class="lucide-icon-btn"
              :loading="testing[section.key]"
              @click="testConnection(section.key)"
            >
              <template #icon><PlugZap :size="16" /></template>
              测试连接
            </a-button>
            <a-button
              type="primary"
              class="lucide-icon-btn"
              :loading="saving[section.key]"
              @click="saveSection(section.key)"
            >
              <template #icon><Save :size="16" /></template>
              保存配置
            </a-button>
          </div>
        </section>
      </div>
    </a-spin>
  </div>
</template>

<script setup>
import { markRaw, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { Database, Eye, EyeOff, HardDrive, Network, PlugZap, Save } from 'lucide-vue-next'
import { infrastructureConfigApi } from '@/apis/system_api'

const loading = ref(false)
const loadError = ref('')
const MASKED_SECRET = '********'
const SYSTEM_DEFAULT_SECRET = '__OPENZETC_SYSTEM_DEFAULT_SECRET__'
const saving = reactive({})
const testing = reactive({})
const activating = reactive({})
const deleting = reactive({})
const status = reactive({})
const sources = reactive({
  object_storage: [],
  vector_database: [],
  graph_database: []
})
const selectedIds = reactive({
  object_storage: null,
  vector_database: null,
  graph_database: null
})
const configNames = reactive({
  object_storage: '',
  vector_database: '',
  graph_database: ''
})
const forms = reactive({
  object_storage: {},
  vector_database: {},
  graph_database: {}
})
const configuredSecrets = reactive({
  object_storage: {},
  vector_database: {},
  graph_database: {}
})
const revealedSecrets = reactive({
  object_storage: {},
  vector_database: {},
  graph_database: {}
})
const systemDefaultSecrets = reactive({
  object_storage: {},
  vector_database: {},
  graph_database: {}
})
const visibleSecrets = reactive({
  object_storage: {},
  vector_database: {},
  graph_database: {}
})
const localDefaults = reactive({ object_storage: {} })

const providerPresets = {
  object_storage: {
    minio: {
      endpoint: 'http://minio:9000',
      access_key: '',
      secret_key: '',
      region: '',
      secure: false,
      public_url: '/minio',
      console_url: 'http://localhost:9001'
    },
    aws_s3: { endpoint: 'https://s3.amazonaws.com', secure: true, public_url: '', console_url: '' },
    aliyun_oss: { endpoint: '', secure: true, public_url: '', console_url: '' },
    tencent_cos: { endpoint: '', secure: true, public_url: '', console_url: '' },
    qiniu_kodo: { endpoint: '', secure: true, public_url: '', console_url: '' },
    s3_compatible: { endpoint: '', secure: true, public_url: '', console_url: '' }
  },
  vector_database: {
    milvus: {
      uri: 'http://milvus:19530',
      name: 'openzetc',
      console_url: 'http://localhost:9091/webui/'
    },
    zilliz: { uri: '', name: 'default', console_url: '' },
    aliyun_milvus: { uri: '', name: 'default', console_url: '' },
    milvus_compatible: { uri: '', name: 'default', console_url: '' }
  },
  graph_database: {
    neo4j: {
      uri: 'bolt://graph:7687',
      username: 'neo4j',
      name: 'neo4j',
      console_url: 'http://localhost:7474/'
    },
    neo4j_aura: { uri: '', username: 'neo4j', name: 'neo4j', console_url: '' },
    neo4j_compatible: { uri: '', username: 'neo4j', name: 'neo4j', console_url: '' }
  }
}

const sections = [
  {
    key: 'object_storage',
    title: '对象存储',
    description: '知识库原文件、解析结果、图片和附件。第三方服务需提供 S3 兼容接口。',
    icon: markRaw(HardDrive),
    providers: [
      { value: 'minio', label: '本机 MinIO' },
      { value: 'aws_s3', label: 'Amazon S3' },
      { value: 'aliyun_oss', label: '阿里云 OSS（S3 兼容）' },
      { value: 'tencent_cos', label: '腾讯云 COS（S3 兼容）' },
      { value: 'qiniu_kodo', label: '七牛云 Kodo（S3 兼容）' },
      { value: 's3_compatible', label: '其他 S3 兼容服务' }
    ],
    fields: [
      {
        key: 'endpoint',
        label: '服务地址',
        wide: true,
        required: true,
        placeholder: 'https://s3.example.com'
      },
      { key: 'region', label: '区域 Region', placeholder: '例如 cn-hangzhou' },
      {
        key: 'access_key',
        label: 'Access Key',
        required: true,
        placeholder: '请输入 Access Key'
      },
      {
        key: 'secret_key',
        label: 'Secret Key',
        type: 'password',
        required: true,
        placeholder: '留用掩码表示不修改',
        help: '本机 MinIO 自动使用 Docker 环境变量中的账号密钥。'
      },
      {
        key: 'documents_bucket',
        label: '知识文件 Bucket',
        required: true,
        placeholder: 'knowledgebases'
      },
      { key: 'public_bucket', label: '公开图片 Bucket', required: true, placeholder: 'public' },
      {
        key: 'public_url',
        label: '公开访问地址/CDN',
        wide: true,
        placeholder: 'https://cdn.example.com'
      },
      { key: 'console_url', label: '管理控制台地址', wide: true, placeholder: '可选' },
      { key: 'secure', label: '使用 HTTPS', type: 'switch' }
    ]
  },
  {
    key: 'vector_database',
    title: '向量数据库',
    description: '知识库 Chunk、实体和关系向量；支持 Milvus 协议及托管服务。',
    icon: markRaw(Database),
    providers: [
      { value: 'milvus', label: '本机/自建 Milvus' },
      { value: 'zilliz', label: 'Zilliz Cloud' },
      { value: 'aliyun_milvus', label: '阿里云 Milvus 兼容服务' },
      { value: 'milvus_compatible', label: '其他 Milvus 兼容服务' }
    ],
    fields: [
      {
        key: 'uri',
        label: '连接地址',
        wide: true,
        required: true,
        placeholder: 'https://your-cluster.example.com'
      },
      {
        key: 'token',
        label: 'Token',
        type: 'password',
        wide: true,
        requiredProviders: ['zilliz', 'aliyun_milvus'],
        placeholder: '本机服务可留空'
      },
      { key: 'name', label: '数据库名称', required: true, placeholder: 'openzetc' },
      { key: 'console_url', label: '管理控制台地址', wide: true, placeholder: '可选' }
    ]
  },
  {
    key: 'graph_database',
    title: '图数据库',
    description: '知识图谱结构和 Cypher 查询；支持 Neo4j Bolt 协议及 Aura。',
    icon: markRaw(Network),
    providers: [
      { value: 'neo4j', label: '本机/自建 Neo4j' },
      { value: 'neo4j_aura', label: 'Neo4j Aura' },
      { value: 'neo4j_compatible', label: '其他 Neo4j 兼容服务' }
    ],
    fields: [
      {
        key: 'uri',
        label: '连接地址',
        wide: true,
        required: true,
        placeholder: 'neo4j+s://your-instance.databases.neo4j.io'
      },
      { key: 'username', label: '用户名', required: true, placeholder: 'neo4j' },
      {
        key: 'password',
        label: '密码',
        type: 'password',
        required: true,
        placeholder: '留用掩码表示不修改'
      },
      { key: 'name', label: '数据库名称', required: true, placeholder: 'neo4j' },
      { key: 'console_url', label: '管理控制台地址', wide: true, placeholder: '可选' }
    ]
  }
]

function selectedSource(sectionKey) {
  return sources[sectionKey].find((source) => source.id === selectedIds[sectionKey]) || null
}

function providerLabel(section, providerValue) {
  return section.providers.find((provider) => provider.value === providerValue)?.label || providerValue
}

function loadSelectedSource(sectionKey) {
  const source = selectedSource(sectionKey)
  if (!source) return
  configNames[sectionKey] = source.config_name
  applyLoadedSection(sectionKey, source.values)
  if (source.requires_secret_reentry) {
    status[sectionKey] = { color: 'error', text: '需要重新填写密钥' }
  } else {
    delete status[sectionKey]
  }
}

function secretRecoveryMessage(sectionKey) {
  const source = selectedSource(sectionKey)
  const labels = (source?.unreadable_secret_fields || []).map((fieldKey) => {
    const field = sections
      .find((section) => section.key === sectionKey)
      ?.fields.find((item) => item.key === fieldKey)
    return fieldLabel(sectionKey, field || { key: fieldKey, label: fieldKey })
  })
  return `数据库已加载，但 ${labels.join('、') || '敏感字段'} 由其他部署密钥加密。请重新填写后保存；修复前不能激活该来源。`
}

function createSource(sectionKey) {
  const section = sections.find((item) => item.key === sectionKey)
  const provider = section.providers[0].value
  selectedIds[sectionKey] = null
  configNames[sectionKey] = ''
  applyLoadedSection(sectionKey, { provider })
  applyProviderPreset(sectionKey, provider)
  status[sectionKey] = { color: 'default', text: '新建来源' }
}

function applyProviderPreset(section, provider) {
  for (const field of passwordFields(section)) {
    forms[section][field.key] = ''
    configuredSecrets[section][field.key] = false
    revealedSecrets[section][field.key] = false
    systemDefaultSecrets[section][field.key] = false
    visibleSecrets[section][field.key] = false
  }
  const preset = providerPresets[section]?.[provider]
  if (preset) Object.assign(forms[section], preset)
  if (section === 'object_storage' && provider === 'minio') {
    Object.assign(forms[section], localDefaults.object_storage)
    if (forms[section].secret_key === MASKED_SECRET) {
      configuredSecrets[section].secret_key = true
      systemDefaultSecrets[section].secret_key = true
    }
  }
  delete status[section]
}

function passwordFields(sectionKey) {
  return (
    sections
      .find((section) => section.key === sectionKey)
      ?.fields.filter((field) => field.type === 'password') || []
  )
}

function applyLoadedSection(sectionKey, values) {
  const normalized = { ...(values || {}) }
  for (const field of passwordFields(sectionKey)) {
    const isConfigured = normalized[field.key] === MASKED_SECRET
    configuredSecrets[sectionKey][field.key] = isConfigured
    revealedSecrets[sectionKey][field.key] = false
    systemDefaultSecrets[sectionKey][field.key] = false
    visibleSecrets[sectionKey][field.key] = false
  }
  Object.assign(forms[sectionKey], normalized)
}

function buildPayload(sectionKey) {
  const values = { ...forms[sectionKey] }
  for (const field of passwordFields(sectionKey)) {
    if (
      systemDefaultSecrets[sectionKey][field.key] &&
      values[field.key] === MASKED_SECRET
    ) {
      values[field.key] = SYSTEM_DEFAULT_SECRET
    } else if (!values[field.key] && configuredSecrets[sectionKey][field.key]) {
      values[field.key] = MASKED_SECRET
    }
  }
  return values
}

function passwordPlaceholder(sectionKey, field) {
  return configuredSecrets[sectionKey][field.key] ? '已配置，留空表示不修改' : field.placeholder
}

function secretInputType(sectionKey, fieldKey) {
  if (visibleSecrets[sectionKey][fieldKey]) return 'text'
  return configuredSecrets[sectionKey][fieldKey] && forms[sectionKey][fieldKey] === MASKED_SECRET
    ? 'text'
    : 'password'
}

function handlePasswordInput(sectionKey, fieldKey) {
  revealedSecrets[sectionKey][fieldKey] = false
  systemDefaultSecrets[sectionKey][fieldKey] = false
  configuredSecrets[sectionKey][fieldKey] = false
}

async function toggleSecretVisibility(sectionKey, fieldKey) {
  if (visibleSecrets[sectionKey][fieldKey]) {
    visibleSecrets[sectionKey][fieldKey] = false
    if (revealedSecrets[sectionKey][fieldKey]) {
      forms[sectionKey][fieldKey] = MASKED_SECRET
      revealedSecrets[sectionKey][fieldKey] = false
    }
    return
  }

  const currentValue = forms[sectionKey][fieldKey]
  if (
    !configuredSecrets[sectionKey][fieldKey] ||
    (currentValue && currentValue !== MASKED_SECRET)
  ) {
    visibleSecrets[sectionKey][fieldKey] = true
    return
  }

  try {
    const source = systemDefaultSecrets[sectionKey][fieldKey] ? 'local_default' : null
    const data = await infrastructureConfigApi.revealSecret(
      sectionKey,
      fieldKey,
      source,
      selectedIds[sectionKey]
    )
    revealedSecrets[sectionKey][fieldKey] = true
    forms[sectionKey][fieldKey] = data.value || ''
    visibleSecrets[sectionKey][fieldKey] = true
  } catch (error) {
    message.error(error.message || '密钥读取失败')
  }
}

function isFieldRequired(sectionKey, field) {
  return field.required || field.requiredProviders?.includes(forms[sectionKey].provider)
}

function fieldLabel(sectionKey, field) {
  if (sectionKey === 'object_storage' && forms[sectionKey].provider === 'minio') {
    if (field.key === 'access_key') return '账号（Access Key）'
    if (field.key === 'secret_key') return '密码（Secret Key）'
  }
  return field.label
}

async function loadConfig(preferredIds = {}) {
  loading.value = true
  loadError.value = ''
  try {
    const data = await infrastructureConfigApi.getConfig()
    Object.assign(localDefaults, data._local_defaults || {})
    for (const section of sections) {
      sources[section.key] = data._sources?.[section.key] || []
      const preferred = sources[section.key].find(
        (source) => source.id === preferredIds[section.key]
      )
      const active = sources[section.key].find((source) => source.is_active)
      const selected = preferred || active || sources[section.key][0]
      if (selected) {
        selectedIds[section.key] = selected.id
        loadSelectedSource(section.key)
      } else {
        createSource(section.key)
      }
    }
  } catch (error) {
    loadError.value = error.message || '基础设施配置加载失败'
    message.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function testConnection(section) {
  testing[section] = true
  delete status[section]
  try {
    await infrastructureConfigApi.testConnection(section, buildPayload(section))
    status[section] = { color: 'success', text: '测试通过（未保存）' }
    message.success('连接成功；当前修改尚未保存')
  } catch (error) {
    status[section] = { color: 'error', text: '连接失败' }
    message.error(error.message || '连接失败')
  } finally {
    testing[section] = false
  }
}

async function saveSection(section) {
  if (!configNames[section]?.trim()) {
    message.error('请输入配置名称')
    return
  }
  saving[section] = true
  try {
    const saved = await infrastructureConfigApi.saveSource(
      section,
      configNames[section],
      buildPayload(section),
      selectedIds[section]
    )
    await loadConfig({ [section]: saved.id })
    status[section] = {
      color: saved.is_active ? 'processing' : 'success',
      text: saved.is_active ? '已保存并继续启用' : '已保存（未激活）'
    }
    message.success(saved.is_active ? '当前激活配置已更新' : '配置来源已保存，可测试后再激活')
  } catch (error) {
    message.error(error.message || '配置保存失败')
  } finally {
    saving[section] = false
  }
}

async function activateSource(section) {
  const sourceId = selectedIds[section]
  if (!sourceId) return
  activating[section] = true
  try {
    await infrastructureConfigApi.activateSource(section, sourceId)
    await loadConfig({ [section]: sourceId })
    status[section] = { color: 'processing', text: '已激活' }
    message.success('已切换当前激活来源；已有数据不会自动迁移')
  } catch (error) {
    message.error(error.message || '配置激活失败')
  } finally {
    activating[section] = false
  }
}

function confirmDeleteSource(section) {
  const source = selectedSource(section)
  if (!source || source.is_active) return
  Modal.confirm({
    title: `删除配置来源“${source.config_name}”？`,
    content: '删除后无法恢复，但不会删除远端存储或数据库中的业务数据。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      deleting[section] = true
      try {
        await infrastructureConfigApi.deleteSource(section, source.id)
        await loadConfig()
        message.success('配置来源已删除')
      } catch (error) {
        message.error(error.message || '配置删除失败')
        throw error
      } finally {
        deleting[section] = false
      }
    }
  })
}

onMounted(loadConfig)
</script>

<style lang="less" scoped>
.infrastructure-settings {
  margin-top: 24px;

  .section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 12px;

    h3 {
      margin: 0 0 4px;
      color: var(--color-text);
      font-size: 18px;
      font-weight: 600;
    }

    p {
      margin: 0;
      color: var(--color-text-secondary);
      font-size: 13px;
    }
  }

  .migration-alert {
    margin-bottom: 12px;
  }

  .source-recovery-alert {
    margin-bottom: 14px;
  }

  .secret-eye {
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .config-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .config-card {
    padding: 16px;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);
  }

  .source-manager {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    margin-bottom: 16px;
    padding: 12px;
    border: 1px solid var(--gray-100);
    border-radius: 8px;
    background: var(--gray-25);
  }

  .source-select {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 6px;
    min-width: 0;

    label {
      color: var(--color-text-secondary);
      font-size: 13px;
      font-weight: 500;
    }

    .required-label::before {
      margin-right: 4px;
      color: #ff4d4f;
      content: '*';
    }
  }

  .source-buttons {
    flex: 0 0 auto;
  }

  .card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
  }

  .card-title {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    color: var(--main-color);

    h4 {
      margin: 0 0 3px;
      color: var(--color-text);
      font-size: 15px;
      font-weight: 600;
    }

    p {
      margin: 0;
      color: var(--color-text-secondary);
      font-size: 12px;
      line-height: 1.5;
    }
  }

  .form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 16px;
  }

  .form-item {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;

    &.wide-field,
    &.provider-field {
      grid-column: span 2;
    }

    &.switch-field {
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      min-height: 32px;

      :deep(.ant-switch) {
        flex: 0 0 auto;
        align-self: center;
        width: auto;
        min-width: 44px;
      }
    }

    label {
      color: var(--color-text-secondary);
      font-size: 13px;
      font-weight: 500;
    }

    .required-label::before {
      margin-right: 4px;
      color: #ff4d4f;
      content: '*';
    }

    .full-width {
      width: 100%;
    }
  }

  .field-help {
    color: var(--color-text-tertiary);
    font-size: 12px;
  }

  .card-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--gray-100);
  }

  .save-hint {
    align-self: center;
    margin-right: auto;
    color: var(--color-text-tertiary);
    font-size: 12px;
  }

  @media (max-width: 768px) {
    .source-manager {
      align-items: stretch;
      flex-direction: column;
    }

    .source-buttons {
      flex-wrap: wrap;
    }

    .form-grid {
      grid-template-columns: 1fr;
    }

    .form-item.wide-field,
    .form-item.provider-field {
      grid-column: span 1;
    }

    .card-actions {
      flex-wrap: wrap;
    }

    .save-hint {
      flex-basis: 100%;
    }
  }
}
</style>

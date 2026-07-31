<template>
  <section class="role-permission-settings">
    <header class="permission-header">
      <div>
        <h2>角色权限</h2>
        <p>配置知识库的创建、管理和共享范围。所有权限都会在服务端强制校验。</p>
      </div>
      <a-select
        v-if="userStore.isSuperAdmin"
        v-model:value="selectedDepartmentId"
        class="department-select"
        :options="departmentOptions"
        placeholder="选择部门"
        @change="loadPermissions"
      />
    </header>

    <a-alert
      v-if="!userStore.isSuperAdmin"
      type="info"
      show-icon
      message="部门管理员只能配置本部门普通用户的权限。管理员角色由超级管理员配置。"
    />

    <div v-if="loading" class="permission-loading">
      <a-spin tip="正在加载角色权限..." />
    </div>

    <div v-else class="role-policy-list">
      <article v-for="role in visibleRoles" :key="role" class="role-policy-card">
        <div class="role-policy-title">
          <div>
            <h3>{{ roleLabels[role] }}</h3>
            <p>{{ roleDescriptions[role] }}</p>
          </div>
          <a-tag :color="role === 'admin' ? 'blue' : 'default'">
            {{ departmentName || '当前部门' }}
          </a-tag>
        </div>

        <div class="permission-grid">
          <div v-for="item in permissionItems" :key="item.key" class="permission-item">
            <div>
              <strong>{{ item.label }}</strong>
              <p>{{ item.description }}</p>
            </div>
            <a-switch v-model:checked="policies[role][item.key]" />
          </div>
        </div>

        <div class="role-policy-actions">
          <a-button type="primary" :loading="savingRole === role" @click="saveRole(role)">
            保存{{ roleLabels[role] }}权限
          </a-button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { departmentApi } from '@/apis/department_api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const savingRole = ref('')
const departments = ref([])
const selectedDepartmentId = ref(null)
const departmentName = ref('')
const editableRoles = ref([])

const createEmptyPolicy = () => ({
  create: false,
  manage_own: false,
  manage_department: false,
  manage_all: false,
  share_users: false,
  share_department: false,
  share_global: false
})

const policies = reactive({
  admin: createEmptyPolicy(),
  user: createEmptyPolicy()
})

const roleLabels = {
  admin: '部门管理员',
  user: '普通用户'
}

const roleDescriptions = {
  admin: '负责本部门知识资源治理，可按需开放跨资源管理和共享能力。',
  user: '默认可创建并管理个人知识库，只读使用公司和部门共享知识库。'
}

const permissionItems = [
  { key: 'create', label: '创建知识库', description: '允许新建自己的知识库。' },
  {
    key: 'manage_own',
    label: '管理个人知识库',
    description: '编辑、上传、入库和删除本人创建的知识库。'
  },
  {
    key: 'manage_department',
    label: '管理部门共享库',
    description: '管理明确共享给本部门的知识库。'
  },
  {
    key: 'manage_all',
    label: '管理全部知识库',
    description: '可管理所有可见知识库，属于高权限能力。'
  },
  { key: 'share_users', label: '共享给指定用户', description: '个人库可授权给其他指定用户。' },
  {
    key: 'share_department',
    label: '共享给本部门',
    description: '个人库可发布为本部门共享知识库。'
  },
  {
    key: 'share_global',
    label: '全局共享',
    description: '个人库可发布为全公司可见，属于高权限能力。'
  }
]

const departmentOptions = computed(() =>
  departments.value.map((item) => ({ label: item.name, value: Number(item.id) }))
)

const visibleRoles = computed(() =>
  ['admin', 'user'].filter((role) => editableRoles.value.includes(role))
)

const loadPermissions = async () => {
  if (!selectedDepartmentId.value) return
  loading.value = true
  try {
    const data = await departmentApi.getRolePermissions(selectedDepartmentId.value)
    departmentName.value = data.department_name || ''
    editableRoles.value = data.editable_roles || []
    Object.assign(policies.admin, createEmptyPolicy(), data.permissions?.admin || {})
    Object.assign(policies.user, createEmptyPolicy(), data.permissions?.user || {})
  } catch (error) {
    message.error(error.message || '加载角色权限失败')
  } finally {
    loading.value = false
  }
}

const saveRole = async (role) => {
  savingRole.value = role
  try {
    const data = await departmentApi.updateRolePermissions(selectedDepartmentId.value, role, {
      ...policies[role]
    })
    Object.assign(policies[role], data.permissions?.[role] || {})
    message.success(`${roleLabels[role]}权限已保存`)
  } catch (error) {
    message.error(error.message || '保存角色权限失败')
  } finally {
    savingRole.value = ''
  }
}

onMounted(async () => {
  try {
    departments.value = await departmentApi.getDepartments()
    const ownDepartmentId = Number(userStore.departmentId || 0)
    const preferred = departments.value.find((item) => Number(item.id) === ownDepartmentId)
    selectedDepartmentId.value = Number(
      preferred?.id || departments.value[0]?.id || ownDepartmentId
    )
    await loadPermissions()
  } catch (error) {
    message.error(error.message || '加载部门失败')
  }
})
</script>

<style lang="less" scoped>
.role-permission-settings {
  padding: 24px;
}

.permission-header,
.role-policy-title,
.permission-item,
.role-policy-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.permission-header {
  margin-bottom: 16px;

  h2 {
    margin: 0 0 6px;
    font-size: 22px;
  }

  p {
    margin: 0;
    color: var(--gray-500);
  }
}

.department-select {
  width: 220px;
}

.permission-loading {
  display: grid;
  min-height: 260px;
  place-items: center;
}

.role-policy-list {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.role-policy-card {
  padding: 20px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  background: var(--gray-0);
}

.role-policy-title {
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gray-100);

  h3 {
    margin: 0 0 4px;
    font-size: 17px;
  }

  p {
    margin: 0;
    color: var(--gray-500);
  }
}

.permission-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 24px;
}

.permission-item {
  min-height: 82px;
  border-bottom: 1px solid var(--gray-100);

  strong {
    font-weight: 600;
  }

  p {
    margin: 4px 0 0;
    color: var(--gray-500);
    font-size: 12px;
  }
}

.role-policy-actions {
  justify-content: flex-end;
  padding-top: 18px;
}

@media (max-width: 760px) {
  .permission-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .department-select,
  .permission-grid {
    width: 100%;
  }

  .permission-grid {
    grid-template-columns: 1fr;
  }
}
</style>

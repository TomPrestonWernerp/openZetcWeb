<template>
  <section class="access-control">
    <header class="access-header">
      <div>
        <h2>权限管理</h2>
        <p>统一管理人员、角色、权限和业务资源范围。所有授权均由服务端强制校验。</p>
      </div>
      <a-button
        v-if="canCreateRole"
        type="primary"
        class="lucide-icon-btn"
        @click="openCreateRole"
      >
        <template #icon><Plus :size="15" /></template>
        新建角色
      </a-button>
    </header>

    <a-alert
      type="info"
      show-icon
      message="权限范围说明"
      description="本人：仅本人账号或本人创建的资源；本部门：覆盖本部门人员和资源；全公司：覆盖所有部门。多个角色的权限会自动合并。"
    />

    <a-tabs v-model:active-key="activeTab" class="access-tabs">
      <a-tab-pane key="roles" tab="角色权限">
        <div class="role-layout">
          <aside class="role-list">
            <a-spin :spinning="loading">
              <button
                v-for="role in roles"
                :key="role.id"
                class="role-list-item"
                :class="{ active: selectedRole?.id === role.id }"
                @click="selectRole(role)"
              >
                <span>
                  <strong>{{ role.name }}</strong>
                  <small>{{ role.department_id ? departmentName(role.department_id) : '公司级' }}</small>
                </span>
                <a-tag :color="role.is_system ? 'blue' : 'default'">
                  {{ role.is_system ? '系统' : '自定义' }}
                </a-tag>
              </button>
              <a-empty v-if="!loading && !roles.length" description="暂无可查看角色" />
            </a-spin>
          </aside>

          <main v-if="selectedRole" class="role-editor">
            <div class="role-editor-title">
              <div>
                <h3>{{ selectedRole.name }}</h3>
                <p>{{ selectedRole.description || '未填写角色说明' }}</p>
              </div>
              <div class="role-actions">
                <a-button
                  v-if="!selectedRole.is_system && canDeleteRole"
                  danger
                  @click="removeSelectedRole"
                >
                  删除
                </a-button>
                <a-button
                  v-if="!selectedRole.is_system && canUpdateRole"
                  type="primary"
                  :loading="saving"
                  @click="saveSelectedRole"
                >
                  保存角色
                </a-button>
              </div>
            </div>

            <a-form v-if="!selectedRole.is_system" layout="vertical" class="role-meta-form">
              <a-form-item label="角色名称">
                <a-input v-model:value="roleForm.name" :maxlength="100" />
              </a-form-item>
              <a-form-item label="角色说明">
                <a-input v-model:value="roleForm.description" :maxlength="255" />
              </a-form-item>
            </a-form>

            <div class="permission-domains">
              <article
                v-for="domain in groupedPermissions"
                :key="domain.code"
                class="permission-domain"
              >
                <header>
                  <div>
                    <h4>{{ domainLabels[domain.code] || domain.code }}</h4>
                    <span>{{ domain.items.length }} 项权限</span>
                  </div>
                  <a-button
                    v-if="canUpdateRole && !selectedRole.is_system"
                    type="link"
                    size="small"
                    @click="clearDomain(domain.code)"
                  >
                    清空本组
                  </a-button>
                </header>
                <div class="permission-list">
                  <div v-for="permission in domain.items" :key="permission.code" class="permission-row">
                    <div>
                      <strong>{{ permission.label }}</strong>
                      <p>{{ permission.description }}</p>
                    </div>
                    <a-select
                      v-model:value="roleForm.permissions[permission.code]"
                      class="scope-select"
                      :disabled="selectedRole.is_system || !canUpdateRole"
                      allow-clear
                      placeholder="不授权"
                    >
                      <a-select-option v-if="canGrantScope(permission.code, 'own')" value="own">
                        本人
                      </a-select-option>
                      <a-select-option
                        v-if="canGrantScope(permission.code, 'department')"
                        value="department"
                      >
                        本部门
                      </a-select-option>
                      <a-select-option
                        v-if="canGrantScope(permission.code, 'global')"
                        value="global"
                      >
                        全公司
                      </a-select-option>
                    </a-select>
                  </div>
                </div>
              </article>
            </div>
          </main>
          <a-empty v-else class="role-empty" description="请选择一个角色" />
        </div>
      </a-tab-pane>

      <a-tab-pane key="users" tab="用户授权">
        <div class="user-role-panel">
          <div class="user-role-toolbar">
            <a-select
              v-model:value="selectedUserId"
              show-search
              option-filter-prop="label"
              placeholder="选择用户"
              :options="userOptions"
              @change="loadUserRoles"
            />
            <a-button
              type="primary"
              :disabled="!selectedUserId || !canAssignRole"
              :loading="savingUserRoles"
              @click="saveUserRoles"
            >
              保存用户角色
            </a-button>
          </div>
          <div v-if="selectedUserId" class="assignable-role-grid">
            <label
              v-for="role in assignableRoles"
              :key="role.id"
              class="assignable-role"
              :class="{ checked: selectedUserRoleIds.includes(role.id) }"
            >
              <a-checkbox v-model:checked="roleSelection[role.id]" />
              <span>
                <strong>{{ role.name }}</strong>
                <small>{{ role.description || '无角色说明' }}</small>
              </span>
            </label>
          </div>
          <a-empty v-else description="选择用户后可分配一个或多个角色" />
        </div>
      </a-tab-pane>

      <a-tab-pane key="catalog" tab="权限目录">
        <div class="catalog-grid">
          <article v-for="domain in groupedPermissions" :key="domain.code" class="catalog-card">
            <h3>{{ domainLabels[domain.code] || domain.code }}</h3>
            <div v-for="permission in domain.items" :key="permission.code" class="catalog-item">
              <strong>{{ permission.label }}</strong>
              <code>{{ permission.code }}</code>
              <p>{{ permission.description }}</p>
            </div>
          </article>
        </div>
      </a-tab-pane>
    </a-tabs>

    <a-modal
      v-model:open="createModalOpen"
      title="新建自定义角色"
      :confirm-loading="saving"
      @ok="createRole"
    >
      <a-form layout="vertical">
        <a-form-item label="角色名称" required>
          <a-input v-model:value="createForm.name" :maxlength="100" placeholder="例如：知识平台主管" />
        </a-form-item>
        <a-form-item label="适用范围">
          <a-select
            v-model:value="createForm.department_id"
            :allow-clear="canCreateCompanyRole"
            :disabled="!canCreateCompanyRole"
            placeholder="公司级角色"
          >
            <a-select-option
              v-for="department in departments"
              :key="department.id"
              :value="Number(department.id)"
            >
              {{ department.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="角色说明">
          <a-textarea v-model:value="createForm.description" :rows="3" :maxlength="255" />
        </a-form-item>
      </a-form>
    </a-modal>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { Plus } from 'lucide-vue-next'
import { departmentApi, rbacApi } from '@/apis'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const activeTab = ref('roles')
const loading = ref(false)
const saving = ref(false)
const savingUserRoles = ref(false)
const roles = ref([])
const permissions = ref([])
const departments = ref([])
const users = ref([])
const selectedRole = ref(null)
const selectedUserId = ref(null)
const selectedUserRoleIds = ref([])
const roleSelection = reactive({})
const createModalOpen = ref(false)

const roleForm = reactive({ name: '', description: '', permissions: {} })
const createForm = reactive({ name: '', description: '', department_id: null })

const domainLabels = {
  user: '人员管理',
  department: '部门管理',
  role: '角色与权限',
  knowledge: '知识库',
  agent: '智能体',
  skill: 'Skill',
  mcp: 'MCP'
}

const groupedPermissions = computed(() => {
  const groups = new Map()
  permissions.value.forEach((item) => {
    if (!groups.has(item.domain)) groups.set(item.domain, [])
    groups.get(item.domain).push(item)
  })
  return [...groups.entries()].map(([code, items]) => ({ code, items }))
})

const canCreateRole = computed(() => userStore.hasPermission('role.create'))
const canCreateCompanyRole = computed(() => userStore.hasPermission('role.create', 'global'))
const canUpdateRole = computed(() => userStore.hasPermission('role.update'))
const canDeleteRole = computed(() => userStore.hasPermission('role.delete'))
const canAssignRole = computed(
  () => userStore.hasPermission('role.assign') && userStore.hasPermission('user.assign_role')
)
const assignableRoles = computed(() => {
  const user = users.value.find((item) => item.id === selectedUserId.value)
  return roles.value.filter(
    (role) =>
      role.code !== 'system.superadmin' &&
      (!role.department_id || Number(role.department_id) === Number(user?.department_id))
  )
})
const selectedUserRoleIdsComputed = computed(() =>
  Object.entries(roleSelection)
    .filter(([, checked]) => checked)
    .map(([id]) => Number(id))
)
const userOptions = computed(() =>
  users.value.map((user) => ({
    value: user.id,
    label: `${user.username}（${user.uid} · ${user.department_name || '未分配部门'}）`
  }))
)

const departmentName = (departmentId) =>
  departments.value.find((item) => Number(item.id) === Number(departmentId))?.name || '未知部门'

const scopeRank = { own: 1, department: 2, global: 3 }
const canGrantScope = (permissionCode, scope) =>
  (scopeRank[userStore.permissions?.[permissionCode]] || 0) >= scopeRank[scope]

const selectRole = (role) => {
  selectedRole.value = role
  roleForm.name = role.name
  roleForm.description = role.description || ''
  roleForm.permissions = { ...(role.permissions || {}) }
}

const clearDomain = (domainCode) => {
  permissions.value
    .filter((item) => item.domain === domainCode)
    .forEach((item) => delete roleForm.permissions[item.code])
}

const refreshAll = async () => {
  loading.value = true
  try {
    await userStore.loadAccess()
    const [permissionData, roleData, departmentData, userData] = await Promise.all([
      rbacApi.getPermissions(),
      rbacApi.getRoles(),
      departmentApi.getDepartments(),
      userStore.getUsers()
    ])
    permissions.value = permissionData
    roles.value = roleData
    departments.value = departmentData
    users.value = userData
    const preferred = roles.value.find((item) => item.id === selectedRole.value?.id) || roles.value[0]
    if (preferred) selectRole(preferred)
  } catch (error) {
    message.error(error.message || '加载权限数据失败')
  } finally {
    loading.value = false
  }
}

const openCreateRole = () => {
  Object.assign(createForm, {
    name: '',
    description: '',
    department_id: userStore.hasPermission('role.create', 'global')
      ? null
      : Number(userStore.departmentId)
  })
  createModalOpen.value = true
}

const createRole = async () => {
  if (!createForm.name.trim()) {
    message.warning('请输入角色名称')
    return
  }
  saving.value = true
  try {
    const role = await rbacApi.createRole({
      name: createForm.name.trim(),
      description: createForm.description || null,
      department_id: createForm.department_id,
      permissions: {}
    })
    createModalOpen.value = false
    roles.value.push(role)
    selectRole(role)
    message.success('角色已创建，请继续配置权限')
  } catch (error) {
    message.error(error.message || '创建角色失败')
  } finally {
    saving.value = false
  }
}

const saveSelectedRole = async () => {
  saving.value = true
  try {
    const updated = await rbacApi.updateRole(selectedRole.value.id, {
      name: roleForm.name.trim(),
      description: roleForm.description || null,
      permissions: Object.fromEntries(
        Object.entries(roleForm.permissions).filter(([, scope]) => Boolean(scope))
      )
    })
    const index = roles.value.findIndex((item) => item.id === updated.id)
    if (index >= 0) roles.value[index] = updated
    selectRole(updated)
    message.success('角色权限已保存')
  } catch (error) {
    message.error(error.message || '保存角色失败')
  } finally {
    saving.value = false
  }
}

const removeSelectedRole = () => {
  Modal.confirm({
    title: `删除角色“${selectedRole.value.name}”？`,
    content: '删除后该角色会从所有用户移除，此操作不可撤销。',
    okType: 'danger',
    async onOk() {
      await rbacApi.deleteRole(selectedRole.value.id)
      roles.value = roles.value.filter((item) => item.id !== selectedRole.value.id)
      selectedRole.value = null
      if (roles.value[0]) selectRole(roles.value[0])
      message.success('角色已删除')
    }
  })
}

const loadUserRoles = async () => {
  Object.keys(roleSelection).forEach((key) => delete roleSelection[key])
  if (!selectedUserId.value) return
  try {
    const assigned = await rbacApi.getUserRoles(selectedUserId.value)
    selectedUserRoleIds.value = assigned.map((item) => item.id)
    roles.value.forEach((role) => {
      roleSelection[role.id] = selectedUserRoleIds.value.includes(role.id)
    })
  } catch (error) {
    message.error(error.message || '加载用户角色失败')
  }
}

const saveUserRoles = async () => {
  const roleIds = selectedUserRoleIdsComputed.value
  if (!roleIds.length) {
    message.warning('至少保留一个角色')
    return
  }
  savingUserRoles.value = true
  try {
    await rbacApi.updateUserRoles(selectedUserId.value, roleIds)
    selectedUserRoleIds.value = roleIds
    message.success('用户角色已更新')
  } catch (error) {
    message.error(error.message || '保存用户角色失败')
  } finally {
    savingUserRoles.value = false
  }
}

onMounted(refreshAll)
</script>

<style lang="less" scoped>
.access-control {
  padding: 24px;
}

.access-header,
.role-editor-title,
.user-role-toolbar,
.permission-domain > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.access-header {
  margin-bottom: 16px;

  h2 {
    margin: 0 0 5px;
    font-size: 22px;
  }

  p {
    margin: 0;
    color: var(--gray-500);
  }
}

.access-tabs {
  margin-top: 14px;
}

.role-layout {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  min-height: 520px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  overflow: hidden;
}

.role-list {
  padding: 10px;
  border-right: 1px solid var(--gray-200);
  background: var(--gray-50);
}

.role-list-item {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 11px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;

  &:hover,
  &.active {
    background: var(--gray-0);
    box-shadow: 0 1px 4px rgb(0 0 0 / 5%);
  }

  &.active {
    color: var(--color-primary-500);
  }

  span:first-child {
    display: grid;
    min-width: 0;
  }

  strong,
  small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    margin-top: 3px;
    color: var(--gray-500);
  }
}

.role-editor {
  min-width: 0;
  padding: 20px;
}

.role-editor-title {
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gray-100);

  h3,
  p {
    margin: 0;
  }

  p {
    margin-top: 4px;
    color: var(--gray-500);
  }
}

.role-actions {
  display: flex;
  gap: 8px;
}

.role-meta-form {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 12px;
  margin-top: 16px;

  :deep(.ant-form-item) {
    margin-bottom: 0;
  }
}

.permission-domains {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.permission-domain {
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  overflow: hidden;

  > header {
    padding: 12px 14px;
    background: var(--gray-50);

    h4 {
      display: inline;
      margin: 0 8px 0 0;
      font-size: 15px;
    }

    span {
      color: var(--gray-500);
      font-size: 12px;
    }
  }
}

.permission-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.permission-row {
  display: flex;
  min-height: 78px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-top: 1px solid var(--gray-100);

  &:nth-child(odd) {
    border-right: 1px solid var(--gray-100);
  }

  strong {
    font-size: 13px;
  }

  p {
    margin: 3px 0 0;
    color: var(--gray-500);
    font-size: 11px;
  }
}

.scope-select {
  width: 106px;
  flex: 0 0 auto;
}

.role-empty {
  align-self: center;
}

.user-role-panel {
  min-height: 420px;
  padding: 20px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
}

.user-role-toolbar {
  margin-bottom: 18px;

  .ant-select {
    width: min(520px, 70%);
  }
}

.assignable-role-grid,
.catalog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.assignable-role {
  display: flex;
  min-height: 78px;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  cursor: pointer;

  &.checked {
    border-color: var(--color-primary-500);
    background: var(--color-primary-50);
  }

  span {
    display: grid;
  }

  small {
    margin-top: 4px;
    color: var(--gray-500);
  }
}

.catalog-card {
  padding: 16px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;

  h3 {
    margin: 0 0 10px;
  }
}

.catalog-item {
  padding: 10px 0;
  border-top: 1px solid var(--gray-100);

  code {
    margin-left: 8px;
    color: var(--color-primary-500);
    font-size: 11px;
  }

  p {
    margin: 4px 0 0;
    color: var(--gray-500);
    font-size: 12px;
  }
}

@media (max-width: 820px) {
  .role-layout {
    grid-template-columns: 1fr;
  }

  .role-list {
    border-right: 0;
    border-bottom: 1px solid var(--gray-200);
  }

  .role-meta-form,
  .permission-list,
  .assignable-role-grid,
  .catalog-grid {
    grid-template-columns: 1fr;
  }

  .permission-row:nth-child(odd) {
    border-right: 0;
  }
}
</style>

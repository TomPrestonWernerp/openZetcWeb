<template>
  <div class="department-management">
    <!-- 头部区域 -->
    <div class="header-section">
      <div class="header-content">
        <div class="section-title">部门管理</div>
        <p class="section-description">管理系统部门，部门下的用户会被隔离管理。</p>
      </div>
      <div class="header-actions">
        <a-button
          @click="handleRefresh"
          :loading="departmentManagement.refreshing"
          title="刷新"
          class="refresh-btn lucide-icon-btn"
        >
          <template #icon
            ><RefreshCw :size="16" :class="{ spin: departmentManagement.refreshing }"
          /></template>
        </a-button>
        <a-button
          v-if="userStore.hasPermission('department.create', 'global')"
          type="primary"
          @click="showAddDepartmentModal"
          class="add-btn lucide-icon-btn"
        >
          <template #icon><Plus :size="16" /></template>
          添加部门
        </a-button>
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="content-section">
      <a-spin :spinning="departmentManagement.loading">
        <div v-if="departmentManagement.error" class="error-message">
          <a-alert type="error" :message="departmentManagement.error" show-icon />
        </div>

        <template v-if="departmentManagement.departments.length > 0">
          <a-table
            :dataSource="departmentManagement.departments"
            :columns="columns"
            :rowKey="(record) => record.id"
            :pagination="false"
            class="department-table"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <button
                  v-if="canViewDepartmentMembers(record)"
                  class="department-link"
                  type="button"
                  @click="openMemberDrawer(record)"
                >
                  {{ record.name }}
                </button>
                <strong v-else>{{ record.name }}</strong>
              </template>
              <template v-if="column.key === 'description'">
                <span class="description-text">{{ record.description || '-' }}</span>
              </template>
              <template v-if="column.key === 'userCount'">
                <a-button
                  v-if="canViewDepartmentMembers(record)"
                  type="link"
                  class="member-count"
                  @click="openMemberDrawer(record)"
                >
                  {{ record.user_count ?? 0 }} 人
                </a-button>
                <span v-else>{{ record.user_count ?? 0 }} 人</span>
              </template>
              <template v-if="column.key === 'action'">
                <a-space>
                  <a-tooltip title="编辑部门">
                    <a-button
                      v-if="userStore.hasPermission('department.update')"
                      type="text"
                      size="small"
                      @click="showEditDepartmentModal(record)"
                      class="action-btn lucide-icon-btn"
                    >
                      <SquarePen :size="14" />
                    </a-button>
                  </a-tooltip>
                  <a-tooltip title="删除部门">
                    <a-button
                      v-if="userStore.hasPermission('department.delete', 'global')"
                      type="text"
                      size="small"
                      danger
                      @click="confirmDeleteDepartment(record)"
                      :disabled="record.id === 1"
                      class="action-btn lucide-icon-btn"
                    >
                      <Trash2 :size="14" />
                    </a-button>
                  </a-tooltip>
                </a-space>
              </template>
            </template>
          </a-table>
        </template>

        <div v-else class="empty-state">
          <a-empty description="暂无部门数据" />
        </div>
      </a-spin>
    </div>

    <!-- 部门表单模态框 -->
    <a-modal
      v-model:open="departmentManagement.modalVisible"
      :title="departmentManagement.modalTitle"
      @ok="handleDepartmentFormSubmit"
      :confirmLoading="departmentManagement.loading"
      @cancel="departmentManagement.modalVisible = false"
      :maskClosable="false"
      width="520px"
      class="department-modal"
    >
      <a-form layout="vertical" class="department-form">
        <a-form-item label="部门名称" required class="form-item">
          <a-input
            v-model:value="departmentManagement.form.name"
            placeholder="请输入部门名称"
            size="large"
            :maxlength="50"
          />
        </a-form-item>

        <a-form-item label="部门描述" class="form-item">
          <a-textarea
            v-model:value="departmentManagement.form.description"
            placeholder="请输入部门描述（可选）"
            :rows="3"
            :maxlength="255"
            show-count
          />
        </a-form-item>

        <a-divider v-if="!departmentManagement.editMode" />

        <template v-if="!departmentManagement.editMode">
          <p class="admin-section-hint">
            创建部门时必须同时创建管理员，该管理员将负责管理本部门用户
          </p>

          <a-form-item label="管理员UID" required class="form-item">
            <a-input
              v-model:value="departmentManagement.form.adminUid"
              placeholder="请输入管理员UID（3-20位字母/数字/下划线）"
              size="large"
              :maxlength="20"
              @blur="checkAdminUid"
            />
            <div v-if="departmentManagement.form.uidError" class="error-text">
              {{ departmentManagement.form.uidError }}
            </div>
            <div v-else class="help-text">此 UID 将用于登录</div>
          </a-form-item>

          <a-form-item label="密码" required class="form-item">
            <a-input-password
              v-model:value="departmentManagement.form.adminPassword"
              :placeholder="`请输入管理员密码（至少 ${MIN_PASSWORD_LENGTH} 位）`"
              size="large"
              :minlength="MIN_PASSWORD_LENGTH"
              :maxlength="50"
            />
          </a-form-item>

          <a-form-item label="确认密码" required class="form-item">
            <a-input-password
              v-model:value="departmentManagement.form.adminConfirmPassword"
              placeholder="请再次输入密码"
              size="large"
              :maxlength="50"
            />
          </a-form-item>

          <a-form-item label="手机号（可选）" class="form-item">
            <a-input
              v-model:value="departmentManagement.form.adminPhone"
              placeholder="请输入手机号（可用于登录）"
              size="large"
              :maxlength="11"
            />
            <div v-if="departmentManagement.form.phoneError" class="error-text">
              {{ departmentManagement.form.phoneError }}
            </div>
          </a-form-item>
        </template>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="memberDrawer.open"
      :title="`${memberDrawer.department?.name || ''} · 部门成员`"
      width="min(720px, 92vw)"
      :destroy-on-close="true"
      class="member-drawer"
    >
      <div class="member-summary">
        <div>
          <strong>{{ memberDrawer.members.length }} 位成员</strong>
          <span>选择成员后可统一调整所属部门</span>
        </div>
        <a-button size="small" :loading="memberDrawer.loading" @click="loadDepartmentMembers">
          刷新
        </a-button>
      </div>

      <a-alert
        v-if="memberDrawer.error"
        type="error"
        :message="memberDrawer.error"
        show-icon
        class="member-error"
      />

      <a-table
        :data-source="memberDrawer.members"
        :columns="memberColumns"
        :row-key="(record) => record.id"
        :row-selection="memberRowSelection"
        :loading="memberDrawer.loading"
        :pagination="{ pageSize: 8, hideOnSinglePage: true, showSizeChanger: false }"
        :scroll="{ x: 520 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'user'">
            <div class="member-identity">
              <strong>{{ record.username }}</strong>
              <span>{{ record.uid }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'role'">
            {{ record.role_name || record.role || '普通用户' }}
          </template>
        </template>
      </a-table>

      <template #footer>
        <div class="drawer-footer">
          <span>已选择 {{ memberDrawer.selectedIds.length }} 人</span>
          <div v-if="canMoveMembers" class="batch-move">
            <a-select
              v-model:value="memberDrawer.targetDepartmentId"
              placeholder="选择目标部门"
              :options="moveDepartmentOptions"
              :disabled="!memberDrawer.selectedIds.length"
            />
            <a-button
              type="primary"
              :disabled="!canSubmitMemberMove"
              :loading="memberDrawer.moving"
              @click="moveSelectedMembers"
            >
              批量移动
            </a-button>
          </div>
          <a-button
            v-if="canAssignMemberRoles"
            :disabled="!memberDrawer.selectedIds.length"
            @click="openMemberRoleModal"
          >
            批量设置角色
          </a-button>
        </div>
      </template>
    </a-drawer>

    <a-modal
      v-model:open="memberRoleModal.open"
      title="批量设置成员角色"
      :confirm-loading="memberRoleModal.saving"
      :ok-button-props="{ disabled: !memberRoleModal.roleIds.length || memberRoleModal.loading }"
      @ok="saveMemberRoles"
    >
      <a-alert
        type="info"
        show-icon
        :message="`将对已选择的 ${memberDrawer.selectedIds.length} 位成员生效`"
        class="member-role-hint"
      />
      <a-spin :spinning="memberRoleModal.loading">
        <a-form layout="vertical">
          <a-form-item label="处理方式">
            <a-radio-group v-model:value="memberRoleModal.mode" button-style="solid">
              <a-radio-button value="add">增加角色</a-radio-button>
              <a-radio-button value="remove">移除角色</a-radio-button>
              <a-radio-button value="replace">覆盖角色</a-radio-button>
            </a-radio-group>
          </a-form-item>
          <a-form-item label="选择角色" required>
            <a-select
              v-model:value="memberRoleModal.roleIds"
              mode="multiple"
              placeholder="选择一个或多个角色"
              :options="memberRoleOptions"
            />
          </a-form-item>
        </a-form>
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, reactive, onMounted, watch } from 'vue'
import { notification, message, Modal } from 'ant-design-vue'
import { apiGet, departmentApi, rbacApi } from '@/apis'
import { useUserStore } from '@/stores/user'
import { Plus, RefreshCw, SquarePen, Trash2 } from 'lucide-vue-next'
import { isPasswordLongEnough, MIN_PASSWORD_LENGTH } from '@/utils/passwordValidation'

const userStore = useUserStore()

const memberColumns = [
  { title: '用户', key: 'user', width: 210 },
  { title: '手机号', dataIndex: 'phone_number', key: 'phone', width: 150 },
  { title: '角色', key: 'role', width: 120 }
]

// 表格列定义
const columns = [
  {
    title: '部门名称',
    dataIndex: 'name',
    key: 'name',
    width: 200
  },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true
  },
  {
    title: '用户数量',
    dataIndex: 'user_count',
    key: 'userCount',
    width: 100,
    align: 'center'
  },
  {
    title: '操作',
    key: 'action',
    width: 120,
    align: 'center'
  }
]

// 部门管理状态
const departmentManagement = reactive({
  loading: false,
  refreshing: false,
  departments: [],
  error: null,
  modalVisible: false,
  modalTitle: '添加部门',
  editMode: false,
  editDepartmentId: null,
  form: {
    name: '',
    description: '',
    adminUid: '',
    adminPassword: '',
    adminConfirmPassword: '',
    adminPhone: '',
    uidError: '',
    phoneError: ''
  }
})

const memberDrawer = reactive({
  open: false,
  department: null,
  members: [],
  selectedIds: [],
  targetDepartmentId: null,
  loading: false,
  moving: false,
  error: null
})
const memberRoleModal = reactive({
  open: false,
  loading: false,
  saving: false,
  roles: [],
  roleIds: [],
  mode: 'add'
})

const canMoveMembers = computed(() => userStore.hasPermission('user.update', 'global'))
const canAssignMemberRoles = computed(
  () => userStore.hasPermission('role.assign') && userStore.hasPermission('user.assign_role')
)
const moveDepartmentOptions = computed(() =>
  departmentManagement.departments
    .filter((item) => Number(item.id) !== Number(memberDrawer.department?.id))
    .map((item) => ({ value: Number(item.id), label: item.name }))
)
const canSubmitMemberMove = computed(
  () => memberDrawer.selectedIds.length > 0 && Boolean(memberDrawer.targetDepartmentId)
)
const memberRowSelection = computed(() => ({
  selectedRowKeys: memberDrawer.selectedIds,
  onChange: (keys) => {
    memberDrawer.selectedIds = keys
  },
  getCheckboxProps: () => ({ disabled: !canMoveMembers.value && !canAssignMemberRoles.value })
}))
const memberRoleOptions = computed(() =>
  memberRoleModal.roles
    .filter(
      (role) =>
        role.code !== 'system.superadmin' &&
        (!role.department_id || Number(role.department_id) === Number(memberDrawer.department?.id))
    )
    .map((role) => ({ value: Number(role.id), label: role.name }))
)
const canViewDepartmentMembers = (department) => {
  if (!userStore.hasPermission('department.view', 'department')) return false
  if (!userStore.hasPermission('user.view', 'department')) return false
  if (
    userStore.hasPermission('department.view', 'global') &&
    userStore.hasPermission('user.view', 'global')
  ) {
    return true
  }
  return Number(department.id) === Number(userStore.departmentId)
}

const loadDepartmentMembers = async () => {
  if (!memberDrawer.department) return
  memberDrawer.loading = true
  memberDrawer.error = null
  try {
    const result = await departmentApi.getDepartmentUsers(memberDrawer.department.id)
    memberDrawer.members = Array.isArray(result) ? result : result?.items || result?.users || []
    memberDrawer.selectedIds = []
  } catch (error) {
    memberDrawer.error = error.message || '加载部门成员失败'
    message.error(memberDrawer.error)
  } finally {
    memberDrawer.loading = false
  }
}

const openMemberDrawer = (department) => {
  memberDrawer.department = department
  memberDrawer.members = []
  memberDrawer.selectedIds = []
  memberDrawer.targetDepartmentId = null
  memberDrawer.open = true
  loadDepartmentMembers()
}

const moveSelectedMembers = async () => {
  memberDrawer.moving = true
  try {
    await departmentApi.batchUpdateUserDepartment(
      memberDrawer.selectedIds,
      memberDrawer.targetDepartmentId
    )
    message.success(`已移动 ${memberDrawer.selectedIds.length} 位成员`)
    await Promise.all([loadDepartmentMembers(), fetchDepartments()])
    memberDrawer.targetDepartmentId = null
  } catch (error) {
    message.error(error.message || '批量移动成员失败')
  } finally {
    memberDrawer.moving = false
  }
}

const openMemberRoleModal = async () => {
  memberRoleModal.open = true
  memberRoleModal.loading = true
  memberRoleModal.roleIds = []
  memberRoleModal.mode = 'add'
  try {
    memberRoleModal.roles = await rbacApi.getRoles()
  } catch (error) {
    memberRoleModal.open = false
    message.error(error.message || '加载角色列表失败')
  } finally {
    memberRoleModal.loading = false
  }
}

const saveMemberRoles = async () => {
  memberRoleModal.saving = true
  try {
    await rbacApi.updateUsersRoles(
      memberDrawer.selectedIds,
      memberRoleModal.roleIds,
      memberRoleModal.mode
    )
    memberRoleModal.open = false
    message.success(`已更新 ${memberDrawer.selectedIds.length} 位成员的角色`)
    await loadDepartmentMembers()
  } catch (error) {
    message.error(error.message || '批量设置成员角色失败')
  } finally {
    memberRoleModal.saving = false
  }
}

// 获取部门列表
const fetchDepartments = async () => {
  try {
    departmentManagement.loading = true
    departmentManagement.error = null
    const departments = await departmentApi.getDepartments()
    departmentManagement.departments = departments
  } catch (error) {
    console.error('获取部门列表失败:', error)
    departmentManagement.error = '获取部门列表失败'
  } finally {
    departmentManagement.loading = false
  }
}

// 刷新部门列表
const handleRefresh = async () => {
  if (departmentManagement.refreshing) return
  departmentManagement.refreshing = true
  try {
    await fetchDepartments()
    message.success('刷新成功')
  } catch (error) {
    console.error('刷新失败:', error)
    message.error('刷新失败')
  } finally {
    departmentManagement.refreshing = false
  }
}

// 打开添加部门模态框
const showAddDepartmentModal = () => {
  departmentManagement.modalTitle = '添加部门'
  departmentManagement.editMode = false
  departmentManagement.editDepartmentId = null
  departmentManagement.form = {
    name: '',
    description: '',
    adminUid: '',
    adminPassword: '',
    adminConfirmPassword: '',
    adminPhone: '',
    uidError: '',
    phoneError: ''
  }
  departmentManagement.modalVisible = true
}

// 打开编辑部门模态框
const showEditDepartmentModal = (department) => {
  departmentManagement.modalTitle = '编辑部门'
  departmentManagement.editMode = true
  departmentManagement.editDepartmentId = department.id
  departmentManagement.form = {
    name: department.name,
    description: department.description || '',
    adminUid: '',
    adminPassword: '',
    adminConfirmPassword: '',
    adminPhone: '',
    uidError: '',
    phoneError: ''
  }
  departmentManagement.modalVisible = true
}

// 验证手机号格式
const validatePhoneNumber = (phone) => {
  if (!phone) {
    return true // 手机号可选
  }
  const phoneRegex = /^1[3-9]\d{9}$/
  return phoneRegex.test(phone)
}

// 监听手机号输入变化
watch(
  () => departmentManagement.form.adminPhone,
  (newPhone) => {
    departmentManagement.form.phoneError = ''
    if (newPhone && !validatePhoneNumber(newPhone)) {
      departmentManagement.form.phoneError = '请输入正确的手机号格式'
    }
  }
)

// 检查管理员UID是否可用
const checkAdminUid = async () => {
  const uid = departmentManagement.form.adminUid.trim()
  departmentManagement.form.uidError = ''

  if (!uid) {
    return
  }

  // 验证格式
  if (!/^[a-zA-Z0-9_]+$/.test(uid)) {
    departmentManagement.form.uidError = 'UID只能包含字母、数字和下划线'
    return
  }

  if (uid.length < 3 || uid.length > 20) {
    departmentManagement.form.uidError = 'UID长度必须在3-20个字符之间'
    return
  }

  // 检查是否已存在
  try {
    const result = await apiGet(`/api/auth/check-uid/${uid}`)
    if (!result.is_available) {
      departmentManagement.form.uidError = '该UID已被使用'
    }
  } catch (error) {
    console.error('检查UID失败:', error)
  }
}

// 处理部门表单提交
const handleDepartmentFormSubmit = async () => {
  try {
    // 验证部门名称
    if (!departmentManagement.form.name.trim()) {
      notification.error({ message: '部门名称不能为空' })
      return
    }

    if (departmentManagement.form.name.trim().length < 2) {
      notification.error({ message: '部门名称至少2个字符' })
      return
    }

    if (!departmentManagement.editMode) {
      // 新建部门时才需要校验并创建管理员
      const adminUid = departmentManagement.form.adminUid.trim()
      if (!adminUid) {
        notification.error({ message: '请输入管理员UID' })
        return
      }

      if (!/^[a-zA-Z0-9_]+$/.test(adminUid)) {
        notification.error({ message: 'UID只能包含字母、数字和下划线' })
        return
      }

      if (adminUid.length < 3 || adminUid.length > 20) {
        notification.error({ message: 'UID长度必须在3-20个字符之间' })
        return
      }

      if (departmentManagement.form.uidError) {
        notification.error({ message: '管理员UID已存在或格式错误' })
        return
      }

      if (!departmentManagement.form.adminPassword) {
        notification.error({ message: '请输入管理员密码' })
        return
      }

      if (!isPasswordLongEnough(departmentManagement.form.adminPassword)) {
        notification.error({ message: `密码至少需要 ${MIN_PASSWORD_LENGTH} 个字符` })
        return
      }

      if (
        departmentManagement.form.adminPassword !== departmentManagement.form.adminConfirmPassword
      ) {
        notification.error({ message: '两次输入的密码不一致' })
        return
      }

      if (
        departmentManagement.form.adminPhone &&
        !validatePhoneNumber(departmentManagement.form.adminPhone)
      ) {
        notification.error({ message: '请输入正确的手机号格式' })
        return
      }
    }

    departmentManagement.loading = true

    if (departmentManagement.editMode) {
      // 更新部门
      await departmentApi.updateDepartment(departmentManagement.editDepartmentId, {
        name: departmentManagement.form.name.trim(),
        description: departmentManagement.form.description.trim() || undefined
      })
      notification.success({ message: '部门更新成功' })
    } else {
      // 创建部门，同时创建管理员
      const adminUid = departmentManagement.form.adminUid.trim()
      await departmentApi.createDepartment({
        name: departmentManagement.form.name.trim(),
        description: departmentManagement.form.description.trim() || undefined,
        admin_uid: adminUid,
        admin_password: departmentManagement.form.adminPassword,
        admin_phone: departmentManagement.form.adminPhone || undefined
      })

      message.success(`部门创建成功，管理员 "${adminUid}" 已创建`)
    }

    // 重新获取部门列表
    await fetchDepartments()
    departmentManagement.modalVisible = false
  } catch (error) {
    console.error('部门操作失败:', error)
    notification.error({
      message: '操作失败',
      description: error.message || '请稍后重试'
    })
  } finally {
    departmentManagement.loading = false
  }
}

// 删除部门
const confirmDeleteDepartment = (department) => {
  Modal.confirm({
    title: '确认删除部门',
    content: `确定要删除部门 "${department.name}" 吗？此操作不可撤销。该部门下的用户会被迁移到默认部门，部门级配置和部门 API Key 会一并清理。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        departmentManagement.loading = true
        await departmentApi.deleteDepartment(department.id)
        notification.success({ message: '部门删除成功' })
        // 重新获取部门列表
        await fetchDepartments()
      } catch (error) {
        console.error('删除部门失败:', error)
        notification.error({
          message: '删除失败',
          description: error.message || '请稍后重试'
        })
      } finally {
        departmentManagement.loading = false
      }
    }
  })
}

// 在组件挂载时获取部门列表
onMounted(() => {
  fetchDepartments()
})
</script>

<style lang="less" scoped>
.department-management {
  .header-section {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 16px;
    margin-bottom: 16px;

    .header-content {
      flex: 1;
      min-width: 0;

      .section-title {
        font-size: 16px;
        font-weight: 500;
        color: var(--gray-900);
        line-height: 1.4;
        margin: 12px 0 12px;
      }

      .section-description {
        font-size: 14px;
        color: var(--gray-600);
        line-height: 1.4;
        margin: 0;
      }
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;

      .refresh-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 6px;
        transition: all 0.2s ease;

        &:hover {
          background: var(--gray-25);
        }

        .spin {
          animation: spin 1s linear infinite;
        }
      }
    }
  }

  .content-section {
    overflow: hidden;

    .error-message {
      padding: 16px 24px;
    }

    .empty-state {
      padding: 60px 20px;
      text-align: center;
    }

    .department-table {
      :deep(.ant-table-thead > tr > th) {
        background: var(--gray-50);
        font-weight: 500;
        padding: 8px 12px;
      }

      :deep(.ant-table-tbody > tr > td) {
        padding: 8px 12px;
      }

      .department-link {
        padding: 0;
        border: 0;
        background: transparent;
        color: var(--main-600);
        font: inherit;
        font-weight: 500;
        cursor: pointer;

        &:hover {
          color: var(--color-primary-500);
        }
      }

      .member-count {
        height: auto;
        padding: 0;
      }

      .description-text {
        color: var(--gray-600);
      }

      .action-btn {
        padding: 4px 8px;
        border-radius: 6px;
        transition: all 0.2s ease;

        &:hover {
          background: var(--gray-25);
        }
      }
    }
  }
}

.member-summary,
.drawer-footer,
.batch-move {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.member-summary {
  margin-bottom: 14px;

  > div {
    display: grid;
    gap: 3px;
  }

  span {
    color: var(--gray-500);
    font-size: 12px;
  }
}

.member-error,
.member-role-hint {
  margin-bottom: 14px;
}

.member-identity {
  display: grid;
  min-width: 0;

  span {
    color: var(--gray-500);
    font-size: 12px;
  }
}

.drawer-footer {
  flex-wrap: wrap;

  > span {
    color: var(--gray-600);
  }
}

.batch-move {
  margin-left: auto;

  .ant-select {
    width: 180px;
  }
}

@media (max-width: 720px) {
  .drawer-footer,
  .batch-move {
    align-items: stretch;
    flex-direction: column;
  }

  .batch-move {
    width: 100%;
    margin-left: 0;

    .ant-select {
      width: 100%;
    }
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.department-modal {
  :deep(.ant-modal-header) {
    padding: 20px 24px;
    border-bottom: 1px solid var(--gray-150);

    .ant-modal-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--gray-900);
    }
  }

  :deep(.ant-modal-body) {
    padding: 24px;
  }

  .department-form {
    .form-item {
      margin-bottom: 20px;

      :deep(.ant-form-item-label) {
        padding-bottom: 4px;

        label {
          font-weight: 500;
          color: var(--gray-900);
        }
      }
    }
  }

  .error-text {
    color: var(--color-error-500);
    font-size: 12px;
    margin-top: 4px;
    line-height: 1.3;
  }

  .help-text {
    color: var(--gray-600);
    font-size: 12px;
    margin-top: 4px;
    line-height: 1.3;
  }
}
</style>

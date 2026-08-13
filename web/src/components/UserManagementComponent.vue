<template>
  <div class="user-management">
    <div class="header-section">
      <div class="header-content">
        <div class="section-title">用户管理</div>
        <p class="section-description">
          集中管理用户、部门与角色。可多选用户批量调整，也可通过 Excel 一次导入。
        </p>
      </div>
      <div class="header-actions">
        <a-button
          v-if="canImportUsers"
          :loading="templateDownloading"
          class="lucide-icon-btn"
          @click="downloadImportTemplate"
        >
          <template #icon><Download :size="16" /></template>
          下载模板
        </a-button>
        <a-button v-if="canImportUsers" class="lucide-icon-btn" @click="openImportModal">
          <template #icon><UploadIcon :size="16" /></template>
          导入用户
        </a-button>
        <a-button
          :loading="userManagement.refreshing"
          title="刷新"
          class="refresh-btn lucide-icon-btn"
          @click="handleRefresh"
        >
          <template #icon>
            <RefreshCw :size="16" :class="{ spin: userManagement.refreshing }" />
          </template>
        </a-button>
        <a-button
          v-if="userStore.hasPermission('user.create')"
          type="primary"
          class="lucide-icon-btn"
          @click="showAddUserModal"
        >
          <template #icon><Plus :size="16" /></template>
          添加用户
        </a-button>
      </div>
    </div>

    <div class="filter-section">
      <a-input
        v-model:value="userManagement.searchKeyword"
        class="search-input"
        placeholder="搜索用户名 / ID / 手机号"
        allow-clear
      >
        <template #prefix><Search :size="16" /></template>
      </a-input>
      <a-select v-model:value="userManagement.departmentFilter" class="filter-select">
        <a-select-option value="">全部部门</a-select-option>
        <a-select-option
          v-for="dept in departmentFilterOptions"
          :key="dept.value"
          :value="dept.value"
        >
          {{ dept.label }}
        </a-select-option>
      </a-select>
      <a-select v-model:value="userManagement.roleFilter" class="filter-select">
        <a-select-option value="">全部旧角色</a-select-option>
        <a-select-option value="superadmin">超级管理员</a-select-option>
        <a-select-option value="admin">管理员</a-select-option>
        <a-select-option value="user">普通用户</a-select-option>
      </a-select>
      <span class="result-count">共 {{ filteredUsers.length }} 人</span>
    </div>

    <div v-if="selectedUserIds.length" class="batch-toolbar">
      <div class="selection-summary">
        <Users :size="17" />
        <strong>已选 {{ selectedUserIds.length }} 人</strong>
        <a-button type="link" size="small" @click="clearSelection">取消选择</a-button>
      </div>
      <div class="batch-actions">
        <div v-if="canBatchDepartment" class="batch-action-group">
          <Building2 :size="16" />
          <a-select
            v-model:value="batchDepartmentId"
            placeholder="调整到部门"
            class="batch-department-select"
            :disabled="batchLoading"
          >
            <a-select-option
              v-for="department in departmentManagement.departments"
              :key="department.id"
              :value="department.id"
            >
              {{ department.name }}
            </a-select-option>
          </a-select>
          <a-button
            :disabled="!batchDepartmentId"
            :loading="batchAction === 'department'"
            @click="confirmBatchDepartment"
          >
            应用
          </a-button>
        </div>
        <div v-if="canBatchRoles" class="batch-action-group role-batch-group">
          <ShieldCheck :size="16" />
          <a-select
            v-model:value="batchRoleMode"
            class="batch-mode-select"
            :disabled="batchLoading"
          >
            <a-select-option value="add">追加角色</a-select-option>
            <a-select-option value="remove">移除角色</a-select-option>
            <a-select-option value="replace">替换角色</a-select-option>
          </a-select>
          <a-select
            v-model:value="batchRoleIds"
            mode="multiple"
            placeholder="选择 RBAC 角色"
            class="batch-role-select"
            :disabled="batchLoading"
            :max-tag-count="2"
          >
            <a-select-option v-for="role in batchAssignableRoles" :key="role.id" :value="role.id">
              {{ role.name
              }}{{ role.department_id ? ` · ${departmentName(role.department_id)}` : '' }}
            </a-select-option>
          </a-select>
          <a-button
            :disabled="!batchRoleIds.length"
            :loading="batchAction === 'roles'"
            @click="confirmBatchRoles"
          >
            应用
          </a-button>
        </div>
      </div>
    </div>

    <div class="content-section">
      <a-alert
        v-if="userManagement.error"
        type="error"
        :message="userManagement.error"
        show-icon
        closable
        class="error-message"
        @close="userManagement.error = null"
      />

      <a-table
        class="user-table"
        size="middle"
        :columns="userColumns"
        :data-source="filteredUsers"
        :row-key="(record) => record.id"
        :row-selection="rowSelection"
        :loading="userManagement.loading"
        :pagination="paginationConfig"
        :scroll="{ x: 1120 }"
        @change="handleTableChange"
      >
        <template #emptyText>
          <a-empty
            :description="userManagement.users.length === 0 ? '暂无用户数据' : '没有匹配的用户'"
          />
        </template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'user'">
            <div class="user-cell">
              <FallbackAvatar
                :src="record.avatar"
                :default-src="getUserDefaultAvatarSrc(record)"
                :name="record.username"
                :seed="record.uid || record.username"
                kind="user"
                :size="34"
                shape="circle"
                :alt="record.username"
              />
              <div class="user-identity">
                <span class="user-name">{{ record.username }}</span>
                <span class="user-uid">{{ record.uid || '-' }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'phone'">
            <span class="phone-text">{{ record.phone_number || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'department'">
            <a-tag v-if="record.department_name" class="department-tag">
              <Building2 :size="12" /> {{ record.department_name }}
            </a-tag>
            <span v-else class="muted-text">未分配</span>
          </template>
          <template v-else-if="column.key === 'legacyRole'">
            <a-tag :class="['legacy-role-tag', `legacy-role-${record.role || 'user'}`]">
              {{ legacyRoleLabel(record.role) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'rbacRoles'">
            <div class="role-tags">
              <span v-if="userRolesLoading[record.id]" class="muted-text">加载中…</span>
              <template v-else-if="userRolesById[record.id]?.length">
                <a-tooltip
                  v-for="role in userRolesById[record.id].slice(0, 2)"
                  :key="role.id"
                  :title="role.description || role.name"
                >
                  <a-tag class="rbac-role-tag">{{ role.name }}</a-tag>
                </a-tooltip>
                <a-tooltip
                  v-if="userRolesById[record.id].length > 2"
                  :title="
                    userRolesById[record.id]
                      .slice(2)
                      .map((role) => role.name)
                      .join('、')
                  "
                >
                  <a-tag class="more-role-tag">+{{ userRolesById[record.id].length - 2 }}</a-tag>
                </a-tooltip>
              </template>
              <span v-else class="muted-text">-</span>
            </div>
          </template>
          <template v-else-if="column.key === 'createdAt'">
            <span class="time-text">{{ formatTime(record.created_at) }}</span>
          </template>
          <template v-else-if="column.key === 'lastLogin'">
            <span class="time-text">{{ formatTime(record.last_login) }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-dropdown
              v-if="
                userStore.hasPermission('user.update') || userStore.hasPermission('user.delete')
              "
              :trigger="['click']"
            >
              <a-button type="text" class="row-more-button" title="更多操作">
                <MoreHorizontal :size="17" />
              </a-button>
              <template #overlay>
                <a-menu>
                  <a-menu-item
                    v-if="userStore.hasPermission('user.update')"
                    key="edit"
                    @click="showEditUserModal(record)"
                  >
                    <span class="lucide-menu-item"><SquarePen :size="14" />编辑用户</span>
                  </a-menu-item>
                  <a-menu-item
                    v-if="userStore.hasPermission('user.delete')"
                    key="delete"
                    :disabled="isUserDeleteDisabled(record)"
                    :danger="!isUserDeleteDisabled(record)"
                    @click="confirmDeleteUser(record)"
                  >
                    <span class="lucide-menu-item"><Trash2 :size="14" />删除用户</span>
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:open="userManagement.modalVisible"
      :title="userManagement.modalTitle"
      :confirm-loading="userManagement.formSubmitting"
      :mask-closable="false"
      width="480px"
      class="user-modal"
      @ok="handleUserFormSubmit"
      @cancel="userManagement.modalVisible = false"
    >
      <a-form layout="vertical" class="user-form">
        <a-form-item label="用户名" required class="form-item">
          <a-input
            v-model:value="userManagement.form.username"
            placeholder="请输入用户名（2-20个字符）"
            :maxlength="20"
            @blur="validateAndGenerateUid"
          />
          <div v-if="userManagement.form.usernameError" class="error-text">
            {{ userManagement.form.usernameError }}
          </div>
          <div
            v-if="userManagement.form.generatedUid && !userManagement.editMode"
            class="help-text"
          >
            登录 ID：{{ userManagement.form.generatedUid }}，将用于登录并根据用户名自动生成。
          </div>
        </a-form-item>
        <a-form-item label="手机号" class="form-item">
          <a-input
            v-model:value="userManagement.form.phoneNumber"
            placeholder="请输入手机号（可选，可用于登录）"
            :maxlength="11"
          />
          <div v-if="userManagement.form.phoneError" class="error-text">
            {{ userManagement.form.phoneError }}
          </div>
        </a-form-item>
        <template v-if="userManagement.editMode">
          <div class="password-toggle">
            <a-checkbox v-model:checked="userManagement.displayPasswordFields">修改密码</a-checkbox>
          </div>
        </template>
        <template v-if="!userManagement.editMode || userManagement.displayPasswordFields">
          <a-form-item label="密码" required class="form-item">
            <a-input-password
              v-model:value="userManagement.form.password"
              :placeholder="`请输入密码（至少 ${MIN_PASSWORD_LENGTH} 位）`"
              :minlength="MIN_PASSWORD_LENGTH"
            />
          </a-form-item>
          <a-form-item label="确认密码" required class="form-item">
            <a-input-password
              v-model:value="userManagement.form.confirmPassword"
              placeholder="请再次输入密码"
            />
          </a-form-item>
        </template>
        <a-form-item
          v-if="userManagement.editMode && userManagement.form.role === 'superadmin'"
          label="旧角色"
          class="form-item"
        >
          <a-input value="超级管理员" disabled />
          <div class="help-text">超级管理员账户无法在此降级。</div>
        </a-form-item>
        <a-form-item v-else label="旧角色" class="form-item">
          <a-select v-model:value="userManagement.form.role">
            <a-select-option value="user">普通用户</a-select-option>
            <a-select-option v-if="userStore.isSuperAdmin" value="admin">管理员</a-select-option>
          </a-select>
          <div class="help-text">业务权限请通过 RBAC 角色分配。</div>
        </a-form-item>
        <a-form-item v-if="canSelectDepartment" label="部门" class="form-item">
          <a-select v-model:value="userManagement.form.departmentId" placeholder="请选择部门">
            <a-select-option
              v-for="dept in departmentManagement.departments"
              :key="dept.id"
              :value="dept.id"
            >
              {{ dept.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="importState.open"
      title="批量导入用户"
      width="760px"
      :mask-closable="false"
      :closable="!importState.loading"
      class="import-user-modal"
      @cancel="closeImportModal"
    >
      <a-steps :current="importState.step" size="small" class="import-steps">
        <a-step title="选择文件" />
        <a-step title="数据预检" />
        <a-step title="导入完成" />
      </a-steps>

      <div v-if="importState.step === 0" class="import-select-panel">
        <a-alert
          type="info"
          show-icon
          message="请使用系统模板填写用户"
          description="支持 .xlsx 文件。部门可填写部门名称，角色可填写多个角色名称；密码只用于创建账户，不会在预检或结果中显示。"
        />
        <a-upload-dragger
          :file-list="importState.fileList"
          :before-upload="selectImportFile"
          :max-count="1"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          class="import-dragger"
          @remove="removeImportFile"
        >
          <p class="ant-upload-drag-icon"><FileSpreadsheet :size="42" /></p>
          <p class="ant-upload-text">点击或拖拽 Excel 文件到此处</p>
          <p class="ant-upload-hint">文件上传后会先校验，不会立即创建用户。</p>
        </a-upload-dragger>
        <a-button type="link" class="template-link" @click="downloadImportTemplate">
          <Download :size="14" />下载 Excel 模板
        </a-button>
      </div>

      <div v-else class="import-review-panel">
        <div class="import-summary">
          <div class="summary-item">
            <span>总行数</span><strong>{{ importState.summary.total }}</strong>
          </div>
          <div class="summary-item success">
            <span>{{ importState.step === 2 ? '创建成功' : '可导入' }}</span>
            <strong>{{
              importState.step === 2 ? importState.createdCount : importState.summary.valid
            }}</strong>
          </div>
          <div class="summary-item" :class="{ error: importState.summary.invalid }">
            <span>异常</span><strong>{{ importState.summary.invalid }}</strong>
          </div>
        </div>
        <a-alert
          v-if="importState.step === 1 && importState.summary.invalid"
          type="warning"
          show-icon
          message="存在无法导入的行"
          description="请根据下方错误修正 Excel 后重新上传。为避免产生部分数据，有异常时不能提交整批导入。"
          class="import-alert"
        />
        <a-alert
          v-if="importState.step === 2"
          :type="importState.createdCount ? 'success' : 'warning'"
          show-icon
          :message="
            importState.createdCount
              ? `已创建 ${importState.createdCount} 个用户`
              : '没有用户被创建'
          "
          description="用户列表已刷新。导入结果不会显示账户密码。"
          class="import-alert"
        />
        <a-table
          :columns="importColumns"
          :data-source="importState.rows"
          :row-key="(row) => row.row"
          :pagination="{ pageSize: 8, size: 'small', hideOnSinglePage: true }"
          :scroll="{ x: 700 }"
          size="small"
          class="import-preview-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <span :class="['row-status', { success: isImportRowSuccess(record) }]">
                <CheckCircle2 v-if="isImportRowSuccess(record)" :size="14" />
                <AlertCircle v-else :size="14" />
                {{ importRowStatusLabel(record) }}
              </span>
            </template>
            <template v-else-if="column.key === 'account'">
              <div class="import-account-cell">
                <strong>{{ record.username || '-' }}</strong>
                <span>{{ record.uid || '自动生成 ID' }}</span>
              </div>
            </template>
            <template v-else-if="column.key === 'department'">
              {{ record.department_name || '-' }}
            </template>
            <template v-else-if="column.key === 'roles'">
              {{ (record.role_names || []).join('、') || '-' }}
            </template>
            <template v-else-if="column.key === 'errors'">
              <span v-if="record.errors?.length" class="import-errors">
                {{ record.errors.join('；') }}
              </span>
              <span v-else class="muted-text">-</span>
            </template>
          </template>
        </a-table>
      </div>

      <template #footer>
        <div class="import-footer">
          <a-button :disabled="importState.loading" @click="closeImportModal">
            {{ importState.step === 2 ? '关闭' : '取消' }}
          </a-button>
          <a-button
            v-if="importState.step === 0"
            type="primary"
            :disabled="!importState.file"
            :loading="importState.loading"
            @click="previewImport"
          >
            开始预检
          </a-button>
          <template v-else-if="importState.step === 1">
            <a-button :disabled="importState.loading" @click="resetImportFile">重新选择</a-button>
            <a-button
              type="primary"
              :disabled="!importState.summary.valid || importState.summary.invalid > 0"
              :loading="importState.loading"
              @click="confirmImportUsers"
            >
              确认导入 {{ importState.summary.valid }} 人
            </a-button>
          </template>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message, Modal, Upload } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'
import { departmentApi, userAdminApi } from '@/apis'
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SquarePen,
  Trash2,
  Upload as UploadIcon,
  Users
} from 'lucide-vue-next'
import { formatDateTime } from '@/utils/time'
import { isPasswordLongEnough, MIN_PASSWORD_LENGTH } from '@/utils/passwordValidation'
import { generatePixelAvatar } from '@/utils/pixelAvatar'
import FallbackAvatar from '@/components/common/FallbackAvatar.vue'

const userStore = useUserStore()

const userColumns = [
  { title: '用户', key: 'user', width: 210, fixed: 'left' },
  { title: '手机号', key: 'phone', width: 128 },
  { title: '部门', key: 'department', width: 140 },
  { title: '旧角色', key: 'legacyRole', width: 106 },
  { title: 'RBAC 角色', key: 'rbacRoles', width: 210 },
  { title: '创建时间', key: 'createdAt', width: 150 },
  { title: '最后登录', key: 'lastLogin', width: 150 },
  { title: '操作', key: 'actions', width: 64, align: 'center', fixed: 'right' }
]

const importColumns = [
  { title: '行', dataIndex: 'row', width: 54 },
  { title: '状态', key: 'status', width: 90 },
  { title: '用户', key: 'account', width: 150 },
  { title: '手机号', dataIndex: 'phone_number', width: 120 },
  { title: '部门', key: 'department', width: 110 },
  { title: '角色', key: 'roles', width: 140 },
  { title: '校验信息', key: 'errors', width: 220 }
]

const userManagement = reactive({
  loading: false,
  refreshing: false,
  formSubmitting: false,
  users: [],
  searchKeyword: '',
  departmentFilter: '',
  roleFilter: '',
  currentPage: 1,
  pageSize: 20,
  error: null,
  modalVisible: false,
  modalTitle: '添加用户',
  editMode: false,
  editUserId: null,
  displayPasswordFields: true,
  form: emptyUserForm()
})

const departmentManagement = reactive({ departments: [] })
const availableRoles = ref([])
const selectedUserIds = ref([])
const userRolesById = reactive({})
const userRolesLoading = reactive({})
const batchDepartmentId = ref(null)
const batchRoleMode = ref('add')
const batchRoleIds = ref([])
const batchAction = ref('')
const templateDownloading = ref(false)

const importState = reactive({
  open: false,
  step: 0,
  loading: false,
  file: null,
  fileList: [],
  rows: [],
  summary: { total: 0, valid: 0, invalid: 0 },
  createdCount: 0
})

function emptyUserForm() {
  return {
    username: '',
    generatedUid: '',
    phoneNumber: '',
    password: '',
    confirmPassword: '',
    role: 'user',
    departmentId: null,
    usernameError: '',
    phoneError: ''
  }
}

const canSelectDepartment = computed(() =>
  userManagement.editMode
    ? userStore.hasPermission('user.update', 'global')
    : userStore.hasPermission('user.create', 'global')
)
const canBatchDepartment = computed(() => userStore.hasPermission('user.update', 'global'))
const canBatchRoles = computed(
  () => userStore.hasPermission('user.assign_role') && userStore.hasPermission('role.assign')
)
const canImportUsers = computed(() => userStore.hasPermission('user.create'))
const canBatchUsers = computed(() => canBatchDepartment.value || canBatchRoles.value)
const batchLoading = computed(() => Boolean(batchAction.value))

const departmentFilterOptions = computed(() => {
  const options = new Map()
  departmentManagement.departments.forEach((dept) => {
    options.set(String(dept.id), { value: String(dept.id), label: dept.name })
  })
  userManagement.users.forEach((user) => {
    if (user.department_id == null && !user.department_name) return
    const value = String(user.department_id ?? user.department_name)
    if (!options.has(value)) {
      options.set(value, { value, label: user.department_name || `部门 ${user.department_id}` })
    }
  })
  return [...options.values()]
})

const filteredUsers = computed(() => {
  const keyword = userManagement.searchKeyword.trim().toLowerCase()
  return userManagement.users.filter((user) => {
    const matchesKeyword =
      !keyword ||
      [user.username, user.uid, user.phone_number].some((value) =>
        String(value || '')
          .toLowerCase()
          .includes(keyword)
      )
    const matchesDepartment =
      !userManagement.departmentFilter ||
      String(user.department_id ?? user.department_name ?? '') === userManagement.departmentFilter
    const matchesRole = !userManagement.roleFilter || user.role === userManagement.roleFilter
    return matchesKeyword && matchesDepartment && matchesRole
  })
})

const paginatedUsers = computed(() => {
  const start = (userManagement.currentPage - 1) * userManagement.pageSize
  return filteredUsers.value.slice(start, start + userManagement.pageSize)
})

const selectedUsers = computed(() => {
  const selected = new Set(selectedUserIds.value)
  return userManagement.users.filter((user) => selected.has(user.id))
})

const batchAssignableRoles = computed(() => {
  const departmentIds = new Set(
    selectedUsers.value
      .map((user) => user.department_id)
      .filter((id) => id != null)
      .map(Number)
  )
  return availableRoles.value.filter((role) => {
    if (role.code === 'system.superadmin' && !userStore.isSuperAdmin) return false
    if (role.department_id == null) return true
    return departmentIds.size === 1 && departmentIds.has(Number(role.department_id))
  })
})

const rowSelection = computed(() => {
  if (!canBatchUsers.value) return null
  return {
    selectedRowKeys: selectedUserIds.value,
    preserveSelectedRowKeys: true,
    onChange: (keys) => {
      selectedUserIds.value = keys.map(Number)
    },
    getCheckboxProps: (record) => ({
      disabled:
        record.id === userStore.userId ||
        record.role === 'superadmin' ||
        (record.role === 'admin' && !userStore.isSuperAdmin),
      name: record.username
    })
  }
})

const paginationConfig = computed(() => ({
  current: userManagement.currentPage,
  pageSize: userManagement.pageSize,
  total: filteredUsers.value.length,
  pageSizeOptions: ['20', '50', '100'],
  showSizeChanger: true,
  showTotal: (total) => `共 ${total} 人`,
  size: 'small'
}))

watch(
  () => [userManagement.searchKeyword, userManagement.departmentFilter, userManagement.roleFilter],
  () => {
    userManagement.currentPage = 1
  }
)

watch(
  () => paginatedUsers.value.map((user) => user.id).join(','),
  () => loadVisibleUserRoles(),
  { immediate: true }
)

watch(
  () => userManagement.displayPasswordFields,
  (visible) => {
    if (!visible) {
      userManagement.form.password = ''
      userManagement.form.confirmPassword = ''
    }
  }
)

watch(
  () => userManagement.form.phoneNumber,
  (phone) => {
    userManagement.form.phoneError =
      phone && !validatePhoneNumber(phone) ? '请输入正确的手机号格式' : ''
  }
)

watch(batchAssignableRoles, (roles) => {
  const allowed = new Set(roles.map((role) => role.id))
  batchRoleIds.value = batchRoleIds.value.filter((id) => allowed.has(id))
})

function handleTableChange(pagination) {
  userManagement.currentPage = pagination.current || 1
  userManagement.pageSize = pagination.pageSize || 20
}

function clearSelection() {
  selectedUserIds.value = []
  batchDepartmentId.value = null
  batchRoleIds.value = []
}

async function fetchUsers() {
  userManagement.loading = true
  try {
    userManagement.users = await userStore.getUsers()
    const validIds = new Set(userManagement.users.map((user) => user.id))
    selectedUserIds.value = selectedUserIds.value.filter((id) => validIds.has(id))
    userManagement.error = null
  } catch (error) {
    console.error('获取用户列表失败:', error)
    userManagement.error = error.message || '获取用户列表失败'
  } finally {
    userManagement.loading = false
  }
}

async function fetchDepartments() {
  if (!userStore.hasPermission('department.view')) return
  try {
    departmentManagement.departments = await departmentApi.getDepartments()
  } catch (error) {
    console.error('获取部门列表失败:', error)
  }
}

async function fetchRoles() {
  if (!userStore.hasPermission('role.view') && !canBatchRoles.value) return
  try {
    availableRoles.value = await userAdminApi.getRoles()
  } catch (error) {
    console.error('获取角色列表失败:', error)
  }
}

async function loadVisibleUserRoles() {
  const pending = paginatedUsers.value.filter(
    (user) => !Object.hasOwn(userRolesById, user.id) && !userRolesLoading[user.id]
  )
  await Promise.allSettled(
    pending.map(async (user) => {
      userRolesLoading[user.id] = true
      try {
        userRolesById[user.id] = await userAdminApi.getUserRoles(user.id)
      } catch (error) {
        userRolesById[user.id] = []
        console.error(`获取用户 ${user.id} 的角色失败:`, error)
      } finally {
        userRolesLoading[user.id] = false
      }
    })
  )
}

async function handleRefresh() {
  if (userManagement.refreshing) return
  userManagement.refreshing = true
  Object.keys(userRolesById).forEach((key) => delete userRolesById[key])
  try {
    await Promise.all([fetchUsers(), fetchDepartments(), fetchRoles()])
    await loadVisibleUserRoles()
    message.success('用户数据已刷新')
  } finally {
    userManagement.refreshing = false
  }
}

function confirmBatchDepartment() {
  const department = departmentManagement.departments.find(
    (item) => Number(item.id) === Number(batchDepartmentId.value)
  )
  Modal.confirm({
    title: `将 ${selectedUserIds.value.length} 人调整到“${department?.name || '所选部门'}”？`,
    content: '部门调整会立即生效，部门角色的可用范围也可能随之变化。',
    okText: '确认调整',
    async onOk() {
      batchAction.value = 'department'
      try {
        const result = await userAdminApi.batchUpdateDepartment(
          selectedUserIds.value,
          batchDepartmentId.value
        )
        message.success(`已调整 ${result.updated_count ?? selectedUserIds.value.length} 名用户`)
        clearSelection()
        await fetchUsers()
      } catch (error) {
        message.error(error.message || '批量调整部门失败')
        throw error
      } finally {
        batchAction.value = ''
      }
    }
  })
}

function confirmBatchRoles() {
  const modeLabels = { add: '追加', remove: '移除', replace: '替换' }
  Modal.confirm({
    title: `${modeLabels[batchRoleMode.value]} ${selectedUserIds.value.length} 人的角色？`,
    content:
      batchRoleMode.value === 'replace'
        ? '替换会移除用户当前未选中的角色，请确认后继续。'
        : '角色权限将在保存后立即生效。',
    okText: '确认应用',
    async onOk() {
      batchAction.value = 'roles'
      try {
        const result = await userAdminApi.batchUpdateRoles(
          selectedUserIds.value,
          batchRoleIds.value,
          batchRoleMode.value
        )
        ;(result.users || []).forEach((item) => {
          userRolesById[item.user_id] = item.roles || []
        })
        message.success(
          `已更新 ${result.updated_count ?? selectedUserIds.value.length} 名用户的角色`
        )
        clearSelection()
        await fetchUsers()
      } catch (error) {
        message.error(error.message || '批量调整角色失败')
        throw error
      } finally {
        batchAction.value = ''
      }
    }
  })
}

function showAddUserModal() {
  userManagement.modalTitle = '添加用户'
  userManagement.editMode = false
  userManagement.editUserId = null
  userManagement.form = emptyUserForm()
  userManagement.displayPasswordFields = true
  userManagement.modalVisible = true
}

function showEditUserModal(user) {
  userManagement.modalTitle = '编辑用户'
  userManagement.editMode = true
  userManagement.editUserId = user.id
  userManagement.form = {
    ...emptyUserForm(),
    username: user.username,
    generatedUid: user.uid || '',
    phoneNumber: user.phone_number || '',
    role: user.role,
    departmentId: user.department_id || null
  }
  userManagement.displayPasswordFields = false
  userManagement.modalVisible = true
}

async function validateAndGenerateUid() {
  const username = userManagement.form.username.trim()
  userManagement.form.usernameError = ''
  userManagement.form.generatedUid = ''
  if (!username || userManagement.editMode) return
  try {
    const result = await userStore.validateUsernameAndGenerateUid(username)
    userManagement.form.generatedUid = result.uid
  } catch (error) {
    userManagement.form.usernameError = error.message || '用户名验证失败'
  }
}

async function handleUserFormSubmit() {
  const form = userManagement.form
  if (form.username.trim().length < 2 || form.username.trim().length > 20) {
    message.error('用户名长度必须在 2-20 个字符之间')
    return
  }
  if (form.phoneNumber && !validatePhoneNumber(form.phoneNumber)) {
    message.error('请输入正确的手机号格式')
    return
  }
  if (userManagement.displayPasswordFields) {
    if (!isPasswordLongEnough(form.password)) {
      message.error(`密码至少需要 ${MIN_PASSWORD_LENGTH} 个字符`)
      return
    }
    if (form.password !== form.confirmPassword) {
      message.error('两次输入的密码不一致')
      return
    }
  }

  userManagement.formSubmitting = true
  try {
    if (userManagement.editMode) {
      const data = { username: form.username.trim(), phone_number: form.phoneNumber || '' }
      if (userStore.isSuperAdmin) data.role = form.role
      if (userStore.hasPermission('user.update', 'global') && form.departmentId) {
        data.department_id = form.departmentId
      }
      if (userManagement.displayPasswordFields && form.password) data.password = form.password
      await userStore.updateUser(userManagement.editUserId, data)
      message.success('用户更新成功')
    } else {
      const data = {
        username: form.username.trim(),
        password: form.password,
        role: userStore.isSuperAdmin ? form.role : 'user',
        phone_number: form.phoneNumber || null
      }
      if (userStore.hasPermission('user.create', 'global') && form.departmentId) {
        data.department_id = form.departmentId
      }
      await userStore.createUser(data)
      message.success('用户创建成功')
    }
    userManagement.modalVisible = false
    await fetchUsers()
  } catch (error) {
    message.error(error.message || '用户操作失败')
  } finally {
    userManagement.formSubmitting = false
  }
}

function confirmDeleteUser(user) {
  if (isUserDeleteDisabled(user)) return
  Modal.confirm({
    title: '确认删除用户',
    content: `确定要删除用户“${user.username}”吗？此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await userStore.deleteUser(user.id)
      message.success('用户删除成功')
      await fetchUsers()
    }
  })
}

function isUserDeleteDisabled(user) {
  return user.id === userStore.userId || (user.role === 'superadmin' && !userStore.isSuperAdmin)
}

function openImportModal() {
  resetImportState()
  importState.open = true
}

function closeImportModal() {
  if (importState.loading) return
  importState.open = false
  resetImportState()
}

function resetImportState() {
  importState.step = 0
  importState.loading = false
  importState.file = null
  importState.fileList = []
  importState.rows = []
  importState.summary = { total: 0, valid: 0, invalid: 0 }
  importState.createdCount = 0
}

function selectImportFile(file) {
  const isXlsx = file.name.toLowerCase().endsWith('.xlsx')
  if (!isXlsx) {
    message.error('请选择 .xlsx 格式的 Excel 文件')
    return Upload.LIST_IGNORE
  }
  importState.file = file
  importState.fileList = [file]
  return false
}

function removeImportFile() {
  importState.file = null
  importState.fileList = []
  return true
}

function resetImportFile() {
  importState.step = 0
  importState.rows = []
  importState.summary = { total: 0, valid: 0, invalid: 0 }
}

async function previewImport() {
  if (!importState.file) return
  importState.loading = true
  try {
    const result = await userAdminApi.previewImport(importState.file)
    applyImportResult(result)
    importState.step = 1
  } catch (error) {
    message.error(error.message || 'Excel 预检失败')
  } finally {
    importState.loading = false
  }
}

async function confirmImportUsers() {
  importState.loading = true
  try {
    const result = await userAdminApi.importUsers(importState.file)
    applyImportResult(result)
    importState.rows = importState.rows.map((row) =>
      isImportRowSuccess(row) ? { ...row, status: 'created' } : row
    )
    importState.createdCount = Number(result.created_count ?? result.summary?.valid ?? 0)
    importState.step = 2
    Object.keys(userRolesById).forEach((key) => delete userRolesById[key])
    await fetchUsers()
  } catch (error) {
    message.error(error.message || '批量导入用户失败')
  } finally {
    importState.loading = false
  }
}

function applyImportResult(result) {
  const rows = Array.isArray(result?.rows) ? result.rows : []
  importState.rows = rows.map((row, index) => ({
    row: row.row ?? index + 2,
    status: row.status || 'invalid',
    errors: Array.isArray(row.errors) ? row.errors : row.errors ? [String(row.errors)] : [],
    uid: row.uid || '',
    username: row.username || '',
    phone_number: row.phone_number || '',
    department_id: row.department_id ?? null,
    department_name: row.department_name || '',
    role_ids: Array.isArray(row.role_ids) ? row.role_ids : [],
    role_names: Array.isArray(row.role_names) ? row.role_names : []
  }))
  importState.summary = {
    total: Number(result?.summary?.total ?? rows.length),
    valid: Number(result?.summary?.valid ?? rows.filter(isImportRowSuccess).length),
    invalid: Number(
      result?.summary?.invalid ?? rows.filter((row) => !isImportRowSuccess(row)).length
    )
  }
}

async function downloadImportTemplate() {
  templateDownloading.value = true
  try {
    const response = await userAdminApi.getImportTemplate()
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') || ''
    const filename = decodeURIComponent(
      disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)?.[1] ||
        'openzetc-users-template.xlsx'
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    message.error(error.message || '下载模板失败')
  } finally {
    templateDownloading.value = false
  }
}

function validatePhoneNumber(phone) {
  return !phone || /^1[3-9]\d{9}$/.test(phone)
}

function formatTime(time) {
  return time ? formatDateTime(time) : '-'
}

function getUserDefaultAvatarSrc(user) {
  return user.uid ? generatePixelAvatar(user.uid) : ''
}

function legacyRoleLabel(role) {
  return { superadmin: '超级管理员', admin: '管理员', user: '普通用户' }[role] || role || '普通用户'
}

function departmentName(departmentId) {
  return (
    departmentManagement.departments.find((item) => Number(item.id) === Number(departmentId))
      ?.name || '部门角色'
  )
}

function isImportRowSuccess(row) {
  return ['valid', 'success', 'created', 'imported'].includes(row.status)
}

function importRowStatusLabel(row) {
  if (row.status === 'valid') return '可导入'
  if (['success', 'created', 'imported'].includes(row.status)) return '已创建'
  return '异常'
}

onMounted(async () => {
  await Promise.all([fetchUsers(), fetchDepartments(), fetchRoles()])
  await loadVisibleUserRoles()
})
</script>

<style lang="less" scoped>
.user-management {
  color: var(--gray-900);

  .header-section {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  .header-content {
    min-width: 0;
  }

  .section-title {
    margin: 12px 0 8px;
    color: var(--gray-900);
    font-size: 16px;
    font-weight: 600;
    line-height: 1.4;
  }

  .section-description {
    margin: 0;
    color: var(--gray-600);
    font-size: 13px;
    line-height: 1.5;
  }

  .header-actions,
  .filter-section,
  .batch-actions,
  .batch-action-group,
  .selection-summary {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .header-actions {
    flex-shrink: 0;
  }

  .refresh-btn,
  .row-more-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .refresh-btn {
    width: 32px;
    height: 32px;
    padding: 0;
  }

  .filter-section {
    margin-bottom: 12px;
  }

  .search-input {
    width: 320px;
  }

  .filter-select {
    width: 150px;
  }

  .result-count {
    margin-left: auto;
    color: var(--gray-500);
    font-size: 12px;
  }

  .batch-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
    padding: 10px 12px;
    border: 1px solid var(--main-100);
    border-radius: 8px;
    background: var(--main-30);
  }

  .selection-summary {
    flex-shrink: 0;
    color: var(--main-700);
    font-size: 13px;

    :deep(.ant-btn-link) {
      height: 24px;
      padding: 0 4px;
    }
  }

  .batch-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .batch-action-group {
    color: var(--gray-600);
  }

  .batch-department-select {
    width: 150px;
  }

  .batch-mode-select {
    width: 112px;
  }

  .batch-role-select {
    width: 230px;
  }

  .content-section {
    overflow: hidden;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);
  }

  .error-message {
    margin: 12px;
  }

  .user-table {
    :deep(.ant-table) {
      color: var(--gray-800);
      background: var(--gray-0);
    }

    :deep(.ant-table-thead > tr > th) {
      padding-top: 10px;
      padding-bottom: 10px;
      border-color: var(--gray-150);
      background: var(--gray-25);
      color: var(--gray-700);
      font-size: 12px;
      font-weight: 600;
    }

    :deep(.ant-table-tbody > tr > td) {
      padding-top: 10px;
      padding-bottom: 10px;
      border-color: var(--gray-100);
      font-size: 13px;
    }

    :deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
      background: var(--main-30);
    }

    :deep(.ant-pagination) {
      margin-right: 12px;
    }
  }

  .user-cell,
  .role-tags,
  .department-tag,
  .lucide-menu-item {
    display: flex;
    align-items: center;
  }

  .user-cell {
    gap: 10px;
  }

  .user-identity {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 2px;
  }

  .user-name {
    overflow: hidden;
    color: var(--gray-900);
    font-size: 13px;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .user-uid,
  .muted-text {
    color: var(--gray-500);
    font-size: 12px;
  }

  .user-uid,
  .phone-text {
    font-family: Monaco, Consolas, monospace;
  }

  .department-tag,
  .role-tags {
    gap: 4px;
  }

  .department-tag {
    margin: 0;
    border-color: var(--main-100);
    background: var(--main-30);
    color: var(--main-700);
  }

  .legacy-role-tag,
  .rbac-role-tag,
  .more-role-tag {
    margin: 0;
    border-color: var(--gray-150);
    background: var(--gray-50);
    color: var(--gray-700);
  }

  .legacy-role-superadmin {
    border-color: var(--color-error-50);
    background: var(--color-error-50);
    color: var(--color-error-700);
  }

  .legacy-role-admin {
    border-color: var(--color-info-50);
    background: var(--color-info-50);
    color: var(--color-info-700);
  }

  .legacy-role-user {
    border-color: var(--color-success-50);
    background: var(--color-success-50);
    color: var(--color-success-700);
  }

  .role-tags {
    flex-wrap: wrap;
  }

  .more-role-tag {
    color: var(--main-700);
  }

  .time-text {
    color: var(--gray-600);
    font-size: 12px;
  }

  .row-more-button {
    width: 28px;
    height: 28px;
    padding: 0;
    color: var(--gray-600);
  }

  .lucide-menu-item {
    gap: 7px;
  }
}

.user-modal {
  :deep(.ant-modal-header) {
    border-bottom: 1px solid var(--gray-150);
  }

  .form-item {
    margin-bottom: 16px;
  }

  .error-text,
  .help-text {
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.4;
  }

  .error-text {
    color: var(--color-error-700);
  }

  .help-text {
    color: var(--gray-600);
  }

  .password-toggle {
    margin-bottom: 16px;
    padding: 10px 12px;
    border: 1px solid var(--gray-100);
    border-radius: 8px;
    background: var(--gray-25);
  }
}

.import-user-modal {
  .import-steps {
    margin-bottom: 24px;
  }

  .import-select-panel,
  .import-review-panel {
    min-height: 340px;
  }

  .import-dragger {
    display: block;
    margin-top: 16px;

    :deep(.ant-upload-drag) {
      border-color: var(--gray-200);
      background: var(--gray-25);
    }

    :deep(.ant-upload-drag-icon) {
      display: flex;
      justify-content: center;
      margin-bottom: 10px;
      color: var(--main-600);
    }

    :deep(.ant-upload-text) {
      color: var(--gray-900);
      font-size: 14px;
    }

    :deep(.ant-upload-hint) {
      color: var(--gray-500);
      font-size: 12px;
    }
  }

  .template-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    padding-left: 0;
  }

  .import-summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-bottom: 12px;
  }

  .summary-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-25);
    color: var(--gray-600);
    font-size: 12px;

    strong {
      color: var(--gray-900);
      font-size: 20px;
    }

    &.success {
      border-color: var(--color-success-50);
      background: var(--color-success-50);

      strong {
        color: var(--color-success-700);
      }
    }

    &.error {
      border-color: var(--color-error-50);
      background: var(--color-error-50);

      strong {
        color: var(--color-error-700);
      }
    }
  }

  .import-alert {
    margin-bottom: 12px;
  }

  .import-preview-table {
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    overflow: hidden;
  }

  .row-status {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--color-error-700);
    font-size: 12px;

    &.success {
      color: var(--color-success-700);
    }
  }

  .import-account-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong {
      color: var(--gray-900);
    }

    span {
      color: var(--gray-500);
      font-family: Monaco, Consolas, monospace;
      font-size: 11px;
    }
  }

  .import-errors {
    color: var(--color-error-700);
    font-size: 12px;
  }

  .muted-text {
    color: var(--gray-500);
  }

  .import-footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .user-management {
    .header-section,
    .batch-toolbar {
      align-items: stretch;
      flex-direction: column;
    }

    .header-actions,
    .batch-actions {
      justify-content: flex-start;
    }

    .selection-summary {
      justify-content: space-between;
    }
  }
}

@media (max-width: 720px) {
  .user-management {
    .header-actions,
    .filter-section,
    .batch-actions,
    .batch-action-group {
      align-items: stretch;
      flex-direction: column;
    }

    .header-actions :deep(.ant-btn),
    .search-input,
    .filter-select,
    .batch-department-select,
    .batch-mode-select,
    .batch-role-select {
      width: 100%;
    }

    .result-count {
      margin-left: 0;
    }

    .refresh-btn {
      width: 100%;
    }
  }

  .import-user-modal .import-summary {
    grid-template-columns: 1fr;
  }
}
</style>

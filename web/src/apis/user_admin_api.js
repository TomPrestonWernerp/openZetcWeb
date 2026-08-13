import { apiGet, apiPost, apiPut } from './base'

const USER_BASE_URL = '/api/auth/users'
const RBAC_BASE_URL = '/api/rbac'

export const userAdminApi = {
  batchUpdateDepartment(userIds, departmentId) {
    return apiPut(`${USER_BASE_URL}/batch/department`, {
      user_ids: userIds,
      department_id: departmentId
    })
  },

  batchUpdateRoles(userIds, roleIds, mode) {
    return apiPut(`${RBAC_BASE_URL}/users/batch/roles`, {
      user_ids: userIds,
      role_ids: roleIds,
      mode
    })
  },

  getRoles() {
    return apiGet(`${RBAC_BASE_URL}/roles`)
  },

  getUserRoles(userId) {
    return apiGet(`${RBAC_BASE_URL}/users/${userId}/roles`)
  },

  getImportTemplate() {
    return apiGet(`${USER_BASE_URL}/import-template`, {}, true, 'blob')
  },

  previewImport(file) {
    const formData = new FormData()
    formData.append('file', file)
    return apiPost(`${USER_BASE_URL}/import/preview`, formData)
  },

  importUsers(file) {
    const formData = new FormData()
    formData.append('file', file)
    return apiPost(`${USER_BASE_URL}/import`, formData)
  }
}

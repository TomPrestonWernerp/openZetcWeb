import { apiDelete, apiGet, apiPost, apiPut } from './base'

const BASE_URL = '/api/rbac'

export const rbacApi = {
  getMyAccess() {
    return apiGet(`${BASE_URL}/me`)
  },
  getPermissions() {
    return apiGet(`${BASE_URL}/permissions`)
  },
  getRoles() {
    return apiGet(`${BASE_URL}/roles`)
  },
  createRole(data) {
    return apiPost(`${BASE_URL}/roles`, data)
  },
  updateRole(roleId, data) {
    return apiPut(`${BASE_URL}/roles/${roleId}`, data)
  },
  deleteRole(roleId) {
    return apiDelete(`${BASE_URL}/roles/${roleId}`)
  },
  getUserRoles(userId) {
    return apiGet(`${BASE_URL}/users/${userId}/roles`)
  },
  updateUserRoles(userId, roleIds) {
    return apiPut(`${BASE_URL}/users/${userId}/roles`, { role_ids: roleIds })
  }
}

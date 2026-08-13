/**
 * 部门管理 API
 */

import { apiGet, apiPost, apiPut, apiDelete } from './base'

const BASE_URL = '/api/departments'

/**
 * 获取部门列表（普通管理员可访问）
 * @returns {Promise<Array>} 部门列表
 */
export const getDepartments = () => {
  return apiGet(BASE_URL)
}

/**
 * 获取部门详情
 * @param {number} departmentId - 部门ID
 * @returns {Promise<Object>} 部门详情
 */
export const getDepartment = (departmentId) => {
  return apiGet(`${BASE_URL}/${departmentId}`)
}

/**
 * 获取部门成员
 * @param {number} departmentId - 部门ID
 * @returns {Promise<Array>} 部门成员列表
 */
export const getDepartmentUsers = (departmentId) => {
  return apiGet(`${BASE_URL}/${departmentId}/users`)
}

/**
 * 批量调整用户所属部门
 * @param {Array<number>} userIds - 用户ID列表
 * @param {number} departmentId - 目标部门ID
 * @returns {Promise<Object>} 批量操作结果
 */
export const batchUpdateUserDepartment = (userIds, departmentId) => {
  return apiPut('/api/auth/users/batch/department', {
    user_ids: userIds,
    department_id: departmentId
  })
}

/**
 * 创建部门
 * @param {Object} data - 部门数据
 * @param {string} data.name - 部门名称
 * @param {string} [data.description] - 部门描述
 * @returns {Promise<Object>} 创建的部门
 */
export const createDepartment = (data) => {
  return apiPost(BASE_URL, data)
}

/**
 * 更新部门
 * @param {number} departmentId - 部门ID
 * @param {Object} data - 部门数据
 * @param {string} [data.name] - 部门名称
 * @param {string} [data.description] - 部门描述
 * @returns {Promise<Object>} 更新后的部门
 */
export const updateDepartment = (departmentId, data) => {
  return apiPut(`${BASE_URL}/${departmentId}`, data)
}

/**
 * 删除部门
 * @param {number} departmentId - 部门ID
 * @returns {Promise<Object>} 删除结果
 */
export const deleteDepartment = (departmentId) => {
  return apiDelete(`${BASE_URL}/${departmentId}`)
}

export const getRolePermissions = (departmentId) => {
  return apiGet(`${BASE_URL}/${departmentId}/role-permissions`)
}

export const updateRolePermissions = (departmentId, role, permissions) => {
  return apiPut(`${BASE_URL}/${departmentId}/role-permissions`, {
    role,
    permissions
  })
}

export const departmentApi = {
  getDepartments,
  getDepartment,
  getDepartmentUsers,
  batchUpdateUserDepartment,
  createDepartment,
  updateDepartment,
  deleteDepartment,
  getRolePermissions,
  updateRolePermissions
}

export const RESOURCE_SCOPE_OPTIONS = [
  { value: 'global', label: '全局' },
  { value: 'department', label: '部门' },
  { value: 'user', label: '个人' }
]

export const RESOURCE_SCOPE_META = {
  global: { label: '全局', color: 'blue' },
  department: { label: '部门', color: 'purple' },
  user: { label: '个人', color: 'green' }
}

export const getResourceScope = (resource, fallback = 'global') => {
  const accessLevel = resource?.share_config?.access_level
  return RESOURCE_SCOPE_META[accessLevel] ? accessLevel : fallback
}

export const getResourceScopeMeta = (resource, fallback = 'global') =>
  RESOURCE_SCOPE_META[getResourceScope(resource, fallback)]

export const matchesResourceScope = (resource, selectedScope, fallback = 'global') =>
  !selectedScope || getResourceScope(resource, fallback) === selectedScope

export const groupResourcesByScope = (resources, fallback = 'global') =>
  RESOURCE_SCOPE_OPTIONS.map((option) => ({
    ...option,
    resources: resources.filter((resource) => getResourceScope(resource, fallback) === option.value)
  })).filter((group) => group.resources.length)

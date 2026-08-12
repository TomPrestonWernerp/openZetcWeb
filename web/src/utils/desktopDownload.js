export const DESKTOP_RELEASE_API_URL =
  'https://api.github.com/repos/TomPrestonWernerp/openZetcX/releases/latest'
export const DESKTOP_RELEASE_PAGE_URL =
  'https://github.com/TomPrestonWernerp/openZetcX/releases/latest'

const normalizeArchitecture = (architecture, bitness = '') => {
  const value = `${architecture || ''} ${bitness || ''}`.toLowerCase()
  if (/arm64|aarch64/.test(value)) return 'arm64'
  if (/x86_64|x64|amd64|x86.*64|64.*x86/.test(value)) return 'x64'
  return 'unknown'
}

const normalizePlatform = (platform, userAgent = '') => {
  const value = `${platform || ''} ${userAgent || ''}`.toLowerCase()
  if (/windows|win32|win64/.test(value)) return 'windows'
  if (/macos|macintosh|macintel/.test(value)) return 'macos'
  if (/linux|x11/.test(value)) return 'linux'
  return 'unknown'
}

export const detectDesktopTarget = async (navigatorLike = navigator) => {
  const userAgentData = navigatorLike.userAgentData
  let highEntropy = {}

  if (userAgentData?.getHighEntropyValues) {
    try {
      highEntropy = await userAgentData.getHighEntropyValues(['architecture', 'bitness', 'platform'])
    } catch {
      highEntropy = {}
    }
  }

  const platform = normalizePlatform(
    highEntropy.platform || userAgentData?.platform || navigatorLike.platform,
    navigatorLike.userAgent
  )
  const architecture = normalizeArchitecture(
    highEntropy.architecture || navigatorLike.userAgent,
    highEntropy.bitness
  )

  return { platform, architecture }
}

export const toDesktopPackages = (assets = []) =>
  assets.flatMap((asset) => {
    const name = asset?.name || ''
    const url = asset?.browser_download_url || ''
    if (!url) return []

    if (/Windows-x64\.exe$/i.test(name)) {
      return [{ id: 'windows-x64', platform: 'windows', architecture: 'x64', label: 'Windows', detail: '64 位安装程序', name, url }]
    }
    if (/macOS-arm64\.dmg$/i.test(name)) {
      return [{ id: 'macos-arm64', platform: 'macos', architecture: 'arm64', label: 'macOS', detail: 'Apple 芯片', name, url }]
    }
    if (/macOS-x64\.dmg$/i.test(name)) {
      return [{ id: 'macos-x64', platform: 'macos', architecture: 'x64', label: 'macOS', detail: 'Intel 芯片', name, url }]
    }
    return []
  })

export const findRecommendedPackage = (packages, target) => {
  const matches = packages.filter(
    (item) => item.platform === target.platform && item.architecture === target.architecture
  )
  return matches[0] || null
}

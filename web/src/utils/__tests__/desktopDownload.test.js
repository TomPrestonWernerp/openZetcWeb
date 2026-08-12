import assert from 'node:assert/strict'

import {
  detectDesktopTarget,
  findRecommendedPackage,
  toDesktopPackages
} from '../desktopDownload.js'

const windows = await detectDesktopTarget({
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
  userAgentData: {
    platform: 'Windows',
    getHighEntropyValues: async () => ({ architecture: 'x86', bitness: '64', platform: 'Windows' })
  }
})
assert.deepEqual(windows, { platform: 'windows', architecture: 'x64' })

const appleSilicon = await detectDesktopTarget({
  platform: 'MacIntel',
  userAgent: 'Mozilla/5.0 (Macintosh)',
  userAgentData: {
    platform: 'macOS',
    getHighEntropyValues: async () => ({ architecture: 'arm64', bitness: '64', platform: 'macOS' })
  }
})
assert.deepEqual(appleSilicon, { platform: 'macos', architecture: 'arm64' })

const packages = toDesktopPackages([
  { name: 'openZetcX-0.6.2-Windows-x64.exe', browser_download_url: 'https://example.test/win' },
  { name: 'openZetcX-0.6.2-macOS-arm64.dmg', browser_download_url: 'https://example.test/mac-arm' },
  { name: 'openZetcX-0.6.2-macOS-x64.dmg', browser_download_url: 'https://example.test/mac-x64' },
  { name: 'openZetcX-0.6.2-Linux-x86_64.AppImage', browser_download_url: 'https://example.test/linux' },
  { name: 'openZetcX-0.6.2-Linux-amd64.deb', browser_download_url: 'https://example.test/linux-deb' },
  { name: 'latest.yml', browser_download_url: 'https://example.test/latest' }
])

assert.equal(packages.length, 3)
assert.equal(packages.some((item) => item.platform === 'linux'), false)
assert.equal(findRecommendedPackage(packages, windows)?.url, 'https://example.test/win')
assert.equal(findRecommendedPackage(packages, appleSilicon)?.url, 'https://example.test/mac-arm')
assert.equal(
  findRecommendedPackage(packages, { platform: 'macos', architecture: 'unknown' }),
  null
)

console.log('desktopDownload: all assertions passed')

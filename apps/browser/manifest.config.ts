import { defineManifest } from '@crxjs/vite-plugin'
import pkg from './package.json'

export default defineManifest({
  manifest_version: 3,
  name: 'Gongzuo — Job Application Autofill',
  short_name: 'Gongzuo',
  version: pkg.version,
  description:
    'One-click auto-fill for job applications. Saves your profile locally and fills Greenhouse, Lever, Workday and most other forms.',
  icons: {
    16: 'icons/icon16.png',
    32: 'icons/icon32.png',
    48: 'icons/icon48.png',
    128: 'icons/icon128.png',
  },
  action: {
    default_popup: 'index.html',
    default_title: 'Gongzuo — Fill this application',
    default_icon: {
      16: 'icons/icon16.png',
      32: 'icons/icon32.png',
      48: 'icons/icon48.png',
      128: 'icons/icon128.png',
    },
  },
  options_page: 'src/options/index.html',
  background: {
    service_worker: 'src/background/background.ts',
    type: 'module',
  },
  content_scripts: [
    {
      matches: ['http://*/*', 'https://*/*'],
      js: ['src/content/content.ts'],
      run_at: 'document_idle',
      all_frames: true,
    },
  ],
  // Deliberately minimal: no host_permissions beyond the content script
  // matches, no tabs/scripting/activeTab — nothing here reads browsing data.
  permissions: ['storage', 'unlimitedStorage'],
})

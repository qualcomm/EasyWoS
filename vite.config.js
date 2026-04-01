/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright (c) 2026 Qualcomm Technologies, Inc.
 * All Rights Reserved.
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8881',
        changeOrigin: true,
      }
    },
  },
})
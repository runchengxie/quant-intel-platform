import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

export default defineConfig({
  site: 'https://runchengxie.github.io',
  base: '/quant-intel-pages',
  outDir: process.env.ASTRO_OUT_DIR || './dist',
  integrations: [react()],
});

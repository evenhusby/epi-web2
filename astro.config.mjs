import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://epiport.org',
  i18n: {
    locales: ['no', 'en'],
    defaultLocale: 'en',
    routing: {
      prefixDefaultLocale: false,
    },
  },
});

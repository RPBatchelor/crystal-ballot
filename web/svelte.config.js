import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// Fully static: every page is prerendered from the model's published JSON.
		adapter: adapter({ pages: 'build', assets: 'build', fallback: '404.html', strict: true })
	}
};

export default config;

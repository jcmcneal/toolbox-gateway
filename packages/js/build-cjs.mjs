/**
 * Build script: produce CJS (.cjs) variants alongside ESM (.js) output.
 * Runs after `tsc -p tsconfig.esm.json` produces dist/*.js.
 */
import * as esbuild from 'esbuild';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const srcDir = resolve(__dirname, 'src');
const distDir = resolve(__dirname, 'dist');

// Entry points that have CJS exports
const entries = ['index', 'schema', 'mcp', 'sqlite-store'];

for (const entry of entries) {
  const srcFile = resolve(srcDir, `${entry}.ts`);

  await esbuild.build({
    entryPoints: [srcFile],
    outfile: resolve(distDir, `${entry}.cjs`),
    format: 'cjs',
    platform: 'node',
    target: 'node18',
    bundle: true,
    external: ['better-sqlite3', 'zod', 'crypto'],
    sourcemap: false,
  });
}

console.log('CJS builds complete.');

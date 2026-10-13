#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const entrypoint = path.basename(process.argv[1]);
const name = ({ 'npm-cli.js': 'npm', 'npx-cli.js': 'npx' })[entrypoint] || entrypoint;
const args = process.argv.slice(2);
const env = Object.fromEntries(['ARTIFACTS_ACCESSTOKEN', 'VSS_NUGET_ACCESSTOKEN', 'VSS_NUGET_URI_PREFIXES'].map(key => [key, process.env[key] ?? null]));
fs.appendFileSync(process.env.TEST_LOG, JSON.stringify({ command: name, args, env }) + '\n');
if (name === 'az') {
  console.log(process.env.TEST_AZ_TOKEN ?? 'fixture-token');
  process.exit(Number(process.env.TEST_AZ_STATUS || 0));
}
if (process.env.TEST_BLOCK === 'yes') {
  process.on('SIGINT', () => process.exit(42));
  process.on('SIGTERM', () => process.exit(42));
  setInterval(() => {}, 1000);
} else if (process.env.TEST_IO === 'yes') {
  process.stdout.write('manager stdout\n');
  process.stderr.write('manager stderr\n');
  process.stdin.pipe(process.stdout);
  process.stdin.on('end', () => { process.exitCode = Number(process.env.TEST_MANAGER_STATUS || 0); });
} else process.exitCode = Number(process.env.TEST_MANAGER_STATUS || 0);

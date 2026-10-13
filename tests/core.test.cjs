'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { resolveShim } = require('../functions/az-auth-core.cjs');

test('Node shims preserve every argument without invoking cmd.exe', () => {
  const args = ['', 'a b', '&whoami', '%PATH%', '!', 'line\nbreak', 'a"b', '^', '|', '<', '>'];
  for (const [script, name] of [
    ['npm/bin/npm-cli.js', 'npm'],
    ['npm/bin/npx-cli.js', 'npx'],
    ['pnpm/bin/pnpm.cjs', 'pnpm'],
    ['yarn/bin/yarn.js', 'yarn'],
    ['corepack/dist/corepack.js', 'corepack'],
    ['corepack/dist/pnpm.js', 'pnpm'],
    ['corepack/dist/pnpx.js', 'pnpx'],
    ['@microsoft/rush/bin/rush', 'rush'],
    ['@microsoft/rush/bin/rush-pnpm', 'rush-pnpm'],
  ]) {
    const relative = `node_modules\\${script.replaceAll('/', '\\')}`;
    const shim = `@echo off\r\n"%dp0%\\node.exe" "%dp0%\\${relative}" %*\r\n`;
    assert.deepEqual(resolveShim(`C:\\tools\\${name}.cmd`, shim, args), {
      file: 'node', args: [`C:\\tools\\${relative}`, ...args],
    });
  }
});

test('Azure CLI shim invokes Python with an argument array', () => {
  assert.deepEqual(resolveShim('C:\\azure\\bin\\az.cmd', '"%~dp0..\\python.exe" -IBm azure.cli %*', ['account', '&']), {
    file: 'C:\\azure\\python.exe', args: ['-IBm', 'azure.cli', 'account', '&'],
  });
});

test('Unknown batch and PowerShell launchers fail closed', () => {
  for (const [file, content] of [
    ['C:\\tools\\npm.cmd', 'echo arbitrary %*'],
    ['C:\\tools\\npm.cmd', '"%dp0%\\node.exe" "%dp0%\\arbitrary.js" %*'],
    ['C:\\tools\\npm.ps1', '& node npm-cli.js $args'],
    ['C:\\tools\\npm.ps1', '"%dp0%\\node.exe" "%dp0%\\node_modules\\npm\\bin\\npm-cli.js" %*'],
    ['C:\\tools\\npm.bat', '"%dp0%\\node.exe" "%dp0%\\node_modules\\npm\\bin\\npm-cli.js" %*'],
    ['C:\\tools\\other.cmd', '"%~dp0..\\python.exe" -IBm azure.cli %*'],
  ]) {
    assert.throws(() => resolveShim(file, content, ['&']), /Unsupported Windows launcher/);
  }
});

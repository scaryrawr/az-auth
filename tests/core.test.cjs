'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { classify, resolveShim } = require('../functions/az-auth-core.cjs');

test('npm typo aliases and case-insensitive NuGet actions retain registry policy', () => {
  for (const alias of ['isnta', 'isntal']) {
    assert.equal(classify('npm', [alias]).registry, true);
    assert.equal(classify('corepack', ['npm', alias]).registry, true);
    assert.equal(classify('npm', ['run', alias]).registry, false);
  }
  for (const action of ['Restore', 'INSTALL', 'uPdAtE']) {
    assert.equal(classify('nuget', [action]).registry, true);
    assert.equal(classify('nuget', [action, '-Help']).registry, false);
  }
  assert.equal(classify('npm', ['INSTALL']).registry, false);
});

test('Short value options follow their manager rather than consuming npm actions', () => {
  for (const flag of ['-s', '-f']) {
    assert.equal(classify('npm', [flag, 'install']).registry, true);
    assert.equal(classify('npm', [flag, 'run', 'install']).registry, false);
    assert.equal(classify('dotnet', [flag, '--help', 'restore']).registry, true);
  }
  assert.equal(classify('nuget', ['-Source', '--help', 'restore']).registry, true);
});

test('Dotnet no-build skips implicit restore only for commands that support it', () => {
  for (const action of ['test', 'run', 'pack', 'publish']) {
    assert.equal(classify('dotnet', [action, '--no-build']).registry, false);
    assert.equal(classify('dotnet', [action, '--', '--no-build']).registry, true);
    assert.equal(classify('dotnet', [action, '--configuration', '--no-build']).registry, true);
  }
  for (const action of ['restore', 'build']) {
    assert.equal(classify('dotnet', [action, '--no-build']).registry, true);
  }
});

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

  test('Variable-based npm launchers resolve only their known CLI entrypoints', () => {
    const args = ['', 'a b', '&', '%PATH%'];
    for (const manager of ['npm', 'npx']) {
      const variable = manager === 'npm' ? 'NPM_CLI_JS' : 'NPX_CLI_JS';
      const shim = [
        '@ECHO OFF', 'SETLOCAL', 'SET "NODE_EXE=%~dp0\\node.exe"',
        'SET "NPM_PREFIX_JS=%~dp0\\node_modules\\npm\\bin\\npm-prefix.js"',
        `SET "${variable}=%~dp0\\node_modules\\npm\\bin\\${manager}-cli.js"`,
        `"%NODE_EXE%" "%${variable}%" %*`,
      ].join('\r\n');
      assert.deepEqual(resolveShim(`C:\\tools\\${manager}.cmd`, shim, args), {
        file: 'node', args: [`C:\\tools\\node_modules\\npm\\bin\\${manager}-cli.js`, ...args],
        prefix: 'C:\\tools\\node_modules\\npm\\bin\\npm-prefix.js',
      });
      assert.throws(() => resolveShim(`C:\\tools\\${manager}.cmd`,
        shim.replace(`${manager}-cli.js`, 'arbitrary.js'), args), /Unsupported Windows launcher/);
    }
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

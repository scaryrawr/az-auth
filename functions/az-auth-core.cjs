#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');

const RESOURCE = '499b84ac-1321-427f-aa17-267ca6975798';
const PLACEHOLDER = '__fish_completion_placeholder__';
const ACTIONS = {
  npm: 'install i in ins inst insta instal add isnt isntall ci clean-install ic install-clean update up upgrade udpate outdated audit view info show v search s se find ping whoami publish unpublish access dist-tag owner dist-tags stars star unstar',
  pnpm: 'install i add update up upgrade remove rm uninstall un outdated audit view info show search ping whoami publish unpublish dist-tag owner fetch patch import dlx',
  yarn: 'install i add up upgrade upgrade-interactive remove outdated audit info publish tag owner dlx',
  'yarn-npm': 'audit info publish whoami login logout tag',
  bun: 'install i add a update remove rm uninstall publish outdated x',
  rush: 'install update add',
  dotnet: 'restore build test run pack publish',
  nuget: 'restore install update',
};
const MANAGERS = 'npm npx pnpm pnpx pn yarn bun corepack rush rush-pnpm dotnet nuget';
const Decision = Object.freeze({ pass: 'pass', token: 'token', placeholder: 'placeholder' });
const contains = (list, word) => (list || '').split(/\s+/).includes(word);
const exists = file => Boolean(file) && fs.existsSync(file);
const relative = (cwd, file) => file ? path.resolve(cwd, file) : '';
const scalar = value => value.trim().replace(/^["']|["']$/g, '');

function valueOption(manager, action, arg) {
  if (arg.includes('=')) return false;
  if (manager === 'nuget') return contains('-configfile -source', arg.toLowerCase());
  return contains('-C --dir --cwd --prefix --filter --filter-prod -F --registry --userconfig --globalconfig --cache --config --store-dir --virtual-store-dir --modules-dir --use-node-version --network-concurrency --child-concurrency --reporter --loglevel --otp --tag --access --scope --from --include --exclude --package --configfile --source -s --project --configuration -c --framework -f --runtime --verbosity', arg) ||
    (manager === 'dotnet' && arg === '-v') ||
    (arg.startsWith('--@') && arg.endsWith(':registry')) ||
    (manager === 'npm' && contains('-w --workspace', arg)) ||
    (arg === '-p' && (contains('npx pnpx', manager) || action === 'dlx'));
}

function help(manager, arg) {
  if (manager === 'dotnet' && arg === '-v') return false;
  return contains('-h --help -v --version -Help', arg) ||
    (manager === 'nuget' && arg.toLowerCase() === '-help');
}

function classify(manager, args) {
  if (contains('pn rush-pnpm', manager)) manager = 'pnpm';
  const result = { manager, name: '', registry: false };
  let action = '', rest = [], local = false;
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--') {
      action = args[i + 1] || '';
      rest = args.slice(i + 2);
      break;
    }
    if (help(manager, arg)) return result;
    if ((arg === '--no-install' && contains('npx bun', manager)) ||
        (manager === 'npx' && contains('--no --yes=false', arg))) local = true;
    if (valueOption(manager, '', arg)) i++;
    else if (!arg.startsWith('-')) {
      action = arg;
      rest = args.slice(i + 1);
      break;
    }
  }
  if (manager === 'corepack') {
    const delegate = action.split('@')[0];
    return contains('npm npx pnpm pnpx yarn', delegate) ? classify(delegate, rest) : result;
  }
  if (manager === 'pnpm') {
    if (contains('recursive r', action)) return classify(manager, rest);
    if (action === 'store' && rest[0] === 'add') action = 'add';
  }
  if (manager === 'yarn') {
    if (action === 'npm') return classify('yarn-npm', rest);
    if (action === 'workspace' && rest.length >= 2) return classify(manager, rest.slice(1));
    if (action === 'workspaces' && rest[0] === 'foreach') return classify(manager, rest.slice(1));
  }
  if (!action && contains('pnpm yarn', manager)) action = 'install';
  result.name = action;
  const runner = contains('npx pnpx', manager) || contains('dlx x', action);
  if (contains('npx pnpx', manager)) {
    result.registry = args.length > 0;
    rest = [];
  } else result.registry = contains(ACTIONS[manager], action) && action !== '';
  for (let i = 0; i < rest.length; i++) {
    const arg = rest[i];
    if (arg === '--') break;
    if (help(manager, arg) || (manager === 'dotnet' && arg === '--no-restore')) {
      result.registry = false;
      return result;
    }
    if (manager === 'bun' && action === 'x' && arg === '--no-install') local = true;
    if (valueOption(manager, action, arg)) i++;
    else if (runner && !arg.startsWith('-')) break;
  }
  if (local && (manager !== 'bun' || action === 'x')) result.registry = false;
  return result;
}

function readConfig(file, required = false) {
  if (!file) return '';
  let bytes;
  try {
    bytes = fs.readFileSync(file);
  } catch (error) {
    if (error.code === 'ENOENT' && !required) return '';
    throw new Error(`Cannot read configuration ${file}.`);
  }
  if (bytes.length > 1024 * 1024) throw new Error(`Configuration ${file} exceeds the supported 1 MiB limit.`);
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return bytes.subarray(2).toString('utf16le');
  return bytes.toString('utf8').replace(/^\uFEFF/, '');
}

function readRegistry(config, format, file) {
  let section = '', context = 'default';
  for (const rawLine of readConfig(file).split(/\r?\n/)) {
    const raw = rawLine.replace(/\s+[;#].*$/, '');
    const line = raw.trim();
    if (!line || /^[#;]/.test(line)) continue;
    if (format === 'npmrc') {
      const match = line.match(/^([^=]+)=(.*)$/);
      if (!match) continue;
      const key = match[1].trim(), value = scalar(match[2]);
      if (key === 'registry') config.entries.set('registry:default', value);
      else if (key.startsWith('@') && key.endsWith(':registry')) config.entries.set(`registry:${key.slice(0, -9)}`, value);
      else if (key.startsWith('//') && key.endsWith(':_authToken')) config.entries.set(`auth:${key.slice(0, -11)}`, value === '${ARTIFACTS_ACCESSTOKEN}');
    } else if (format === 'yarn') {
      const match = raw.match(/^(\s*)([^:]+):\s*(.*?)\s*$/);
      if (!match) continue;
      const indent = match[1].length, key = scalar(match[2]), value = scalar(match[3]);
      if (indent === 0) {
        section = '';
        context = 'default';
        if (contains('npmScopes npmRegistries', key)) {
          section = key;
          continue;
        }
      } else if (indent === 2 && section) {
        context = section === 'npmScopes' ? `@${key}` : scalar(line.slice(0, -1));
        continue;
      }
      if (key === 'npmRegistryServer') config.entries.set(`registry:${context}`, value);
      else if (key === 'npmAuthToken') {
        const reference = /^\$\{ARTIFACTS_ACCESSTOKEN([:-][^}]*)?\}$/.test(value);
        config.placeholder ||= reference;
        config.entries.set(`${section === 'npmRegistries' ? 'auth' : 'token'}:${context}`, reference);
      }
    } else if (format === 'bun') {
      if (line.startsWith('[')) {
        const end = line.indexOf(']');
        if (end !== -1) {
          section = line.slice(1, end);
          context = section.startsWith('install.scopes.') ? `@${scalar(section.slice(15)).replace(/^@/, '')}` : 'default';
        }
        continue;
      }
      const match = line.match(/^([^=]+)=(.*)$/);
      if (!match || !section.startsWith('install')) continue;
      const key = scalar(match[1]), value = scalar(match[2]);
      if (section === 'install.scopes') context = `@${key.replace(/^@/, '')}`;
      if (value.startsWith('{')) {
        const url = value.match(/(?:url|registry)\s*=\s*["']([^"']+)["']/);
        if (url) config.entries.set(`registry:${context}`, url[1]);
        config.entries.set(`token:${context}`, /token\s*=\s*["']\$(?:\{ARTIFACTS_ACCESSTOKEN\}|ARTIFACTS_ACCESSTOKEN)["']/.test(value));
      } else if (contains('url registry', key)) {
        config.entries.set(`registry:${context}`, value);
        if (key === 'registry' && section === 'install') config.entries.set(`token:${context}`, false);
      } else if (key === 'token') config.entries.set(`token:${context}`, contains('$ARTIFACTS_ACCESSTOKEN ${ARTIFACTS_ACCESSTOKEN}', value));
    }
  }
}

function hasFeed(config) {
  const normalized = value => value.replace(/^https?:/, '').replace(/\/+$/, '') + '/';
  for (const [key, value] of config.entries) {
    if (!key.startsWith('registry:')) continue;
    const context = key.slice(9);
    const token = config.entries.has(`token:${context}`) ? config.entries.get(`token:${context}`) : config.entries.get('token:default');
    if (token) return true;
    let credential = false, specificity = -1;
    for (const [auth, reference] of config.entries) {
      if (!auth.startsWith('auth:')) continue;
      const prefix = normalized(auth.slice(5));
      if (normalized(value).startsWith(prefix) && prefix.length > specificity) {
        credential = reference;
        specificity = prefix.length;
      }
    }
    if (credential) return true;
  }
  return false;
}

function ancestors(directory) {
  const dirs = [];
  for (;;) {
    dirs.push(directory);
    const parent = path.dirname(directory);
    if (parent === directory) return dirs;
    directory = parent;
  }
}

function environment() {
  const env = {};
  for (const [key, value] of Object.entries(process.env)) env[process.platform === 'win32' ? key.toUpperCase() : key] = value;
  env.HOME ||= os.homedir();
  return env;
}

function executable(name, env) {
  const extensions = process.platform === 'win32' ? (env.PATHEXT || '.COM;.EXE;.BAT;.CMD').split(';') : [''];
  for (const directory of (env.PATH || '').split(path.delimiter)) {
    if (!directory) continue;
    for (const extension of extensions) {
      const file = path.resolve(directory, name + extension.toLowerCase());
      try {
        fs.accessSync(file, process.platform === 'win32' ? fs.constants.F_OK : fs.constants.X_OK);
        if (fs.statSync(file).isFile()) return file;
      } catch {}
    }
  }
  throw Object.assign(new Error(`${name} executable not found on PATH.`), { exitCode: 127 });
}

function registryConfiguration(invocation) {
  const { args, env } = invocation;
  let cwd = invocation.cwd, manager = invocation.manager;
  const option = (key, fallback) => env[`npm_config_${key}`] ?? env[`NPM_CONFIG_${key.toUpperCase()}`] ?? fallback;
  let user = option('userconfig', path.join(env.HOME, '.npmrc'));
  let global = option('globalconfig', '');
  let prefix = option('prefix', env.PREFIX || '');
  if (!prefix) {
    try { prefix = path.dirname(path.dirname(executable('node', env))); } catch {}
  }
  let globalMode = option('global', '') === 'true';
  const cli = new Map();
  let state = 'action';
  scan: for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--') break;
    const at = arg.indexOf('=');
    const key = at === -1 ? arg : arg.slice(0, at);
    let value = at === -1 ? '' : arg.slice(at + 1);
    const isScope = key.startsWith('--@') && key.endsWith(':registry');
    if (contains('-C --dir --cwd --prefix --userconfig --globalconfig --registry', key) || isScope) {
      if (at === -1 && i + 1 < args.length) value = args[++i];
      switch (key) {
        case '-C': case '--dir': case '--cwd': cwd = relative(cwd, value); break;
        case '--prefix':
          prefix = relative(invocation.cwd, value);
          if (manager === 'npm') cwd = prefix;
          break;
        case '--userconfig': user = value; break;
        case '--globalconfig': global = value; break;
        case '--registry': cli.set('registry:default', value); break;
        default: cli.set(`registry:${key.slice(2, -9)}`, value);
      }
    } else if (contains('-g --global --global=true', arg)) globalMode = true;
    else if (arg === '--global=false') globalMode = false;
    else if (valueOption(manager, state, arg)) i++;
    else if (!arg.startsWith('-')) {
      if (manager === 'corepack') manager = arg.split('@')[0];
      else {
        switch (state) {
          case 'action':
            if (contains('npx pnpx', manager)) break scan;
            if (manager === 'yarn' && arg === 'workspace') state = 'workspace-name';
            else if (manager === 'yarn' && arg === 'workspaces') state = 'foreach';
            else if ((contains('pnpm pn', manager) && contains('recursive r', arg)) || (manager === 'yarn' && arg === 'npm')) {}
            else state = contains('run exec x dlx', arg) ? arg : 'targets';
            break;
          case 'workspace-name': state = 'action'; break;
          case 'foreach': state = arg === 'foreach' ? 'action' : 'targets'; break;
          case 'run': case 'exec': case 'x': case 'dlx': break scan;
        }
      }
    }
  }
  if (contains('pn pnpx rush-pnpm', manager)) manager = 'pnpm';
  else if (manager === 'npx') manager = 'npm';
  const dirs = ancestors(cwd);
  let project = dirs.find(dir => exists(path.join(dir, 'package.json')) || exists(path.join(dir, 'node_modules'))) || cwd;
  const workspace = dirs.find(dir => exists(path.join(dir, 'pnpm-workspace.yaml')));
  const rush = dirs.find(dir => exists(path.join(dir, 'rush.json')));
  if (manager === 'pnpm' && workspace) project = workspace;
  if (!global && prefix) global = path.join(prefix, 'etc', 'npmrc');
  const files = [['npmrc', relative(invocation.cwd, global)], ['npmrc', relative(invocation.cwd, user)]];
  if (!globalMode) files.push(['npmrc', path.join(project, '.npmrc')]);
  if (contains('rush rush-pnpm', invocation.manager) && rush) {
    files.push(['npmrc', path.join(rush, 'common/config/rush/.npmrc')], ['npmrc', path.join(rush, 'config/rush/.npmrc')]);
  }
  if (manager === 'yarn') files.push(...dirs.slice().reverse().map(dir => ['yarn', path.join(dir, '.yarnrc.yml')]));
  if (manager === 'bun') files.push(...[path.join(env.HOME, '.bunfig.toml'), path.join(cwd, '.bunfig.toml'), path.join(cwd, 'bunfig.toml')].map(file => ['bun', file]));
  const config = { entries: new Map([['registry:default', 'https://registry.npmjs.org/']]), placeholder: false };
  for (const [format, file] of files) readRegistry(config, format, file);
  for (const variable of ['NPM_CONFIG_REGISTRY', 'npm_config_registry']) {
    if (env[variable] !== undefined) config.entries.set('registry:default', env[variable]);
  }
  for (const [key, value] of cli) config.entries.set(key, value);
  return config;
}

function azureSource(source) {
  try {
    const url = new URL(source);
    return /^https:\/\//i.test(source) && url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash &&
      (url.hostname === 'pkgs.dev.azure.com' || (url.hostname.endsWith('.pkgs.visualstudio.com') && url.hostname !== '.pkgs.visualstudio.com'));
  } catch { return false; }
}

function xmlEntities(value) {
  if (/&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[\da-fA-F]+);)/.test(value)) throw new Error('Unsupported XML entity.');
  return value.replace(/&([^;]+);/g, (_, entity) => {
    const named = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };
    if (named[entity]) return named[entity];
    const code = entity.startsWith('#x') ? parseInt(entity.slice(2), 16) : Number(entity.slice(1));
    if (code <= 0 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) throw new Error('Invalid XML character.');
    return String.fromCodePoint(code);
  });
}

function readNuget(file, sources, disabled, required = false) {
  const xml = readConfig(file, required);
  if (!xml) return;
  const stack = [];
  let offset = 0, root = false, complete = false;
  while (offset < xml.length) {
    if (xml.startsWith('<!--', offset) || xml.startsWith('<?', offset)) {
      const comment = xml.startsWith('<!--', offset);
      const end = xml.indexOf(comment ? '-->' : '?>', offset);
      if (end === -1) throw new Error(`Malformed XML in ${file}.`);
      offset = end + (comment ? 3 : 2);
      continue;
    }
    if (xml[offset] !== '<') {
      const end = xml.indexOf('<', offset);
      const text = xml.slice(offset, end === -1 ? xml.length : end);
      if (!stack.length && text.trim()) throw new Error(`Malformed XML in ${file}.`);
      xmlEntities(text);
      offset = end === -1 ? xml.length : end;
      continue;
    }
    const tag = /<(?:[^"'<>]|"[^"]*"|'[^']*')*>/y;
    tag.lastIndex = offset;
    const match = tag.exec(xml);
    if (!match || /^<!/.test(match[0])) throw new Error(`Unsupported or malformed XML in ${file}. DTD and CDATA are not supported.`);
    offset = tag.lastIndex;
    let body = match[0].slice(1, -1).trim();
    if (body.startsWith('/')) {
      if (stack.pop() !== body.slice(1).trim()) throw new Error(`Mismatched XML tags in ${file}.`);
      if (!stack.length) complete = true;
      continue;
    }
    const selfClosing = body.endsWith('/');
    if (selfClosing) body = body.slice(0, -1).trim();
    const start = body.match(/^([A-Za-z_][\w.:-]*)([\s\S]*)$/);
    if (!start) throw new Error(`Malformed XML tag in ${file}.`);
    const name = start[1], attrs = {};
    let remaining = start[2];
    while (remaining.trim()) {
      const attr = remaining.match(/^\s+([A-Za-z_][\w.:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/);
      if (!attr || Object.hasOwn(attrs, attr[1])) throw new Error(`Malformed XML attributes in ${file}.`);
      attrs[attr[1]] = xmlEntities(attr[2] ?? attr[3]);
      remaining = remaining.slice(attr[0].length);
    }
    if (!stack.length) {
      if (root || complete || name !== 'configuration') throw new Error(`Expected one NuGet configuration root in ${file}.`);
      root = true;
    }
    stack.push(name);
    if (stack.length === 3) {
      const target = stack[1] === 'packageSources' ? sources : stack[1] === 'disabledPackageSources' ? disabled : null;
      if (target) {
        const key = (attrs.key || '').toLowerCase();
        if (name === 'clear') target.clear();
        else if (name === 'remove') target.delete(key);
        else if (name === 'add' && key) target.set(key, (attrs.value || '').trim());
      }
    }
    if (selfClosing) {
      stack.pop();
      if (!stack.length) complete = true;
    }
  }
  if (stack.length || !root || !complete) throw new Error(`Incomplete XML in ${file}.`);
}

function nugetSources(invocation) {
  let explicit = '';
  const overrides = [];
  for (let i = 0; i < invocation.args.length; i++) {
    const arg = invocation.args[i];
    if (arg === '--') break;
    const at = arg.indexOf('='), key = (at === -1 ? arg : arg.slice(0, at)).toLowerCase();
    if (!contains('--configfile -configfile --source -source -s', key)) continue;
    let value = at === -1 ? invocation.args[++i] : arg.slice(at + 1);
    if (value === undefined) throw new Error(`${key} requires a value.`);
    if (contains('--configfile -configfile', key)) explicit = relative(invocation.cwd, value);
    else overrides.push(...value.split(';'));
  }
  const sources = new Map(), disabled = new Map();
  if (explicit) readNuget(explicit, sources, disabled, true);
  else {
    const user = invocation.env.APPDATA ? path.join(invocation.env.APPDATA, 'NuGet/NuGet.Config') : path.join(invocation.env.HOME, '.nuget/NuGet/NuGet.Config');
    readNuget(user, sources, disabled);
    const seen = new Set();
    for (const dir of ancestors(invocation.cwd).reverse()) {
      for (const name of ['NuGet.config', 'nuget.config', 'NuGet.Config']) {
        const file = path.join(dir, name);
        if (!exists(file)) continue;
        const real = fs.realpathSync(file);
        if (seen.has(real)) continue;
        seen.add(real);
        readNuget(file, sources, disabled);
      }
    }
  }
  const active = overrides.length ? overrides.map(value => sources.get(value.toLowerCase()) || value) :
    [...sources].filter(([key]) => (disabled.get(key) || '').toLowerCase() !== 'true').map(([, value]) => value);
  return [...new Set(active.filter(azureSource))].sort();
}

function providerInstalled(invocation) {
  if (invocation.env.NUGET_PLUGIN_PATHS) {
    return invocation.env.NUGET_PLUGIN_PATHS.split(';').some(file => {
      try { return fs.statSync(file).isFile(); } catch { return false; }
    });
  }
  const name = invocation.manager === 'nuget' ? 'CredentialProvider.Microsoft.exe' : 'CredentialProvider.Microsoft.dll';
  const dirs = [path.join(invocation.env.HOME, '.nuget/plugins')];
  while (dirs.length) {
    const dir = dirs.pop();
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { continue; }
    for (const entry of entries) {
      if (entry.isFile() && entry.name === name) return true;
      if (entry.isDirectory()) dirs.push(path.join(dir, entry.name));
    }
  }
  return false;
}

function resolveShim(file, content, args, windowsPath = path.win32) {
  if (!/\.cmd$/i.test(file)) throw new Error(`Unsupported Windows launcher ${file}. Only standard .cmd shims or native executables are supported.`);
  const azure = content.match(/"%~dp0([^"%\r\n]*python\.exe)"\s+-IBm\s+azure\.cli\s+%\*/i);
  if (azure && windowsPath.basename(file).toLowerCase() === 'az.cmd') {
    return { file: windowsPath.resolve(windowsPath.dirname(file), azure[1]), args: ['-IBm', 'azure.cli', ...args] };
  }
  const node = content.match(/"(?:%dp0%|%~dp0|%basedir%)[\\/]?([^"%\r\n]+)"\s+%\*/i);
  if (node) {
    const script = node[1].replace(/\\/g, '/');
    const rush = script.endsWith('node_modules/@microsoft/rush/bin/rush') || script.endsWith('node_modules/@microsoft/rush/bin/rush-pnpm');
    if (rush || contains('npm-cli.js npx-cli.js pnpm.cjs pnpx.cjs yarn.js corepack.js rush.js rush-pnpm.js', path.posix.basename(script))) {
      return { file: 'node', args: [windowsPath.resolve(windowsPath.dirname(file), node[1]), ...args] };
    }
  }
  throw new Error(`Unsupported Windows launcher ${file}. Install a native executable or standard Node package-manager .cmd shim. Arbitrary batch and PowerShell scripts are not executed.`);
}

function command(name, args, env) {
  let file = executable(name, env);
  if (process.platform !== 'win32' || /\.(exe|com)$/i.test(file)) return { file, args };
  const resolved = resolveShim(file, readConfig(file, true), args);
  if (resolved.file === 'node') {
    const local = path.join(path.dirname(file), 'node.exe');
    resolved.file = exists(local) ? local : executable('node', env);
    if (!exists(resolved.args[0])) throw new Error(`Node entrypoint for ${name} is missing.`);
  }
  return resolved;
}

function child(command, env, capture = false) {
  return new Promise((resolve, reject) => {
    const running = spawn(command.file, command.args, { env, shell: false, stdio: ['inherit', capture ? 'pipe' : 'inherit', 'inherit'] });
    let stdout = '', oversized = false;
    const listeners = new Map();
    for (const signal of process.platform === 'win32' ? ['SIGINT'] : ['SIGINT', 'SIGTERM', 'SIGHUP', 'SIGQUIT']) {
      const forward = () => {
        if (process.platform !== 'win32') {
          try { running.kill(signal); } catch {}
        }
      };
      listeners.set(signal, forward);
      process.on(signal, forward);
    }
    const cleanup = () => {
      for (const [signal, listener] of listeners) process.removeListener(signal, listener);
    };
    if (capture) running.stdout.on('data', chunk => {
      if (stdout.length + chunk.length > 1024 * 1024) {
        oversized = true;
        running.kill();
      } else stdout += chunk.toString();
    });
    running.once('error', error => { cleanup(); reject(error); });
    running.once('close', (code, signal) => {
      cleanup();
      if (oversized) reject(new Error('Azure CLI token output exceeded the supported limit.'));
      else resolve({ code: code ?? 128 + (os.constants.signals[signal] || 1), stdout });
    });
  });
}

async function acquireToken(env, inherited) {
  if (inherited && inherited.trim()) return { value: inherited, code: 0 };
  const azure = command('az', ['account', 'get-access-token', '--resource', RESOURCE, '--query', 'accessToken', '-o', 'tsv'], env);
  const result = await child(azure, env, true);
  if (result.code) throw Object.assign(new Error('Azure CLI failed. Run az login and verify feed access.'), { exitCode: result.code });
  const value = result.stdout.trim();
  if (!value) throw new Error('Azure CLI returned an empty access token.');
  return { value, code: 0 };
}

async function run(invocation, completion) {
  const { manager, args, env } = invocation;
  const overlay = {};
  if (completion) overlay.ARTIFACTS_ACCESSTOKEN = PLACEHOLDER;
  else {
    const action = classify(manager, args);
    let decision = Decision.pass, sources = [];
    if (contains('dotnet nuget', manager)) {
      if (action.registry) {
        sources = nugetSources(invocation);
        if (sources.length) {
          if (!providerInstalled(invocation)) throw new Error(`Install the Azure Artifacts Credential Provider for ${manager} in ~/.nuget/plugins, or set NUGET_PLUGIN_PATHS to its executable. No installer runs automatically.`);
          decision = Decision.token;
        }
      }
    } else {
      const config = registryConfiguration(invocation);
      if (action.registry && hasFeed(config)) decision = Decision.token;
      else if (config.placeholder && !Object.hasOwn(env, 'ARTIFACTS_ACCESSTOKEN')) decision = Decision.placeholder;
    }
    if (decision === Decision.token) {
      const inherited = env.ARTIFACTS_ACCESSTOKEN || (sources.length ? env.VSS_NUGET_ACCESSTOKEN : '');
      const token = await acquireToken(env, inherited);
      overlay.ARTIFACTS_ACCESSTOKEN = token.value;
      if (sources.length) {
        overlay.VSS_NUGET_ACCESSTOKEN = token.value;
        overlay.VSS_NUGET_URI_PREFIXES = sources.join(';');
      }
    } else if (decision === Decision.placeholder) overlay.ARTIFACTS_ACCESSTOKEN = PLACEHOLDER;
  }
  const managerCommand = command(manager, args, env);
  return (await child(managerCommand, { ...env, ...overlay })).code;
}

function atomicWrite(file, content) {
  const temporary = path.join(path.dirname(file), `.npmrc-${process.pid}-${require('node:crypto').randomUUID()}`);
  try {
    fs.writeFileSync(temporary, content, { flag: 'wx', mode: exists(file) ? fs.statSync(file).mode & 0o777 : 0o600 });
    fs.renameSync(temporary, file);
  } finally {
    try { fs.unlinkSync(temporary); } catch {}
  }
}

async function writeNpm(args, env) {
  if (args[0] === '--') args = args.slice(1);
  if (!args.length || !args[0]) throw new Error('usage: write-npm FEED [USER [EMAIL]]');
  const fromProject = args[0] === '--from-project';
  if (fromProject && args.length !== 1) throw new Error('--from-project takes no other arguments.');
  let feed = args[0], user = args[1] || 'AzCliToken', email = args[2] || 'not-used@example.com';
  const target = path.join(env.HOME, '.npmrc');
  if (fromProject) {
    const file = path.join(process.cwd(), '.npmrc');
    if (!exists(file)) throw new Error('No project .npmrc in the current directory.');
    const config = { entries: new Map(), placeholder: false };
    readRegistry(config, 'npmrc', file);
    const registry = config.entries.get('registry:default') || '';
    if (!azureSource(registry)) throw new Error('Project registry must be an HTTPS Azure Artifacts URL.');
    feed = registry.replace(/^https:\/\//i, '');
    user = 'VssSessionToken';
  } else if (args.length > 3) throw new Error('usage: write-npm FEED [USER [EMAIL]]');
  if ([feed, user, email].some(value => /[\r\n\0]/.test(value))) throw new Error('Feed, user, and email must not contain newlines or NUL.');
  const entries = base => `//${base}:username=${user}\n//${base}:_authToken=\${ARTIFACTS_ACCESSTOKEN}\n//${base}:email=${email}\n`;
  if (!fromProject) {
    fs.appendFileSync(target, entries(`${feed}/registry/`) + entries(`${feed}/`), { mode: 0o600 });
    return 0;
  }
  if (exists(target) && fs.lstatSync(target).isSymbolicLink()) throw new Error('Project writer does not replace a symlinked user .npmrc. Update the target explicitly.');
  const old = readConfig(target), base = feed.replace(/\/+$/, '') + '/', content = entries(base);
  const current = old.replace(/\r\n/g, '\n').split('\n');
  if (content.trim().split('\n').every(line => current.includes(line))) return 0;
  const keys = ['username', '_authToken', 'email'].map(key => `//${base}:${key}`);
  const kept = current.filter(line => !keys.includes(line.split('=')[0].trim()));
  if (kept.length !== current.length) {
    process.stderr.write('Update existing authentication entries in user .npmrc? [y/N] ');
    const readline = require('node:readline').createInterface({ input: process.stdin });
    let answer = '';
    for await (const line of readline) { answer = line; break; }
    readline.close();
    if (answer.trim().toLowerCase() !== 'y') return 0;
  }
  if (readConfig(target) !== old) throw new Error('User .npmrc changed while confirming. Run write-npm again.');
  const preserved = kept.join('\n').replace(/\n+$/, '');
  atomicWrite(target, (preserved ? preserved + '\n' : '') + content);
  return 0;
}

async function main(args = process.argv.slice(2)) {
  try {
    if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('Node 22 or newer is required.');
    if (args[0] === 'write-npm') return await writeNpm(args.slice(1), environment());
    if (args.length < 4 || !contains('run complete', args[0]) || args[1] !== '--manager' || args[3] !== '--') throw new Error('usage: az-auth-core run|complete --manager MANAGER -- ARGS; write-npm -- FEED [USER [EMAIL]]');
    let manager = args[2];
    if (!contains(MANAGERS, manager)) throw new Error(`Unsupported manager ${manager}.`);
    if (args[0] === 'complete' && manager !== 'pnpm') throw new Error('Completion supports only pnpm.');
    if (manager === 'pn') manager = 'pnpm';
    const invocation = { manager, args: args.slice(4), cwd: process.cwd(), env: environment() };
    return await run(invocation, args[0] === 'complete');
  } catch (error) {
    process.stderr.write(`az-auth-core: ${error.message}\n`);
    return error.exitCode || 1;
  }
}

module.exports = { main, classify, resolveShim };
if (require.main === module) main().then(code => { process.exitCode = code; });

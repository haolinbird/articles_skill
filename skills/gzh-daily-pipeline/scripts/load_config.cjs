#!/usr/bin/env node
/**
 * 统一配置加载器 —— 流水线所有脚本的配置入口（零依赖）。
 *
 * 为什么要这个东西：
 *   以前每个脚本各写一份「找 .env」的逻辑，路径写死成 ../.env，
 *   于是配置散在多个文件里、打包后还会断链。现在只在这里找一次。
 *
 * 配置分两层，都由本文件读取：
 *   L1 config/pipeline.env      —— 共享参数与密钥（T2I、字数、日产量、Token）
 *   L2 config/platforms.json    —— 平台开关与同步参数（唯一数据源）
 *
 * 根目录定位（开发态与打包态都能用，不写死层数）：
 *   从本文件所在目录逐级向上，找第一个含有 config/pipeline.env 的目录。
 *   开发态：skills/gzh-daily-pipeline/scripts → 项目根（3 层）
 *   打包态：<安装根>/<包名>/scripts        → <包名>（1 层）
 *   可用环境变量 GZH_PROJECT_ROOT 直接指定根目录覆盖。
 *
 * 用法（脚本内）：
 *   const { loadEnv, cfg, getPlatforms, getEnabledPlatforms } = require('./load_config.cjs');
 *   loadEnv();                       // 自动加载，已存在的环境变量不会被覆盖
 *   const key = cfg('GZH_T2I_API_KEY');
 *
 * 用法（命令行调试）：
 *   node load_config.cjs --root              打印定位到的项目根
 *   node load_config.cjs --platforms         打印平台清单（id / 名称 / 是否启用）
 *   node load_config.cjs --sync-plan         打印 S6 应同步的平台与喂入文件
 */

const fs = require('fs');
const path = require('path');

const ENV_FILENAME = 'pipeline.env';
const PLATFORMS_FILENAME = 'platforms.json';
const ENV_REL = path.join('config', ENV_FILENAME);
const PLATFORMS_REL = path.join('config', PLATFORMS_FILENAME);
const MAX_UP = 6;

/**
 * 定位项目根：向上找第一个含 config/ 且其中有 platforms.json 或 pipeline.env 的目录。
 *
 * 为什么认 config/ 目录而不是只认 pipeline.env：
 *   分发包里 pipeline.env 含密钥、按设计被排除，只带 platforms.json 和模板。
 *   若以 pipeline.env 为线索，包内定位会失败，连带读不到平台开关。
 *
 * @returns {string|null}
 */
function findRoot() {
  if (process.env.GZH_PROJECT_ROOT) {
    return process.env.GZH_PROJECT_ROOT;
  }
  let dir = __dirname;
  for (let i = 0; i < MAX_UP; i++) {
    if (fs.existsSync(path.join(dir, 'config'))
        && (fs.existsSync(path.join(dir, PLATFORMS_REL))
            || fs.existsSync(path.join(dir, ENV_REL)))) {
      return dir;
    }
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return null;
}

/**
 * 解析 env 文件内容为键值对。支持 # 注释、export 前缀、单双引号。
 * @param {string} text
 * @returns {Object}
 */
function parseEnv(text) {
  const out = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const m = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!m) continue;
    out[m[1]] = m[2].replace(/^["']|["']$/g, '').trim();
  }
  return out;
}

/**
 * 加载 L1 配置到 process.env。
 * 已在进程环境中的变量优先，不被文件覆盖（命令行 export 优先级最高）。
 * @returns {{root: string|null, file: string|null, loaded: boolean, keys: string[]}}
 */
function loadEnv() {
  const root = findRoot();
  if (!root) {
    return { root: null, file: null, loaded: false, keys: [] };
  }
  const file = path.join(root, ENV_REL);
  if (!fs.existsSync(file)) {
    return { root, file, loaded: false, keys: [] };
  }
  const vars = parseEnv(fs.readFileSync(file, 'utf8'));
  const keys = [];
  for (const [k, v] of Object.entries(vars)) {
    if (!(k in process.env)) {
      process.env[k] = v;
      keys.push(k);
    }
  }
  return { root, file, loaded: true, keys };
}

/**
 * 读取配置项。环境变量优先，其次取已加载的文件值。
 * @param {string} key
 * @param {string} [fallback='']
 */
function cfg(key, fallback) {
  const v = process.env[key];
  return v === undefined || v === '' ? (fallback === undefined ? '' : fallback) : v;
}

/**
 * 读取 L2 平台清单。
 * @returns {{root: string|null, file: string|null, platforms: Array}}
 */
function getPlatforms() {
  const root = findRoot();
  if (!root) return { root: null, file: null, platforms: [] };
  const file = path.join(root, PLATFORMS_REL);
  if (!fs.existsSync(file)) return { root, file, platforms: [] };
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  return { root, file, platforms: data.platforms || [] };
}

/**
 * 取启用的平台，可按是否支持 wechatsync 过滤。
 * @param {{syncable?: boolean}} [opts]
 */
function getEnabledPlatforms(opts) {
  const o = opts || {};
  return getPlatforms().platforms.filter((p) => {
    if (!p.enabled) return false;
    if (o.syncable && !(p.wechatsync && p.wechatsync.supported)) return false;
    return true;
  });
}

module.exports = {
  findRoot,
  loadEnv,
  cfg,
  getPlatforms,
  getEnabledPlatforms,
  parseEnv,
};

/* ---------------- 命令行调试模式 ---------------- */
if (require.main === module) {
  const args = process.argv.slice(2);
  const info = loadEnv();
  if (args.includes('--root')) {
    console.log(info.root || '(未找到项目根：缺少 config/pipeline.env)');
    process.exit(info.root ? 0 : 1);
  }
  if (args.includes('--platforms')) {
    for (const p of getPlatforms().platforms) {
      console.log(`${p.enabled ? '✅' : '❌'} ${p.id.padEnd(12)} ${p.name}`);
    }
    process.exit(0);
  }
  if (args.includes('--sync-plan')) {
    const list = getEnabledPlatforms({ syncable: true });
    if (!list.length) {
      console.log('没有可同步的平台（检查 config/platforms.json 的 enabled）');
      process.exit(1);
    }
    for (const p of list) {
      console.log(`${p.wechatsync.param}  ${p.wechatsync.sync_input}  [${p.name}]`);
    }
    process.exit(0);
  }
  console.log('用法: node load_config.cjs --root | --platforms | --sync-plan');
  process.exit(0);
}

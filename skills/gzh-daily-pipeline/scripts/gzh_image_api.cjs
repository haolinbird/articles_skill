#!/usr/bin/env node
/**
 * gzh_image_api.cjs - 正文配图批量生成器（gzh-daily-pipeline S4-1 阶段）
 *
 * 用途：按 shot list 批量生成正文配图，取代 ImageGen 工具调用，不消耗 WorkBuddy 积分。
 *
 * ⚠️ 所有配置集中在 config/pipeline.env —— 本脚本不写死任何通道信息，换通道只改那一个文件：
 *   GZH_T2I_ENABLED          总开关，false 则跳过（降级，不阻塞流水线）
 *   GZH_T2I_ENDPOINT         端点完整 URL
 *   GZH_T2I_API_KEY          API Key
 *   GZH_T2I_MODEL            模型名
 *   GZH_T2I_PROTOCOL         协议：dashscope | openai
 *   GZH_T2I_SIZE             输出尺寸，如 1024x576（16:9 横版，配图模板要求）
 *   GZH_T2I_WATERMARK        是否加水印（dashscope 协议支持关闭），建议 false
 *   GZH_IMAGES_PER_ARTICLE   每篇张数（拆上下篇时按篇计算；批量超限仅警告）
 *
 * 当前默认通道：商汤日日新 SenseNova（OpenAI images 兼容，2026-10-12 从智谱 CogView-4 切来）
 *
 * 协议差异（脚本已自动处理，换通道无需改代码）：
 *   dashscope: body = {model, input:{messages:[{role,content:[{text}]}]}, parameters:{size,n,watermark}}
 *              响应 = output.choices[0].message.content[0].image  （同步，直接是图片 URL）
 *              若只返回 output.task_id → 自动轮询 GET /api/v1/tasks/{task_id}
 *   openai:    body = {model, prompt, size, n}
 *              响应 = data[0].url | data[0].b64_json
 *
 * 与 gzh_opener.cjs 的区别（勿混用）：
 *   - opener 只做开篇人设图，端点写死拼 /v1；本脚本端点完整可配，支持批量、间隔、尺寸回退、异步轮询。
 *   - 本脚本不负责压缩（sips）与改写 md 引用，那是 S4-1 后续步骤。
 *
 * 用法：
 *   # 单张
 *   node gzh_image_api.cjs --prompt "画面描述" --out assets/xxx/01-slug.png [--size 1024x576]
 *
 *   # 批量（shots.json 为数组：[{ "slug": "01-aaa", "prompt": "..." }]）
 *   node gzh_image_api.cjs --shots shots.json --dir assets/xxx [--delay 3000] [--size 1024x576]
 *
 * 退出码：0 全部成功或按配置跳过；2 配置缺失或全部失败；3 部分失败（已生成的部分保留）
 */

const fs = require('fs');
const path = require('path');

// 统一配置入口：向上查找 config/pipeline.env 自动加载，不再各脚本自己找 .env
const { loadEnv } = require('./load_config.cjs');

// 默认值必须与当前实际通道（商汤 SenseNova）一致：
// 若留成阿里百炼，一旦 config/pipeline.env 缺 GZH_T2I_ENDPOINT，脚本会拿百炼端点+dashscope 协议
// 去请求商汤的 Key，表现为诡异失败而非清晰报错（2026-10-13 修正）。
const DEFAULT_ENDPOINT = 'https://token.sensenova.cn/v1/images/generations';
const DEFAULT_MODEL = 'sensenova-u1.5-lite';
const DEFAULT_PROTOCOL = 'openai';
// 尺寸回退序列：先按用户指定，被拒则依次降级。不同厂商支持的分辨率差异很大。
// ⚠️ 全部保持 16:9 横版，与 GZH_T2I_SIZE 及配图模板的构图要求一致，回退时不得退回方形。
// ⚠️ 商汤要求宽高为 32 的倍数：1024x576(32×32 / 32×18)、512x288(32×16 / 32×9) 均合规。
const SIZE_FALLBACKS = ['1024x576', '512x288'];

function getArg(name, def) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

function baseOf(endpoint) {
  const m = String(endpoint).match(/^(https?:\/\/[^/]+)/);
  return m ? m[1] : 'https://dashscope.aliyuncs.com';
}

/** OpenAI 风格尺寸 1024x576 → 阿里风格 1024*576 */
function toDashscopeSize(s) {
  return String(s).replace('x', '*');
}

function buildBody(cfg, prompt, size) {
  if (cfg.protocol === 'dashscope') {
    const parameters = { size: toDashscopeSize(size), n: 1 };
    if (cfg.watermark !== undefined) parameters.watermark = cfg.watermark;
    return {
      model: cfg.model,
      input: { messages: [{ role: 'user', content: [{ text: prompt }] }] },
      parameters,
    };
  }
  // OpenAI 兼容协议
  // watermark 只在 config/pipeline.env 里显式配置了 GZH_T2I_WATERMARK 时才发送。
  // 商汤 SenseNova 不传该字段默认带水印，必须显式传 false 才去水印；
  // 而部分厂商（智谱等）的 OpenAI 端点不认该字段，清空该变量即可退回不传，互不干扰。
  const body = { model: cfg.model, prompt, size, n: 1 };
  if (cfg.watermarkExplicit) body.watermark = cfg.watermark;
  return body;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function downloadImage(url) {
  const r = await fetch(url, { signal: AbortSignal.timeout(120000) });
  if (!r.ok) throw new Error(`图片下载失败 HTTP ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

/** 异步通道：轮询任务直到 SUCCEEDED / FAILED */
async function pollTask(cfg, taskId) {
  const url = `${baseOf(cfg.endpoint)}/api/v1/tasks/${taskId}`;
  const deadline = Date.now() + 300000; // 5 分钟
  let last = '';
  while (Date.now() < deadline) {
    const r = await fetch(url, {
      headers: { Authorization: `Bearer ${cfg.apiKey}` },
      signal: AbortSignal.timeout(60000),
    });
    const t = await r.text();
    let j;
    try { j = JSON.parse(t); } catch { throw new Error(`任务查询返回非 JSON: ${t.slice(0, 200)}`); }
    const out = j.output || {};
    const st = out.task_status || '';
    if (st && st !== last) { console.log(`  任务状态: ${st}`); last = st; }
    if (st === 'SUCCEEDED') {
      const results = out.results || out.choices || [];
      const u = (results[0] || {}).url || (results[0] || {}).image;
      if (!u) throw new Error(`任务成功但无图片 URL: ${t.slice(0, 200)}`);
      return await downloadImage(u);
    }
    if (st === 'FAILED' || st === 'CANCELED' || st === 'UNKNOWN') {
      throw new Error(`生图任务失败: ${out.code || ''} ${out.message || st}`);
    }
    await sleep(3000);
  }
  throw new Error('轮询超时（5 分钟）');
}

/** 调用一次生图接口，返回 Buffer。sizeRejected=true 表示尺寸不被支持（供上层回退）。 */
async function generate(cfg, prompt, size) {
  const resp = await fetch(cfg.endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${cfg.apiKey}` },
    body: JSON.stringify(buildBody(cfg, prompt, size)),
    signal: AbortSignal.timeout(300000),
  });

  const text = await resp.text();
  if (!resp.ok) {
    const sizeBad = /size|resolution|dimension/i.test(text);
    const err = new Error(`HTTP ${resp.status}: ${text.slice(0, 300)}`);
    err.sizeRejected = sizeBad && resp.status === 400;
    throw err;
  }

  let data;
  try { data = JSON.parse(text); } catch { throw new Error(`返回非 JSON: ${text.slice(0, 200)}`); }

  // 阿里原生（同步）：output.choices[0].message.content[0].image = 图片 URL
  const choice = (data.output && data.output.choices && data.output.choices[0]) || null;
  if (choice) {
    const content = (choice.message && choice.message.content) || [];
    const imgItem = content.find((x) => x && x.image);
    if (imgItem && imgItem.image) return await downloadImage(imgItem.image);
    const results = data.output.results || [];
    const u = (results[0] || {}).url || (results[0] || {}).image;
    if (u) return await downloadImage(u);
  }

  // 阿里原生（异步）：只返回 task_id → 轮询
  if (data.output && data.output.task_id) {
    return await pollTask(cfg, data.output.task_id);
  }

  // OpenAI 风格 {data:[{url|b64_json}]} 与 硅基流动风格 {images:[{url}]}
  const list = data.data || data.images || [];
  const item = list[0];
  if (!item) throw new Error(`返回无图片数据: ${text.slice(0, 200)}`);
  if (item.b64_json) return Buffer.from(item.b64_json, 'base64');
  if (item.url) return await downloadImage(item.url);
  if (typeof item === 'string' && item.startsWith('data:image')) {
    return Buffer.from(item.split(',')[1], 'base64');
  }
  throw new Error(`返回里无 b64_json / url: ${JSON.stringify(item).slice(0, 200)}`);
}

/** 带尺寸回退的生图：先试首选尺寸，被拒则按 SIZE_FALLBACKS 降级。 */
async function generateWithFallback(cfg, prompt, outPath, label) {
  const tried = [cfg.size, ...SIZE_FALLBACKS.filter((s) => s !== cfg.size)];
  for (const size of tried) {
    try {
      const buf = await generate(cfg, prompt, size);
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
      fs.writeFileSync(outPath, buf);
      console.log(`OK   ${label} -> ${outPath} (${size}, ${Math.round(buf.length / 1024)} KB)`);
      return true;
    } catch (e) {
      if (e.sizeRejected && size !== tried[tried.length - 1]) {
        console.log(`  ${label} 尺寸 ${size} 不被支持，回退中...`);
        continue;
      }
      console.error(`FAIL ${label}: ${e.message}`);
      return false;
    }
  }
  return false;
}

async function main() {
  loadEnv();

  // ---- 总开关：关闭则整段跳过（降级，不阻塞流水线）----
  const enabled = (process.env.GZH_T2I_ENABLED || 'true').trim().toLowerCase();
  if (enabled === 'false' || enabled === '0' || enabled === 'no') {
    console.log('GZH_T2I_ENABLED=false，按配置跳过正文配图生成（终稿不带图，流水线继续）。');
    process.exit(0);
  }

  const singlePrompt = getArg('--prompt', '');
  const out = getArg('--out', '');
  const shotsFile = getArg('--shots', '');
  const dir = getArg('--dir', '');
  const delay = parseInt(getArg('--delay', '3000'), 10); // 批量间隔，防限流

  const endpoint = getArg('--endpoint', '') || process.env.GZH_T2I_ENDPOINT || DEFAULT_ENDPOINT;
  const apiKey = getArg('--api-key', '') || process.env.GZH_T2I_API_KEY || '';
  const model = getArg('--model', '') || process.env.GZH_T2I_MODEL || DEFAULT_MODEL;
  const protocol = getArg('--protocol', '') || process.env.GZH_T2I_PROTOCOL || DEFAULT_PROTOCOL;
  const size = getArg('--size', process.env.GZH_T2I_SIZE || '1024x576');
  // 取原始值判断「是否显式配置」，不能直接用默认值兜底，否则分不清「没配」和「配了 false」
  const wmRaw = (process.env.GZH_T2I_WATERMARK === undefined
    ? ''
    : String(process.env.GZH_T2I_WATERMARK).trim().toLowerCase());
  const watermark = wmRaw === 'true' || wmRaw === '1';
  const watermarkExplicit = wmRaw !== '';

  if (!apiKey) {
    console.error('缺少 API Key：请在 config/pipeline.env 填 GZH_T2I_API_KEY，或用 --api-key 传入。');
    console.error(`当前端点: ${endpoint}  模型: ${model}`);
    process.exit(2);
  }
  if (!singlePrompt && !shotsFile) {
    console.error('用法: --prompt "描述" --out <文件>  或  --shots shots.json --dir <目录>');
    process.exit(2);
  }

  const cfg = { endpoint, apiKey, model, protocol, size, watermark, watermarkExplicit };
  console.log(`端点: ${endpoint}\n模型: ${model}\n协议: ${protocol}\n尺寸: ${size}\n水印: ${watermark}${watermarkExplicit ? '' : '（未显式配置，不下发该字段）'}\n`);

  // ---- 单张模式 ----
  if (singlePrompt) {
    if (!out) { console.error('单张模式必须给 --out'); process.exit(2); }
    const ok = await generateWithFallback(cfg, singlePrompt, out, 'single');
    process.exit(ok ? 0 : 2);
  }

  // ---- 批量模式 ----
  let shots;
  try { shots = JSON.parse(fs.readFileSync(shotsFile, 'utf-8')); }
  catch (e) { console.error(`读取 ${shotsFile} 失败: ${e.message}`); process.exit(2); }
  if (!Array.isArray(shots) || !shots.length) { console.error('shots.json 必须是非空数组'); process.exit(2); }
  if (!dir) { console.error('批量模式必须给 --dir'); process.exit(2); }

  const perArticle = parseInt(process.env.GZH_IMAGES_PER_ARTICLE || '0', 10);
  if (perArticle > 0 && shots.length > perArticle) {
    console.warn(`⚠️ 本批 ${shots.length} 张，超过 config/pipeline.env 配置的每篇 ${perArticle} 张，确认是否为多篇合并批量。`);
  }

  // 并发度：1 = 串行；>1 = 分桶并行（桶内 Promise.all，桶间仍 sleep(delay) 防限流）
  const concurrency = Math.max(1, parseInt(process.env.GZH_T2I_CONCURRENCY || '1', 10));

  let okCount = 0;
  if (concurrency === 1) {
    // 串行（原行为）：逐张生成，每张间隔 delay
    for (let i = 0; i < shots.length; i++) {
      const s = shots[i];
      const outPath = path.join(dir, `${s.slug}.png`);
      if (await generateWithFallback(cfg, s.prompt, outPath, s.slug)) okCount++;
      if (i < shots.length - 1 && delay > 0) await sleep(delay);
    }
  } else {
    // 并行：按 concurrency 分桶，桶内并发，桶间 sleep(delay)
    console.log(`并发模式：桶大小 = ${concurrency}`);
    for (let b = 0; b < shots.length; b += concurrency) {
      const bucket = shots.slice(b, b + concurrency);
      const results = await Promise.all(bucket.map((s) => {
        const outPath = path.join(dir, `${s.slug}.png`);
        return generateWithFallback(cfg, s.prompt, outPath, s.slug);
      }));
      okCount += results.filter(Boolean).length;
      if (b + concurrency < shots.length && delay > 0) await sleep(delay);
    }
  }

  console.log(`\n完成: ${okCount}/${shots.length} 张`);
  process.exit(okCount === shots.length ? 0 : okCount > 0 ? 3 : 2);
}

main().catch((e) => {
  console.error(`异常: ${e.message}`);
  process.exit(2);
});

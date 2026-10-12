#!/usr/bin/env node
/**
 * gzh_opener.cjs - 公众号开篇人设图生成器（gzh-daily-pipeline S4-0 阶段）
 *
 * 功能：按固定模板生成开篇插画（人物形象 + 关键词大字 + 口号小字），
 *       插在终稿固定问候语之后。
 *
 * 用法：
 *   node gzh_opener.cjs --keyword "GPT 6.0" --out D:/path/YYYYMMDD_开篇图.png \
 *                       [--persona "1位黑发中年大叔"] [--slogan "一人公司"] \
 *                       [--size 1536x1024] [--prompt "自定义完整提示词"] \
 *                       [--base-url <API地址>] [--api-key <密钥>]
 *
 * API 配置（优先级：命令行参数 > 环境变量 > 报错）：
 *   GZH_IMAGE_BASE_URL   OpenAI images 兼容端点，如 http://your-host:8090
 *   GZH_IMAGE_API_KEY    对应 API Key
 *   GZH_IMAGE_MODEL      模型名（默认 gpt-image-2，推荐：中文文字渲染可靠）
 *
 * 退出码：0 成功；2 失败（执行方应降级用其他图片生成工具，prompt 直接用模板文字，
 *         并在末尾追加「图片中必须准确出现这些中文文字」）
 *
 * 说明：双引号在即梦 AI 里表示「引号内文字必须出现在图里」；gpt-image 系列
 *       对引号包裹文字的遵循度同样最好，故模板保留双引号写法。
 */

const fs = require('fs');
const path = require('path');

const DEFAULT_MODEL = 'gpt-image-2';

// 开篇图固定模板。占位符：
//   {KW}      文章核心观点名词（--keyword 传入）
//   {PERSONA} 人物形象描述（--persona 或环境变量 GZH_OPENER_PERSONA，配置在 resources/author_visual_assets.md）
//   {SLOGAN}  固定小字口号（--slogan 或环境变量 GZH_OPENER_SLOGAN，配置在 resources/author_visual_assets.md）
const TEMPLATE =
  '"{KW}"，插画风格，可爱的{PERSONA}在笔记本电脑前，绿色养眼背景，' +
  '关键词文字放大作为背景显示，画面下方中间是小字"{SLOGAN}"，文字不要太靠近上下的边缘，横版构图';

// 统一配置入口：向上查找 config/pipeline.env 自动加载，不再各脚本自己找 .env
const { loadEnv } = require('./load_config.cjs');

function getArg(name, def) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

async function main() {
  loadEnv();

  const keyword = getArg('--keyword', '');
  const out = getArg('--out', '');
  const persona = getArg('--persona', process.env.GZH_OPENER_PERSONA || '1位黑发中年大叔');
  const slogan = getArg('--slogan', process.env.GZH_OPENER_SLOGAN || '一人公司');
  const size = getArg('--size', '1536x1024'); // gpt-image 横版
  const customPrompt = getArg('--prompt', '');

  const baseUrl = (getArg('--base-url', '') || process.env.GZH_IMAGE_BASE_URL || '').replace(/\/+$/, '');
  const apiKey = getArg('--api-key', '') || process.env.GZH_IMAGE_API_KEY || '';
  const model = getArg('--model', '') || process.env.GZH_IMAGE_MODEL || DEFAULT_MODEL;

  if (!keyword || !out) {
    console.error('用法: node gzh_opener.cjs --keyword "文章关键词" --out <输出.png> [--persona ...] [--slogan ...] [--size 1536x1024] [--prompt 自定义]');
    console.error('API 配置: 环境变量 GZH_IMAGE_BASE_URL / GZH_IMAGE_API_KEY / GZH_IMAGE_MODEL，或 --base-url / --api-key 参数（见 config/pipeline.env.example）');
    process.exit(1);
  }
  if (!baseUrl || !apiKey) {
    console.error('缺少 API 配置：请设置 GZH_IMAGE_BASE_URL 和 GZH_IMAGE_API_KEY（复制 config/pipeline.env.example 为 config/pipeline.env 填写），或用 --base-url/--api-key 传入');
    process.exit(2);
  }

  const prompt = customPrompt
    || TEMPLATE.replace('{KW}', keyword).replace('{PERSONA}', persona).replace('{SLOGAN}', slogan);
  console.log(`生成开篇图: 关键词="${keyword}" 人物="${persona}" 口号="${slogan}" 尺寸=${size}`);
  console.log(`prompt: ${prompt}`);

  // 商汤等部分厂商不传 watermark 时默认带水印，显式下发 GZH_T2I_WATERMARK 的值（默认 false）
  const wmRaw = (process.env.GZH_T2I_WATERMARK === undefined
    ? ''
    : String(process.env.GZH_T2I_WATERMARK).trim().toLowerCase());
  const body = { model, prompt, size, n: 1 };
  if (wmRaw !== '') body.watermark = (wmRaw === 'true' || wmRaw === '1');

  const resp = await fetch(`${baseUrl}/v1/images/generations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(300000), // 生图最长 5 分钟
  });

  if (!resp.ok) {
    console.error(`API 失败 HTTP ${resp.status}: ${(await resp.text()).slice(0, 300)}`);
    console.error('降级指引: 用环境内的图片生成工具，prompt=上面的模板文字，并追加要求图片中必须准确出现引号内的中文文字');
    process.exit(2);
  }

  const data = await resp.json();
  const item = data.data && data.data[0];
  if (!item) {
    console.error(`API 返回无数据: ${JSON.stringify(data).slice(0, 300)}`);
    process.exit(2);
  }

  let buf;
  if (item.b64_json) {
    buf = Buffer.from(item.b64_json, 'base64');
  } else if (item.url) {
    const imgResp = await fetch(item.url, { signal: AbortSignal.timeout(120000) });
    if (!imgResp.ok) {
      console.error(`图片下载失败 HTTP ${imgResp.status}`);
      process.exit(2);
    }
    buf = Buffer.from(await imgResp.arrayBuffer());
  } else {
    console.error(`返回里既无 b64_json 也无 url: ${JSON.stringify(item).slice(0, 200)}`);
    process.exit(2);
  }

  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, buf);
  console.log(`OK 开篇图已保存: ${out} (${Math.round(buf.length / 1024)} KB)`);
}

main().catch((e) => {
  console.error(`异常: ${e.message}`);
  console.error('降级指引: 用环境内的图片生成工具按模板生成');
  process.exit(2);
});

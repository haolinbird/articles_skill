#!/usr/bin/env node
/**
 * gzh_format.cjs - 公众号排版美化转换器（gzh-daily-pipeline S4b 阶段核心脚本）
 *
 * 功能：把干净的 Markdown 终稿转换为「带内联样式的富文本 Markdown」，
 *       供 Wechatsync 直接同步到公众号草稿箱（公众号编辑器只认内联样式）。
 *       独立成段的图片行回填为 HTML <img> 标签（本地路径），确保 Wechatsync 上传后公众号能正常渲染。
 *
 * 用法：
 *   node gzh_format.cjs <输入.md> [--theme warm|tech|mono] [--out 输出.md]
 *                       [--keep-h1] [--title "文章标题"]
 *
 * 依赖：markdown-it（已装在 <全局 node_modules 路径>）
 *       NODE_PATH=<全局 node_modules 路径>
 *
 * 主题：warm（默认，暖橙）/ tech（科技蓝）/ mono（极简黑白）
 */

const fs = require('fs');
const path = require('path');
const MarkdownIt = require('markdown-it');

// ---------------- 主题定义 ----------------
// 公众号排版规范要点：全内联、正文15px、行高1.75、两端8px留白、
// 段间距16px、标题左竖条、金句卡片居中、图注居中灰字
const THEMES = {
  warm: {
    primary: '#c2571a',      // 暖棕橙（强调色：标题/加粗/金句）
    accent: '#fdf3ec',       // 浅橙底（金句卡背景）
    text: '#3f3f3f',
    secondary: '#8a5a3b',
  },
  tech: {
    primary: '#1d4ed8',
    accent: '#eff4ff',
    text: '#333333',
    secondary: '#3b5b8a',
  },
  mono: {
    primary: '#111111',
    accent: '#f2f2f2',
    text: '#333333',
    secondary: '#555555',
  },
};

function buildStyles(t) {
  return {
    wrap:
      "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;" +
      `font-size:15px;color:${t.text};letter-spacing:0.5px;line-height:1.75;`,
    p: 'margin:0 0 16px;padding:0 8px;text-align:justify;',
    h1: `font-size:18px;color:${t.primary};font-weight:bold;margin:36px 0 20px;padding:0 8px;`,
    h2: `font-size:17px;color:${t.primary};font-weight:bold;margin:36px 0 20px;padding:0 8px;border-left:4px solid ${t.primary};`,
    h3: `font-size:16px;color:${t.text};font-weight:bold;margin:28px 0 16px;padding:0 8px;`,
    h4: `font-size:15px;color:${t.secondary};font-weight:bold;margin:24px 0 12px;padding:0 8px;`,
    strong: `color:${t.primary};font-weight:bold;`,
    em: '',
    quote: `margin:24px 8px;padding:16px 20px;background:${t.accent};border-radius:8px;`,
    quote_p: `font-size:16px;color:${t.primary};font-weight:bold;text-align:center;line-height:1.9;margin:0;`,
    caption: 'text-align:center;color:#999999;font-size:13px;margin:0 0 24px;padding:0 8px;',
    ul: 'margin:0 0 16px;padding-left:24px;',
    ol: 'margin:0 0 16px;padding-left:24px;',
    li: 'margin-bottom:8px;text-align:justify;',
    li_p: 'margin:0;text-align:justify;',
    hr: "border:none;height:1px;background:#e5e5e5;margin:32px 8px;",
    link: `color:${t.primary};text-decoration:none;`,
    code_inline: 'background:#f5f5f5;padding:2px 6px;border-radius:4px;font-size:14px;color:#c7254e;',
    fence: 'background:#f7f7f7;padding:12px;border-radius:6px;font-size:13px;overflow-x:auto;',
    img_p: 'margin:0 0 8px;text-align:center;', // 独图段落（紧跟图注）
  };
}

// ---------------- 预处理 ----------------
// 1) 抽出「独立成段的图片行」→ 占位符（最终原样回填 markdown 语法，保 Wechatsync 上传逻辑）
// 2) 剥离第一个 h1（标题在发布框单独填）
function preprocess(src, keepH1) {
  const imgLines = [];
  const lines = src.split(/\r?\n/);
  const out = [];
  const imgRe = /^!\[[^\]]*\]\(([^)]+)\)\s*$/;
  for (const line of lines) {
    const m = line.match(imgRe);
    if (m) {
      imgLines.push(line.trim());
      out.push(`{{GZH_IMG_${imgLines.length - 1}}}`);
    } else {
      out.push(line);
    }
  }
  let text = out.join('\n');

  if (!keepH1) {
    text = text.replace(/^#\s+.+\r?\n+/, ''); // 第一个一级标题
  }
  return { text, imgLines };
}

// ---------------- 渲染 ----------------
function render(text, s) {
  const md = new MarkdownIt({ html: true, breaks: true, linkify: false });
  let inQuote = 0;
  let inListItem = 0;

  // 直接控制每个标签输出，不依赖 renderToken 上下文
  const open = (tag, style) => `<${tag} style="${style}">\n`;
  const close = (tag) => `</${tag}>\n`;

  // block 级开闭标签
  md.renderer.rules.paragraph_open = (tokens, idx) => {
    const inline = tokens[idx + 1];
    const ch = inline && inline.type === 'inline' ? inline.children || [] : null;
    // 图注判定：整段只有一个 em（em_open ... em_close）
    const isCaption =
      ch && ch.length >= 2 && ch[0].type === 'em_open' && ch[ch.length - 1].type === 'em_close';
    // 独图段落判定：段落 inline 只含一个 image
    const isSoloImg = ch && ch.length === 1 && ch[0].type === 'image';
    const style = isCaption
      ? s.caption
      : isSoloImg
        ? s.img_p
        : inQuote > 0
          ? s.quote_p
          : inListItem > 0
            ? s.li_p
            : s.p;
    return open('p', style);
  };
  md.renderer.rules.paragraph_close = () => close('p');

  md.renderer.rules.heading_open = (tokens, idx) => open(tokens[idx].tag, s[tokens[idx].tag] || s.h4);
  md.renderer.rules.heading_close = (tokens, idx) => close(tokens[idx].tag);

  md.renderer.rules.blockquote_open = () => { inQuote++; return open('blockquote', s.quote); };
  md.renderer.rules.blockquote_close = () => { inQuote--; return close('blockquote'); };

  md.renderer.rules.bullet_list_open = () => open('ul', s.ul);
  md.renderer.rules.bullet_list_close = () => close('ul');
  md.renderer.rules.ordered_list_open = () => open('ol', s.ol);
  md.renderer.rules.ordered_list_close = () => close('ol');
  md.renderer.rules.list_item_open = () => { inListItem++; return open('li', s.li); };
  md.renderer.rules.list_item_close = () => { inListItem--; return close('li'); };

  md.renderer.rules.hr = (tokens, idx, options, env, self) => {
    const t = tokens[idx];
    t.attrSet('style', s.hr);
    return `<hr${self.renderAttrs(t)}>\n`;
  };

  // inline 级
  md.renderer.rules.strong_open = (t, i) => `<${t[i].tag} style="${s.strong}">`;
  md.renderer.rules.strong_close = (t, i) => `</${t[i].tag}>`;
  md.renderer.rules.em_open = (t, i) => `<em style="${s.em}">`;
  md.renderer.rules.em_close = () => `</em>`;
  md.renderer.rules.code_inline = (t, i) => `<code style="${s.code_inline}">${t[i].content}</code>`;
  md.renderer.rules.link_open = (t, i) => {
    t[i].attrSet('style', s.link);
    return `<a href="${t[i].attrGet('href')}" style="${s.link}">`;
  };
  md.renderer.rules.link_close = () => `</a>`;
  md.renderer.rules.fence = (t, i) => {
    const code = md.utils.escapeHtml(t[i].content);
    return `<pre style="${s.fence}"><code>${code}</code></pre>\n`;
  };

  return md.render(text);
}

// ---------------- 主流程 ----------------
function main() {
  const args = process.argv.slice(2);
  const input = args[0];
  if (!input || !fs.existsSync(input)) {
    console.error('用法: node gzh_format.cjs <输入.md> [--theme warm|tech|mono] [--out 输出.md] [--keep-h1] [--title "标题"]');
    process.exit(1);
  }
  const getArg = (name, def) => {
    const i = args.indexOf(name);
    return i >= 0 && args[i + 1] ? args[i + 1] : def;
  };
  const hasFlag = (name) => args.includes(name);

  const themeName = getArg('--theme', 'warm');
  const theme = THEMES[themeName];
  if (!theme) {
    console.error(`未知主题: ${themeName}（可选 warm / tech / mono）`);
    process.exit(1);
  }
  const s = buildStyles(theme);
  const outPath = getArg('--out', input.replace(/\.md$/i, `_gzh.md`));
  const title = getArg('--title', '');
  const keepH1 = hasFlag('--keep-h1');

  const src = fs.readFileSync(input, 'utf-8');
  const { text, imgLines } = preprocess(src, keepH1);
  let html = render(text, s).trim();

  // 图片行回填：占位符段替换回 HTML <img> 标签（本地相对路径）。
  // 注意：不能回填 markdown ![]() 语法——公众号渲染器把排版版整体当 HTML 处理，
  // markdown 图片语法会原样显示成网址文字。HTML <img src="本地路径"> 同样能被
  // Wechatsync 的图片识别逻辑匹配上传，并替换为其 CDN 地址。
  for (let i = 0; i < imgLines.length; i++) {
    const m = imgLines[i].match(/^!\[[^\]]*\]\(([^)]+)\)\s*$/);
    const imgTag = m
      ? `<img src="${m[1]}" alt="" style="max-width:100%;display:block;margin:16px auto;border-radius:8px;" />`
      : imgLines[i];
    html = html.replace(new RegExp(`<p style="[^"]*">\\s*{{GZH_IMG_${i}}}\\s*</p>`), imgTag);
    html = html.replace(`{{GZH_IMG_${i}}}`, imgTag); // 兜底
  }

  const header = title
    ? `<!-- gzh-formatted theme=${themeName} | 标题: ${title} | 本文件由 gzh_format.cjs 生成，勿手改进度样式 -->\n`
    : `<!-- gzh-formatted theme=${themeName} | 本文件由 gzh_format.cjs 生成，勿手改进度样式 -->\n`;

  const result = `${header}\n<section style="${s.wrap}">\n\n${html}\n\n</section>\n`;
  fs.writeFileSync(outPath, result, 'utf-8');

  const imgCount = imgLines.length;
  console.log(`OK 排版完成: ${outPath}`);
  console.log(`   主题=${themeName} 图片=${imgCount}张 标题=${title || '(未指定)'}`);
}

main();

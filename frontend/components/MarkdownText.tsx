"use client";

import React from "react";

/**
 * 轻量 Markdown 渲染器 —— 覆盖 AI 输出常见语法（标题 / 列表 / 加粗 / 行内代码 /
 * 代码块 / 段落），无第三方依赖，保证在客户端可靠渲染。
 *
 * 与 react-markdown 相比，这里对中文简历/对话更友好：段落内的单个换行会保留为
 * <br>，而不是被合并成空格，避免「姓名：张三 电话：138…」这类内容挤成一行。
 */

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // 匹配 **加粗** 与 `行内代码`
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${keyBase}-b${i++}`}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={`${keyBase}-c${i++}`}>{token.slice(1, -1)}</code>);
    }
    last = m.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export default function MarkdownText({ text }: { text: string }) {
  if (text == null) return null;
  // 防御：localStorage 恢复的旧数据可能不是字符串（如对象），直接 .split 会抛
  // "text.split is not a function"。这里兜底转成可读字符串，避免整页渲染崩溃。
  if (typeof text !== "string") {
    try {
      text = JSON.stringify(text, null, 2);
    } catch {
      text = String(text);
    }
  }
  if (!text) return null;

  const lines = text.split("\n");
  const blocks: React.ReactNode[] = [];
  let listItems: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let paragraph: string[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let key = 0;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push(
        <p key={`p${key++}`}>
          {paragraph.map((line, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && <br />}
              {renderInline(line, `p${key}-${idx}`)}
            </React.Fragment>
          ))}
        </p>
      );
      paragraph = [];
    }
  };

  const flushList = () => {
    if (listItems.length && listType) {
      const items = listItems.map((item, idx) => (
        <li key={`li${key}-${idx}`}>{renderInline(item, `li${key}-${idx}`)}</li>
      ));
      blocks.push(
        listType === "ul" ? (
          <ul key={`u${key++}`}>{items}</ul>
        ) : (
          <ol key={`o${key++}`}>{items}</ol>
        )
      );
      listItems = [];
      listType = null;
    }
  };

  const flushCode = () => {
    if (codeLines.length) {
      blocks.push(
        <pre key={`pre${key++}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      codeLines = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, "");

    // 代码块围栏
    if (line.trimStart().startsWith("```")) {
      flushParagraph();
      flushList();
      if (inCodeBlock) {
        flushCode();
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    // 标题
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      flushParagraph();
      flushList();
      const level = h[1].length;
      const content = renderInline(h[2], `h${key}`);
      if (level === 1) blocks.push(<h1 key={`h${key++}`}>{content}</h1>);
      else if (level === 2) blocks.push(<h2 key={`h${key++}`}>{content}</h2>);
      else if (level === 3) blocks.push(<h3 key={`h${key++}`}>{content}</h3>);
      else blocks.push(<h4 key={`h${key++}`}>{content}</h4>);
      continue;
    }

    // 水平线
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push(<hr key={`hr${key++}`} />);
      continue;
    }

    // 无序列表
    const ulMatch = line.match(/^\s*[-*]\s+(.*)$/);
    if (ulMatch) {
      flushParagraph();
      if (listType !== "ul") {
        flushList();
        listType = "ul";
      }
      listItems.push(ulMatch[1]);
      continue;
    }

    // 有序列表
    const olMatch = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (olMatch) {
      flushParagraph();
      if (listType !== "ol") {
        flushList();
        listType = "ol";
      }
      listItems.push(olMatch[1]);
      continue;
    }

    // 空行
    if (line.trim() === "") {
      flushParagraph();
      flushList();
      continue;
    }

    // 普通段落行
    flushList();
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  flushCode();

  return <>{blocks}</>;
}

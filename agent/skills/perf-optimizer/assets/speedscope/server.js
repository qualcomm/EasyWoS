#!/usr/bin/env node

const http = require('http');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const url = require('url');

const PORT = 8888;
const DIST_DIR = __dirname;

// 创建 HTTP 服务器
const server = http.createServer((req, res) => {
  // 解析 URL
  const parsedUrl = url.parse(req.url, true);
  let pathname = parsedUrl.pathname;

  // 移除前导斜杠
  if (pathname.startsWith('/')) {
    pathname = pathname.slice(1);
  }

  // 默认文件
  if (pathname === '' || pathname === '/') {
    pathname = 'index-auto.html';
  }

  const filePath = path.join(DIST_DIR, pathname);

  // 安全检查：防止目录遍历
  if (!filePath.startsWith(DIST_DIR)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('Forbidden');
    return;
  }

  // 读取文件
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not Found');
      return;
    }

    // 设置正确的 Content-Type
    let contentType = 'application/octet-stream';
    const ext = path.extname(filePath).toLowerCase();
    const mimeTypes = {
      '.html': 'text/html',
      '.js': 'application/javascript',
      '.css': 'text/css',
      '.json': 'application/json',
      '.png': 'image/png',
      '.ico': 'image/x-icon',
      '.woff2': 'font/woff2',
      '.ttf': 'font/ttf',
      '.wasm': 'application/wasm',
      '.txt': 'text/plain',
      '.md': 'text/markdown'
    };

    contentType = mimeTypes[ext] || contentType;

    res.writeHead(200, {
      'Content-Type': contentType,
      'Access-Control-Allow-Origin': '*'
    });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});

// 获取命令行参数
const args = process.argv.slice(2);
let jsonFile = args[0];

if (jsonFile) {
  // 转换为绝对路径
  if (!path.isAbsolute(jsonFile)) {
    jsonFile = path.resolve(process.cwd(), jsonFile);
  }

  // 检查文件是否存在
  if (!fs.existsSync(jsonFile)) {
    console.error(`Error: File not found: ${jsonFile}`);
    process.exit(1);
  }

  // 获取文件名
  const fileName = path.basename(jsonFile);

  // 等待服务器启动后打开浏览器
  setTimeout(() => {
    const openUrl = `http://localhost:${PORT}/index-auto.html?file=${encodeURIComponent(fileName)}`;
    console.log(`Opening: ${openUrl}`);

    // 复制文件到 dist 目录（临时）
    const destPath = path.join(DIST_DIR, fileName);
    fs.copyFileSync(jsonFile, destPath);

    // 打开浏览器
    const platform = process.platform;
    let command;
    if (platform === 'win32') {
      command = `start ${openUrl}`;
    } else if (platform === 'darwin') {
      command = `open "${openUrl}"`;
    } else {
      command = `xdg-open "${openUrl}"`;
    }

    exec(command, (err) => {
      if (err) console.error('Failed to open browser:', err);
    });
  }, 500);
} else {
  console.log(`Usage: node server.js <path-to-speedscope.json>`);
  console.log(`Example: node server.js C:\\Temp\\Test\\i4Tools_16556.speedscope.json`);
}

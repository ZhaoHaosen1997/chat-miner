# Chat-Miner 前端

Vue 3 + Vite + TailwindCSS 构建的群聊分析仪表盘。

## 技术栈

- **Vue 3** — Composition API + `<script setup>`
- **Vite** — 构建工具
- **TailwindCSS** — 原子化 CSS
- **Lucide** — 图标库
- **Chart.js** — 数据可视化

## 目录结构

```
src/
├── App.vue              # 根组件
├── main.js              # 入口
├── router.js            # 路由 (Hash: / /report/:date /portraits /portrait/:id)
├── components/
│   ├── Sidebar.vue      # 侧边栏（群切换、导航）
│   ├── DailyReport.vue  # 日报详情页
│   ├── PortraitList.vue # 群友画像列表
│   ├── PortraitDetail.vue # 群友画像详情
│   ├── UploadModal.vue  # 上传导入弹窗
│   ├── ProgressPanel.vue # 分析进度 SSE 面板
│   └── ...              # 其他组件
└── views/               # 页面视图
```

## 开发

```bash
npm install
npm run dev    # 开发服务器 :5173
npm run build  # 生产构建 → dist/
```

## 生产部署

构建后由 FastAPI 托管静态文件，与后端同端口。

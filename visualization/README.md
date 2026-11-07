# 前端

React、TypeScript 和 ECharts 实现事件研究界面，Dagre 负责关系图布局，TanStack Query 管理请求状态。依赖版本见 `package.json` 和 `package-lock.json`。

## 运行

```powershell
npm ci
npm run dev
```

开发服务器将 `/api` 代理到 `http://127.0.0.1:8000`。运行 `npm run build` 后，FastAPI 提供 `dist/` 中的生产资源。

## 页面

- 事件研究：选择事件、按角色查看证券、打开逐跳原文、切换历史日期、比较行情、导出简报。
- 案例库：查看不同模型主题的事件与研究结果。
- 知识更新：提交文本或选择回放样例，预览抽取结果、入图及重置。
- 资料与方法：搜索来源，查看实体、关系和日期计算说明。

关系图按真实事实边排列节点，事实方向与查询遍历方向分别处理。入图后返回原事件并聚焦新增证券。源码位于 `src/views/`、`src/components/` 和 `src/lib/`。

界面与布局参考及许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和根目录 [ATTRIBUTIONS.md](../ATTRIBUTIONS.md)。录屏方法见 [RECORDING.md](RECORDING.md)。

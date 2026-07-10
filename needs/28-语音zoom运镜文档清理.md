# 需求28 · 语音精简、zoom 调试、运镜文档与项目清理

## 目标

1. act9「方案确认与经验沉淀」语音仅播报步骤标题。
2. 地图左上角增加 zoom 调试指示器。
3. 梳理镜头运镜逻辑至 `docs/design/camera_movement.md`。
4. 清理无效代码、陈旧文档与过时单测断言。

## 验收

- [x] act9 TTS 文本为「方案确认与经验沉淀。」
- [x] 左上角 `data-testid="zoom-indicator"` 实时显示 zoom
- [x] 运镜文档覆盖九幕配置与算法
- [x] 移除永久隐藏的 DownstreamTopologyInset、废弃 DEMO_INPUT_CASE2、修复 design README 断链
- [x] 单测由 43 文件/169 用例精简至 27 文件/164 用例（按域合并，去除重复 lerpPath 等边界测试）

# 陈守义十段月度口语稿 v2

本目录从原工作区新版三人稿件中，仅纳入公交司机十篇，原稿 SHA-256 保持不变。这是有意设计的虚构测试月份，不是自然采样的真实生活记录，也不代表阿尔茨海默症人群的临床表现。其他两个人本轮没有重新处理。

十篇已在 2026-10-11 重新生成小米音频，由 ECS Paraformer 实际识别，再经技术核对、DeepSeek 提取入库。阶段清单见 `processed/run-manifest.json`。`manifest.json` 的 `status` 描述冻结稿件时的状态，不是本轮处理结果。技术核对不等于人工逐段听读，也不等于真实本人认可。

授权、修订、期望答案等测试员工作写在 `review-notes.md`，不进入 TTS 或模型答案输入。不同片段允许长短不同，不为凑千字重复讲道理。原来的 v1 文件、音频、ASR、gold、结果没有改动。

这些稿件不是旧音频的“准确转写”。新的具体措辞与转述对话都是虚构创作。不能直接替换v1输入再与旧60问比较准确率，不能用新稿覆盖ASR，不能把文字字数当成音频时长。

## 阅稿顺序

先读 01/04/10，再按 01 至 10 连续读，检查人物关系、年份纠正和前后变化。`processed/` 分别保存机器稿、技术核对稿与模型结果，修改记录可以逐项对照。音频以独立材料包交付，哈希记录在处理清单中。

本轮先跑第一段小样并在 Android 播放，再顺序处理九段。旧集仍保留，本轮没有用新稿覆盖旧 ASR、重算旧 60 问成绩或删除历史失败。原始 ASR 中仍有同音词和断句问题，具体见验收说明。

## 文件与复验

- `initial-model-story.json` 是每段初次模型结果；`processed-story.json` 是修订和技术复核后的当前结果。请保留这一区分。
- `technical-curation.json` 记录人工技术合并、排除与补充，不伪装成自动提取。
- `answer-review.json` 只检查本轮12道开发题，`access-checks.json` 记录三轮撤权。没有重跑旧60问。
- 音频见0.9.0发布附件 `remember-me-chenshouyi-materials-20261011.zip`。包内 `audio/bus_driver-01.wav` 至10，与 `run-manifest.json` 哈希逐一对应。

开发者可用 `python -m tools.monthly_eval.spoken_garden_ecs --help` 查看分阶段入口。运行输出目录必须位于忽略的 `services/backend/var/`；小米密钥从受限环境读取，工作台会话令牌只存该目录的 `private-config.json`。不要使用公开演示账号执行重复批量导入。需要新验收时创建新的虚构空间，按 audio/upload/review/snapshot 阶段操作，先保留ASR再制作核对稿；禁止直接拿脚本替代ASR。

[完整验收](../../docs/agent-loop/IMMERSIVE_GARDEN_ACCEPTANCE_2026-10-11.md) · [手机体验入口](../../docs/agent-loop/ANDROID_090_QUICK_START.md)

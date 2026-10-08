# 本轮交付：补充用词、普通账号、Android真实闭环

2026-10-08。基线 `b3d5142`，工作区 `D:/codex_work/remember-me-agent-loop`，分支 `codex/agent-integration`。未push/merge/publish，未改饮食项目。

**Android模拟器已跑通原生录音到有来源回答的真实服务流程。当前交付仍依赖PC后端，不是任意网络开箱即用的发布版。**

## 三项标准对应的实际状态

|用户标准|本轮结果|仍未完成|
|---|---|---|
|手机录音、分析、调用、形成记忆|MediaRecorder录音、暂停/继续、播放、ANDROID_MIC上传、Groq转写、核对、微信模型整理、保存和App问答实际完成|输入为小米合成声音经虚拟麦克风注入；不是实体手机或真人麦克风验收|
|有记忆与人物理解的Twin|真实故事、书面补充、人物视图/候选、授权读者问答可用；新增候选1条未自动批准。此前真实校准与ADD见AGENT_CORE_RESULTS|不能承诺人格仿真准确率；60问有1项漏答、24项质量问题。自动重复事件判断和自动冲突识别未完整实现|
|认可的设计语言|Android自然场景、花朵品牌、通透表面、固定今天/档案/对话/我的，档案分录音/记忆/人物；网页保留自然花园与材质|iOS未在Windows编译；全尺寸、大字、减少动效及实体设备全面视觉验收未完成|

## 手动补充与普通账号

- 私有“我的用词”支持人名、生僻字、方言与含义，不自动送模型或共享。核对时可带入独立“本次补充说明”。原始ASR、核对文字、书面说明分别保存。
- 说明以`owner-input`记忆和`CALIBRATION`证据保存，没有伪造音频偏移，不允许ORIGINAL。实际问答能使用它，也明确标为书面说明。
- 分享包括原音、完整核对文字、补充和记忆；词表不自动分享。修改/删除遵守修订失效规则，重试不会复活删除内容。pending修订的补充也保持pending。
- 普通账号注册只建立自己的空白空间。30天设备会话，Android Keystore加密保存，网页HttpOnly Cookie。退出清除本地内容并尝试服务端撤销；失败时不假称服务端已撤销。
- 追加迁移0012/0013；`var/pre-0013-backup.db`与`0013-migration-trial.db`保留。副本完整性检查ok，核心旧表计数未变，再迁移运行库。旧空间不自动认领。

真实示例：“落屋就是回家，不是辞职；老隗是同事隗师傅，不是亲戚。”App和独立Reader都实际答对；Reader三轮均为SIMULATION及CALIBRATION来源。

## 实际验收和失败历史

1. Android普通登录，保存用词，原生录音约20.168秒，本机播放，再经Groq `whisper-large-v3`转写、技术核对、Deepseek-v4-flash整理：1条模型记忆+1条书面补充。机器稿末句有误识别，未用创作稿覆盖。
2. 微信模型生成1个关于工作收入与家庭安全取舍的人物候选，仍pending，不自动升级稳定人格。
3. 独立Reader授权→问答→人物视图→原音200→撤权→原音及旧答案404，连续3轮通过。私有词表接口404，可见资料不包含未带入故事的测试词。
4. Android重启保持登录、读取人物资料、退出清除会话通过。首次仪器测试没等异步资料加载，补正确等待后通过，没有改数据过关。
5. Playwright实际验证：延迟旧401不会清除新登录；断网退出请求失败后刷新仍停留登录页。
6. 原生录音脚本有控制文件重定向、按钮等待、滚动定位失败历史。前几次重试曾追加用词，最终故事补充保留3次重复；测试已修复为替换输入，没有暗改已确认历史。
7. Reader首轮将书面说明误路由ORIGINAL，严格校验拒绝，未保存错误答案。v6说明来源后，3轮实际请求恢复。结构/证据/鉴权错误现在返回明确代码，评测不再误当暂时性503自动重试。

## 完整60问复测

固定30段Groq月度故事，三人各20问，`twin-compact-v6`：60个结果、61次尝试，1次45秒超时后有界重试。未重做音频，未将创作原稿或gold给模型。请求/响应均标识Deepseek-v4-flash；不能独立证明底层模型身份。

|助手逐条读回答和证据后的分类|数量|
|---|---:|
|所问主要要点有支持|35|
|字形、指代、冗长、附加细节或遗漏边界需改进|24|
|明确未通过|1|
|当前权限、来源、ORIGINAL逐字一致机械错误|0|

失败为`life_review-q16`：Reader可见材料明确看海城市与日期未定，却返回UNKNOWN，属于漏答。保留本轮失败，不挑其他轮正确答案替换。此前消防员爱好错误归属、本子原因无依据推断，本轮未重现；不能保证任意问法。

24项细节见`tools/mobile_eval/review_product_v6.py`和本机逐题报告。不是自然语音准确率、人工听读或临床评估。新补充功能未用于倒改固定输入以提高分数。

## 规则、构建与交付

- Backend **365项**、AI Core **176项**、Android **33项单元测试**全部通过。debug APK和测试APK构建成功。
- 两项真实Android仪器测试分别通过：录音到问答、重启人物页与退出。最终仅来源标签微调的APK再次安装启动成功。
- 新增5项用词/来源规则、3项账号规则和4项Twin错误分类包含在Backend总数，不累计重复。
- 代码审查缺陷先复现后修复：共享补充纠正泄露、pending补充提前生效、共享补充搜索误隐藏；另修网页登录竞态、离线退出、空空间Android退出。
- `git diff --check`通过；合成声音、真实模型、模拟器、确定性替身测试分别记录。

[安装与操作说明](INSTALL_ANDROID.md)包含当前电脑、其他电脑、实体Android连接和公网部署边界。

- `tools/Start-RememberMe.ps1`检查/启动服务、选择ADB设备转发、安装启动App。当前环境的检查与安装路径已执行，不重复启动运行中的服务。
- `tools/package_local_product.py`白名单打包服务端源码、品牌、说明和APK，排除.env、var、身份、数据库；不是捆绑Python/模型的离线运行包。
- 本机文件：`output/remember-me/remember-me-local-debug.apk`、`remember-me-local-kit.zip`、`manifest.json`，不提交Git。

## 同学结构及剩余硬缺口

现有统一后端提供Owner审核的ADD/SUPPORT/CONFLICT/CHANGE，新旧版本、冲突暂停、时间说明和失效保留。不复制第二套事实库，也不称为同学完整自动Trait状态机。

仍需持续在线后端目标及HTTPS、实体Android录音体验、签名分发。目前没有服务器/域名，未执行公网发布。iOS需要Mac构建。账号找回、备份恢复演练、稳定人格表达和自动关系判断仍待后续验收。

## 本机证据索引

相对`services/backend/`：
- `var/mobile-product/result.json`、`injection.json`、`instrumentation.log`、`persisted-session-retry.log`、`profile.json`、`followthrough.json`及截图。
- `var/product-final-regression.log`、`product-ai-regression.log`、`product-final-android-build.log`、`product-web-{race,logout}-final.log`。
- `var/monthly-eval/qa-groq-product-v6-full.json`和`cloud-asr-runs/relay-compact/groq-product-v6-full-{annotations,review}.json`。
- `var/ai-core.log`、`var/groq-asr/calls.jsonl`含实际端点、模型、提示SHA、耗时、usage/缺失、finish_reason和校验结果。身份文件不打包。

## 执行取舍

沿用用户已授权设计，没有因新增技能模板删除已有实现重做。新增功能首轮测试为实现后验证；审查缺陷先失败再修，不能称整轮完整TDD。公网目标缺失不妨碍本机实现，但必须继续标明未部署。合成音频注入不冒充真人或实体手机。

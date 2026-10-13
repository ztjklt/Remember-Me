# iOS 记忆花园基础版交付

2026-10-14，Asia/Singapore。用户在本聊天明确选择「继续记忆花园基础版」，授权复用真实记忆、故事和来源浏览。本轮保留主工作区已有未提交改动；不实现受保护区域、密码解锁、Legacy 激活或多人声纹。

## 实际行为

- 入口：记忆 → 进入记忆花园。原来的记忆列表、搜索、详情和管理流程保留，四个主入口不变。
- 二维花朵浏览分为「故事与记忆」「人物与关系」，支持内容及来源文字搜索。正常空库不生成样例。
- 故事和人物记录复用既有 workbench narrative 读取接口，只投影本人已确认、当前有效且全部来源可解析的记录。未确认、历史、失效或缺失来源记录不展示。
- 没有已核对故事时，已有记忆按同一 Episode 分组；标识为同段原文中的记忆，不把同一录音擅自归为同一事件。人物记忆逐条保留归属，同名人物不自动合并；装饰花径不表示因果关系。
- 打开花朵后可看已核对记录、原话、来源类型和原始记忆，实际录音沿用已有原音播放器；文字来源不伪造音频。日期使用设备时区的录入日期，故事已有时间文字原样保留，不推断事件日期。
- 「移出本机花园」明确确认后只保存展示编号，右上角可恢复。文件按服务、pin、Actor、Subject 隔离，完整文件保护且排除备份；不保存正文、凭据或音频，也不授予访问权限。
- 删除记忆仍进入既有 Memory 详情流程，使相关理解和答案失效；原始录音保留。本轮没有新增整段来源永久删除，也不能把移出展示称为底层删除。
- 登出、更换账号／空间、模型或记忆更新立即使旧故事快照失效；晚到请求不能恢复旧空间内容。读取接口返回错误空间或 reader 时拒绝；401/403 显示登录／权限不可用，旧服务缺少故事能力或其他读取错误明确回退已有记忆浏览。
- 大字号保留系统字体，切换内容改用菜单、缩短介绍；长标题可换行，列表仍可滚动。

## 接口与代码范围

新增客户端 MemoryGarden.swift、13 项投影／隔离测试及 3 项花园 UI 测试；复用 ReviewOverview、MemoryRecord、EpisodeRecord、APIClient、MemoryDetailView 和 OriginalPlayer。现有四入口 UI 测试用于兼容回归。仅增加内部只读内容修订号及播放器／来源标签的模块可见性。

没有新增必填字段、公开 Contract、数据库迁移或 Android 改动，没有替换 Backend／Worker／供应商。测试时在线服务为 CloudBase019 / ios-voice-completion-85b4987；本轮未发布服务。另一个声音设置任务的后续变化不计入本轮花园验证。

使用已有蓝花素材，原始 PNG 未编辑，保持图片比例。来源为 codex/twin-chat-memory 工作区既有 Android drawable-nodpi，与 docs/mobile-ui/native-garden/asset-manifest.json 对应：

| 素材 | SHA256 |
| --- | --- |
| rm_garden_flower_front.png | 4eb9e3b8c00afb37b45bd70ce10d667e41ceffeb3ddd69fa8dce8530f1d3bc4f |
| rm_garden_flower_side.png | 4c2d226b0f066d64adbfc3c961edf686cee97a3ea817469efa288b9ec4a40381 |

## 实际验证

模拟器 iPhone 18 Pro：100 个单元用例通过，包含 Garden 13、连接／聊天 35、LocalRecording 21、PersonReview 15、Voice 16；日志 build/ios-garden-unit-delivery-20261014.log。覆盖来源失效、人物归属、不合并录音、显示偏好隔离、账号变化、晚到响应、reader 拒绝、错误回退、全部分组记忆搜索及日期时区。

4 个不同 UI 用例通过：真实离线空库没有假记忆；虚构隔离预览的移出取消／确认／恢复及人物切换；辅助功能 XXXL 下能到达故事详情及控制；既有四入口。初次三个用例、单独大字号用例以及布局调整后两个复验分别记录，不能相加为更多不同用例：

- build/ios-garden-ui-20261014.log
- build/ios-garden-large-ui-20261014.log
- build/ios-garden-ui-final-20261014.log

最终普通字号和大字号截图已查看，未见裁切或重叠。花朵内容截图是显式 DEBUG 虚构预览，有可见样例标签、无真实账号／网络／授权；不能代替本人真实内容验收。截图及 xcresult 保存在 build/ios-garden-ui-final-attachments-20261014 和 build/ios-garden-20261014/Logs/Test。

初次编译因 catch error 名称遮蔽、私有修订号访问和浮点字面量写法失败；修正后上述单元、UI 和签名构建通过。原生 macOS 探针初次编译缺少 Cloud DTO／RecordingDraft 定义，补齐真实源码定义后通过。这些失败不是业务场景通过。

云端探针从当前客户端实际 Network.swift／DTO／投影代码编译，使用系统 HTTPS 及既有隔离 QA 账号读取，不打印正文、凭据或音频。实际读取 4 个 Episode、6 条 Memory，投影为 4 个花园条目；已有确认故事为 0。随后只在该 QA 空间创建一条现有来源支持的测试故事，使用既有人工确认接口，原生探针成功解码并投影 1 条确认故事；结束时已停用该测试记录，保留服务端审计痕迹。原 Episode／Memory 未修改，未调用模型生成或读取真人资料。写入测试记录不是只读操作；探针读取本身只读。

安全摘要位于 build/private/garden-cloud-read-result.json、garden-story-qa-result.json。QA 记录创建／确认／停用成功不代表本人实际核对故事或原音播放已经验收。

## 真机交付

签名 Debug 构建成功，codesign --verify --deep --strict 通过，包标识 me.remember.personal.ios，版本 **1.8.0 / 2026101402**。build/ios-garden-device-20261014.log 记录 BUILD SUCCEEDED。devicectl 覆盖安装到 iPhone 15 Pro Max「黑幕」成功，设备应用列表独立核对为上述版本，启动 success，未传入测试参数；没有卸载或清空容器。

安装／查询／启动摘要保存在 build/private/garden-install-20261014.json、garden-installed-apps-20261014.json、garden-launch-20261014.json。工作区另一个声音任务随后将源码版本推进至 1.8.1 / 2026101403；本轮保留其变更，1.8.0 是本轮实际构建和安装的历史记录，不表示后续设备版本固定。

本人在手机浏览真实花园、播放原音、移出和恢复的自然体验仍需本人操作。104 个不同自动用例、QA 云端联调及真机安装启动已经完成；本人内容体验、服务端受保护区域、密码与身后开放没有被这些结果代替。

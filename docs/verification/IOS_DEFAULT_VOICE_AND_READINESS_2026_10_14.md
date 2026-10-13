# 默认声音通话与本人音色可视状态

2026-10-14，Asia/Singapore。用户报告声音设置／通话按钮无法点击，并明确要求可见的录音与复刻状态，随后批准“允许默认声音先通话，复刻好后再切换”。沿用原 iOS 云服务和 LiveKit/CosyVoice Worker，不变更 Android 或删除原数据。

## 最终行为

- 没有本人复刻音色时，默认声音也能发起实时通话。仍需当前声音／识别用途确认、独立 VOICE 和 CLOUD_TWIN 许可。
- 页首显示当前选用默认声音或本人音色。默认声音不会被标成本人复刻；录样本与复刻可以稍后进行。
- 本人音色卡显示录制、确认提交、复刻中、已就绪／失败。就绪用绿色标记，准备时自动检查，未知状态保留手动检查。
- 录音保存在手机不等于已提交复刻；样本文字为空、未确认本人声音、未确认用途等条件都有下一步提示。编辑文字可在同一账号空间恢复。
- 本人音色就绪后可试听固定合成句，由本人判断是否像自己；可以停止试听。后续通话可选本人音色；已进行的通话保留原选用模式。
- 通话按钮位于音色设置之前，并解释禁用原因；云端问答用途可以在本页确认。

## 授权与 Contract

提案：docs/architecture/twin-voice-preview-proposal.md、docs/architecture/twin-default-voice-proposal.md。v0.8 增加可选 default_voice_available 和 voice_mode（personal / default）；旧请求省略仍选本人音色，v0.1–v0.7 文件保留。

默认通话的内部 rvp_default_ Profile 无声音样本，不进入本人音色查询，也不阻止随后复刻。撤销时先结束通话并清空预置音色引用，维护任务也拒绝删除系统音色。公开 payload 无供应商音色编号。试听逐包及返回前验证登录、本人空间、声音许可和同一个就绪音色，音频只在内存，不成为 Episode 或人格证据，不缓存。

## 实际检查

Backend 实时 Voice 31 项通过（2 个上游弃用警告），包含无克隆的默认通话、两个许可依然必需、旧请求仍需本人音色、默认引用不成为本人音色、撤销不请求删除系统音色，以及合成试听与生成期间撤销。初次试听撤销测试嵌套 TestClient 的 portal 报错；更正为独立许可状态变更后通过。

Contracts 25 项通过。iOS Voice 17 项、三个 UI 状态用例通过；此前新增的声音文字恢复／空间隔离用例 1 项通过，共 21 个不同 Native 用例。待提交 UI 的第一次执行卡在自动化启动，停止后单独复验通过；最终三个 UI 均通过。默认声音无克隆时，确认用途后开始按钮可用；未实际从 UI fixture 发起网络或录音。默认及就绪状态截图已检查。

Backend 源码 5952ccc（试听）及 6cb7c17（默认通话）已推送 codex/twin-chat-memory。1.8.2 / 2026101405 Release 签名构建通过。默认通话源包白名单 168 文件，SHA256 61b439d3eefba504b8f215ae0ccac032786f09ed95ac8564a33a7356a829d0ed；解压逐文件检查运行密钥不在包内。

## 发布记录

试听 CloudRun020 / task 2352679 管理任务失败，实际镜像完整推送，digest fe2997a1209b24197dfdc30566852203257adb9d4d4a444af7f8fb9b246a6f43。默认声音 CloudRun021 / task 2352720 同样构建和推送成功，但发布任务失败，平台仅返回“创建版本失败：任务失败”。不从此错误推断业务代码故障或永久网络故障。

默认声音镜像基于该完成的 020 镜像，只替换当前 Backend 和 schemas。已向同一原服务提交直接发布镜像 task 2352734，等待上线和真实 RTC 检查。CLI 登录在监控中失效，恢复同一账号、设备、既有权限和期限；授权回调内容经筛选，未把凭据输出到工具或源码。没有迁移、开新服务或变更 Worker。

此前 iOS 1.8.0 / 2026101402（基础提示）和 1.8.1 / 2026101404（状态、试听入口）已覆盖安装并核对启动；最终默认声音版本 1.8.2 / 2026101405 已覆盖安装；包内版本和设备应用列表独立核对，devicectl 启动成功。未卸载或清空容器。

直接镜像发布 CloudRun022 / task 2352734 也失败。平台启动日志明确返回 python 无法读取 /opt/remember/infra/cloudbase/runtime/launch.py，Errno 13 Permission denied。原因是本轮 ZipFile.writestr 默认生成 0600 源文件，并被镜像 COPY 保留，运行用户 remember 无法读取。这是本轮打包缺陷；不把失败归于供应商或通话业务。

修正所有归档成员权限为 0644，并在已有镜像基础上修正 runtime、Backend / AI 源码和 schema 的读取权限；依赖和已下载模型保留。逐成员权限检查通过。修正版 SHA256 16e5823cfd5ce8a6fe8fd7c6b558f66076d24917b934b29ab193cb078edb6b2e，任务 2352744 已提交，待实际上线验证。

修正后的 CloudRun023 / task 2352744 CreateVersion、ReleaseVersion 均 finished。实际 HTTPS service-info 为 ios-default-voice-6cb7c17，ready 为 database / object_store ok。原服务、配置、Worker 和数据库保留，未执行迁移。

真实 HTTPS 合成试听通过：HTTP 200，单声道 24 kHz、116640 帧，Cache-Control 包含 no-store；匿名 401。首轮验证误要求 header 严格等于 no-store，被网关追加的 no-cache / must-revalidate / max-age=0 导致断言失败，已改为检查 no-store 语义并复验通过。仅使用系统预置音色和隔离 QA，未复刻真人；预置引用先清空，再撤销新 VOICE，HTTP 200，profile missing。报告 build/voice-preview-live-proof.json。

公开 default 模式的真实 RTC 单轮通过：无本人 clone 时取得默认 ticket、连接 RTC、Worker / ASR 就绪、收到 CONVERSATION 回答、接收 6 帧非零输出音频。整体监听事件在 23.472 秒、问题 27.124 秒、回答 / speaking 38.320 秒；不等于真人手机停说到听见的延迟。结束和新 VOICE 撤销均 HTTP 200，专用测试 turn 已按 answer_id + Actor / Subject 删除，个人 profile 仍 missing。报告 build/default-voice-live-proof.json。本次未重复既有三轮 / 65 秒测试，也未把系统预置音色或 UI fixture 当成本人克隆与真人验收。

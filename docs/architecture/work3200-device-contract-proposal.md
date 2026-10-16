# WORK_3200 Android 首次设备联调（2026-10-16）

用户在换机交接后明确要求：实体录音豆已到手，先完成 App 内扫描、连接、绑定和真实录音下载，提供可直接安装的 APK，无需 USB 调试。本次按这一范围继续原有准备模块。

新增接口 `POST /api/v1/hardware/work3200/credentials`。请求为 `{device_id: "rm-install-<UUID>"}`；必须使用现有登录凭据。服务端从已认证 Actor 取得厂商 user_id，拒绝客户端传入 user_id 或其他额外字段。返回 version、environment、user_id、device_id、token、token_expire_time、license_json、license_signature；响应不缓存。业务 app_key 只保存在服务端配置中，授权失败不回显厂商响应或密钥。

私有资料包实测：测试环境 code=1 返回授权；正式环境拒绝本批 app_id。默认 DEVELOPMENT，固定厂商域名，不允许客户端指定任意授权地址。SDK 仍负责校验厂商签名，App 先核对当前账号、手机安装标识和有效期。

线上接口未部署时，可使用 App 导出的本机申请和 `services/backend/tools/work3200_provision.py` 生成短期授权文件，再由手机选择文件导入。授权文件不能跨账号或跨安装使用，缓存由 Android Keystore 加密；业务密钥不能导入 App。

本次不改变现有 Episode/Consent/Subject 契约，不自动上传、不远程启动录音、不删除设备录音。设备下载保存在账号和人物隔离的本机导入日志中；完成回调还需经过目录约束、非空文件检查和 SHA-256 校验，才能显示手机已保存。原始文件和试听衍生 WAV 分开保留。重复下载保留同一导入身份；同一设备文件 ID 返回不同字节时明确拒绝。

音频解码按官方 1.3.02 文档的 160 字节/20 ms Opus 分包处理，校验 TOC 帧时长并通过 Android MediaCodec 解码为 PCM WAV，核对输出格式和总时长。格式不符时保留原件并提示导出，不把文件改名当作完成解码。模拟器合成音频检查与实物音频验收分别记录。

SDK 是可选私有构建依赖，由 `rememberSoundcoreSdk` 指定本地 AAR。未提供时构建保留明确不可用状态；设备发布构建必须启用 `rememberRequireHardwareSdk=true`。既有主 App 与 iOS 行为保留。

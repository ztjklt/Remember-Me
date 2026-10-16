# 未复刻时使用默认声音通话

2026-10-14，Product / Integration Owner 明确批准“允许默认声音先通话，复刻好后再切换”。本提案授权同一实时通话服务的默认声音模式；不更换供应商，不向默认模式发送本人复刻样本。

v0.8 在 capabilities 增加可选 default_voice_available；通话请求增加可选 voice_mode（personal / default，省略仍为 personal）；ticket 返回选用模式。默认模式仍要求 CLOUD_TWIN、声音用途确认及独立 VOICE 许可，但无需声音样本或就绪克隆。客户端明确显示默认声音，不冒充本人原音。

后台以 rvp_default_ 前缀的内部 Profile 绑定已授权默认声音通话，沿用现有 VoiceCall 权限和结束处理，无新迁移。此类记录不出现在本人音色查询、不阻止以后复刻。撤销默认声音许可只删除本地引用，永远不请求供应商删除系统预置音色。已就绪的本人音色可用于后续通话；进行中的通话保持原选用模式。

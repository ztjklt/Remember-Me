# AWS 部署准备与实际验证

状态：本地部署准备已经落地，**AWS 实例、S3、实例角色和公网入口尚未创建**。
源码基线99c2294，工作区为Remember Me的codex/agent-integration；未push/merge。

## 本轮修复

1. PostgreSQL原来的SERIALIZABLE设置不能独自保护“最终来源校验→保存答案”区间。
   新独立线程探针先复现普通写入穿过该区间，再改为短事务内锁定已映射表的DML。
   来源写入、授权和后台worker因此共享保守的一致性边界。模型调用仍在事务外。
   代价：测试版的写入会全局串行；不宣称已满足大规模并发吞吐。
2. PostgreSQL锁超时原先会成为500；现在SQLSTATE 40001/40P01/55P03返回
   409 STATE_CONFLICT，其他数据库运行错误返回503。响应不包含SQL、参数或密钥，
   不会自动重放一次已经完成的模型调用。
3. PostgreSQL连接使用宿主机时区，曾使同一个confirmed_at在初次返回和重新读取时
   分别为UTC和+08:00，破坏重复确认的一致输出。连接设UTC，as_utc也正确转换偏移。
4. Linux检索依赖显式锁定CPU torch。安装日志确认torch2.14.1+cpu，删除不需要的
   Linux CUDA依赖。Windows安装仍由相应平台的锁定包决定。
5. 独立审查发现S3角色漏掉healthcheck/probe；为该精确对象补齐读写删除权限，
   通过实际S3ObjectStore.healthcheck配合受模板策略约束的本地对象桩回归。
   这验证静态权限覆盖，不代替真实AWS IAM/S3验收。
6. 发布包改为指定源码目录、静态资源及命名模板白名单；实际.env、SQLite、dump和
   未知配置不打包。清单描述筛选/扫描策略，不再无条件宣称所有内容必然没有凭据。
7. 模型预热读取api.env，实际systemd临时单元在HF_HUB_OFFLINE=1下完成编码。
   本地单元使用测试用户及缓存目录，不冒称已完成云主机rememberme用户整体激活。
8. 代理上限调整为28MB，覆盖后端25MiB及multipart封装；补齐本地Linux测试环境
   的数据库角色、完整源码、依赖和root前置条件。两个Minor均处理，无留待项。

## 实测结果与证据边界

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Windows/SQLite后端 | 365通过，3个PG专属测试跳过 | var/aws-sqlite-final.log |
| Ubuntu24.04/PostgreSQL16后端 | 368通过 | var/aws-pg-fixed.log |
| 实际Caddy HTTPS、账号及恢复 | 13项通过 | var/aws-https-smoke-final.log |
| CPU中文检索模型 | 同一固定revision，512维输出成功，峰值RSS约503MiB | var/aws-embedding-offline.log |
| 发布包/部署权限回归 | Linux 6通过；Windows 5通过、链接权限检查跳过1项 | tools/test_cloud_package.py、tools/test_aws_deployment.py |
| systemd离线预热 | 实际EnvironmentFile配置与编码通过 | var/aws-systemd-prewarm.log |
| CloudFormation静态检查 | cfn-lint通过 | infra/aws/pilot.yaml |
| Linux脚本语法 | bash -n通过 | infra/aws/*.sh |

上述var路径相对services/backend且受Git忽略。PG设置使用随机schema，每次测试独立迁移；
显式构造SQLite的旧测试仍用SQLite，不能把368项都称为PG专用探针。

13项真实网络检查包括：客户端验证本地CA证书、工作台可打开、隐藏接口文档、Secure+
HttpOnly+SameSite Cookie、伪造转发头无效、空间鉴权、跨域写入被拒绝、API重启后
账号及会话保留、pg_dump恢复到另一独立数据库后账号和Owner空间一致、退出失效、
重新登录、错误Origin被拒绝、staging拒绝明文HTTP登录。
CA只由测试客户端信任，没有安装系统根证书。本组测试没有ASR或文本模型调用。

保留失败记录：var/aws-pg-full.log的两个时区错误、旧publication探针和锁超时的先失败
记录。HF首次在线下载出现连接重置(var/aws-embedding-smoke.log)，没有更换模型；
从本机既有同revision公共模型缓存加载，在HF_HUB_OFFLINE=1下验证成功。
这证明CPU运行，不证明未来AWS到模型下载站的网络正常。
审查修复前已分别观察到打包泄漏边界、readiness对象权限、预热缺EnvironmentFile
三个回归失败；修复后Linux六项通过。最终Caddy配置再次通过13项实际TLS演练。

## 可审查交付

- infra/aws/pilot.yaml：单机、私有S3、SSM实例角色、仅80/443的可选入口。
- infra/aws/prepare-host.sh、activate.sh、run-service.sh、systemd文件及Caddyfile。
- 各服务独立配置模板；模型密钥仅服务端，未写入模板或打包。
- tools/package_cloud.py：源码白名单、凭据检查、运行目录排除、路径/链接拒绝。
- tools/aws_linux_smoke.py：可重复的Linux实测脚本。
- infra/aws/backup.sh：数据库本地备份和私有S3上传；**上传尚待真实AWS测试**。
- output/aws/remember-me-cloud.tar.gz及其manifest：源码部署包，不含数据库/音频/账号。

部署选择：单台Linux使用systemd，减少Docker运行层维护；代价是更依赖明确的Ubuntu
版本和安装步骤。Windows混合.env和路径不复用，云端按服务配置；代价是需要一次独立配置。
短事务全表DML锁优先保证当前证据一致性，代价是小试点的写入吞吐受限，需后续压测。

## 拟创建资源和费用口径

区域ap-southeast-1，新加坡。Ubuntu24.04，1台t3.medium（2核4GiB）、40GiB加密gp3、
一个固定IPv4、一个私有S3桶。选择4GiB是基于当前小规模串行模型调用及CPU检索加载
结果，不是多人压测结论。无GPU、RDS、NAT Gateway或负载均衡器。

2026-10-08控制台显示t3.medium Linux按需US$0.0528/小时；[AWS IPv4价目](https://aws.amazon.com/vpc/pricing/)
为US$0.005/小时。两者合计US$1.3872/天；从10月8日至31日按不超过24天估算约US$33.30，
另有磁盘、S3请求/存储及流量。建议首轮AWS预算US$50，预计小规模测试约US$35–45；
这是估算和拟议预算，不是已配置的硬性扣费上限。外部Groq/微信费用不由AWS抵扣金覆盖。
目前看到的活动US$200抵扣金到期日是2026-10-31，不能假定11月仍可用。

访问范围：网页和APP走HTTPS；80用于证书验证/跳转，443为登录后的业务API。
数据库、AI Core、worker不开放公网端口；S3保持私有；运维使用SSM、不开放SSH。
EC2角色只访问本项目桶的指定前缀，不授予账户管理员权限。
密钥待通过安全配置进入该EC2，不在UserData、SSM命令正文、日志或安装包中出现。

创建前仍需：具体资源/费用/访问范围确认、域名或替代HTTPS入口选择、账号创建权限及
活动区域限制核验。当前控制台仅有未提交表单，不能把它当作已创建服务器。

## 后续验收不能省略

1. AWS到Groq/微信实际网络与鉴权；私有S3上传、哈希回读、撤权后拒绝访问。
2. 真实云端录音→核对/手工补充→整理保存→人物候选→问答和两身份循环。
3. 定时备份、完整远端恢复、磁盘监控与到期迁移；本轮只验证了本地数据库恢复。
4. 最终HTTPS地址的Android安装包、手机移动网络、真人麦克风测试；iOS仍需Mac。
5. Agent质量：现有v6的35支持/24质量问题/1漏答仍有效，本次没有修改模型提示或
   重跑这60题，不能把部署/数据库通过改写成回答质量全部通过。

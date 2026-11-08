# AI 远程配置与客户端直连需求索引

日期：2026-11-08；状态：需求设计，尚未实现。

三端唯一主文档位于 TravelDiaryClient：

[AI远程配置与客户端直连完整需求](../../../../TravelDiary/TravelDiaryClient/需求文档/AI画布排版/27-AI远程配置与客户端直连完整需求.md)

选择服务端下发配置、客户端直连供应商，不恢复 AI 网关。服务端拟新增 ai_runtime 应用，复用 ai_production 任务与额度；后台新增 AI 服务配置，保留 AI 制作额度页面。具体数据表、公共/管理 API、权限、发布、凭证轮换、兼容迁移与验收以主文档为准。

该相对链接按当前 TravelDiary 与 Reference/SparkService 同属 project 的工作区结构解析；独立检出服务端仓库时，应按上方文件名到客户端仓库查阅，不复制维护第二份需求。

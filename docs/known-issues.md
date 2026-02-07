
# known-issues

P0 缺少 API 鉴权与租户隔离，job_id 可直接读写任务。证据：main.py (line 33)、jobs.py (line 22)、repository.py (line 36)。风险是任意调用方可查询/中止/下载他人任务。

P1 /start 存在并发竞态，可能重复入队同一任务并并发执行。证据：orchestrator.py (line 140)、orchestrator.py (line 147)、orchestrator.py (line 151)、repository.py (line 166)。当前状态更新不是“带前置状态条件”的原子操作。

P1 状态机约束不完整，abort 可覆盖终态。证据：orchestrator.py (line 165)、orchestrator.py (line 171)、repository.py (line 179)。这会导致 succeeded/failed -> aborted，破坏终态语义与审计一致性。

P1 权限处理未按 sessionID 过滤，可能误回复其他会话的权限请求。证据：executor.py (line 327)、opencode-api.json (line 3145)。OpenCode 的 /permission 是跨会话待处理列表，当前实现会遍历并回复全部请求。
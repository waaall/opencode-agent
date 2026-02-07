## 问题审查

```
使用 Vercel React Best Practices skill
根据现在的后端设计 backend-design.md  overall-design-plan.md  overall-damand.md ；
审查现在的 frontend-build-plan.md 前端设计文档。
```



## 不向后兼容的修复问题

```
修复如下这几个问题：

1. 存在 main.py 使用 @app.on_event("startup")，在当前 FastAPI 版本属于已弃用路径（推荐 lifespan）。
2. container 中依赖基本都是 @lru_cache 单例（container.py 等），同时 OpenCodeClient 每次调用重建 httpx.Client（client.py 等），性能上确实不理想。线程安全本身问题不大，主要是效率问题。
3. client.py 各方法都 with httpx.Client(...)，在高频轮询路径（executor.py ）开销明显。
4. jobs.py 是 async 生成器，但里面直接调用同步 DB 路径，会阻塞事件循环。
5. executor.py 只做轮询；event_bridge 实现了但未被引用（event_bridge.py ，全项目无调用）。与设计文档“订阅 /event + 补偿轮询”不一致（design-plan-detail.md ）。

注意，当前设计还没有开始测试，更没有开始使用，所以不用向后兼容，老旧的不好的设计直接修改就行。
```

修改完了如果检查没有问题，就同步文档：

```
将改动 同步到 文档 @docs/backend-design.md
```


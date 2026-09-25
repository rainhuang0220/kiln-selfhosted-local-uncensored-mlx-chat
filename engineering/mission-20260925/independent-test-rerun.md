# 独立子 Agent 重跑

本文件由独立测试复核子 Agent 写入，不是实现者，也不是人类审核员。未改源码、未重启 8081/8787、未向 MLX 发请求、未删除文件。未改测试。

## backend

- 工作目录：`/Users/rainhuang/Desktop/models/kiln/backend`
- 命令：`/Users/rainhuang/Desktop/models/kiln/.venv/bin/python -m pytest -q -k 'not test_wan_teacache_module_imports'`
- 计入结果的一次结束于 2026-09-25 13:14:47
- 退出码：`0`
- 原文摘要：`278 passed, 1 deselected in 79.77s (0:01:19)`
- 失败测试：无

同目录更早一次（约 13:12）在 `app/services/context_route.py` 落盘前收集中断（该文件 mtime 13:12:29），退出码 `2`，不是断言失败，不计入上面的通过数。原文：

```
ERROR tests/test_context_route.py
E   ModuleNotFoundError: No module named 'app.services.context_route'
1 deselected, 1 error in 0.12s
```

## web

- 工作目录：`/Users/rainhuang/Desktop/models/kiln/web`
- 命令：`./node_modules/.bin/vitest run src/api/sse-fuzz.test.ts src/api/sse-assembly.test.ts src/stores/chat-store.test.ts src/lib/service-banner.test.ts src/components/SidebarFooter.test.tsx`
- 开始：2026-09-25 13:12:17
- 退出码：`0`
- 原文摘要：

```
 ✓ src/api/sse-assembly.test.ts (5 tests) 2ms
 ✓ src/lib/service-banner.test.ts (5 tests) 2ms
 ✓ src/stores/chat-store.test.ts (12 tests) 8ms
 ✓ src/components/SidebarFooter.test.tsx (11 tests) 11ms
 ✓ src/api/sse-fuzz.test.ts (2 tests) 137ms

 Test Files  5 passed (5)
      Tests  35 passed (35)
   Duration  428ms (transform 162ms, setup 0ms, collect 352ms, tests 160ms, environment 0ms, prepare 276ms)
```

- 失败测试：无

# A5 正在跑的模型（2026-09-25）

只读。核对时刻 **2026-09-25 02:06 CST**。没有下载，没有把任何检查点加载进 MLX，没有调用生成接口。

## 进程

只有一个 `mlx_lm.server`：PID **1581**，父进程 1，`etime` **13-06:16:02**。命令行：

```
/opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -m mlx_lm.server --model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4 --host 127.0.0.1 --port 8081 --max-tokens 32768 --temp 1.0 --top-p 0.95 --top-k 20 --decode-concurrency 1 --prompt-concurrency 1 --prefill-step-size 1024 --prompt-cache-size 4 --prompt-cache-bytes 4G --chat-template-args {"enable_thinking":false,"reasoning_effort":"medium"}
```

`--model` 指向 `/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`。该目录 `du -sh` 为 **5.3G**。

## README 里的 uncensored

权重目录 `README.md` 仍然自称 uncensored：front matter 标签含 `uncensored` / `unrestricted` / `decensored`；正文写 “Qwen3.5-9B uncensored by HauhauCS.”，以及 “**0/465 refusals.** Fully uncensored with zero capability loss.” 同页还写模型不会拒绝，但回答末尾仍可能加免责声明，并说那不是拒绝。

**0/465 不是本机测量。** 这次没有跑拒答集，不把这个数字写成拒绝率。

Kiln 自己的 `README.md` 第 28 行用名字 “Qwen3.5-9B Uncensored Aggressive” 指默认模型；第 23 行写不要把 “uncensored” 读成「总是听从提示」。`MODEL.md` 写上游卡片声称 `0/465`，并写 Kiln 没有重跑那套测试。仓库文档没有把 0/465 当成已测结果。

## `~/.mtplx` 的 4B

有。目录是 `~/.mtplx/models/Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed`，`du -sh` 为 **2.4G**。同层还有 `Youssofal--Qwen3.5-9B-MTPLX-Optimized-Speed`。两者都没有加载。

## GGUF

`find /Users/rainhuang/Desktop/models -maxdepth 3 -iname '*.gguf'` 结果为 **0**。只搜了这一层深度，没有再往下找，也没有启动 llama.cpp。

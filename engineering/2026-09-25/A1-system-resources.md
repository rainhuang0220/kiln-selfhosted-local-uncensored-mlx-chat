# A1 系统资源（只读）

采样：2026-09-25 02:41:30–02:47:17 CST。只读，无 sudo。未重启、未 kill、未 purge、未 launchctl、未删文件、未请求 MLX 生成、未跑 GPU/20K。

总控 02:36 快照里的 swap used 13270.06M、PID 1581 RSS 约 7616KB，下面全部是本次重测，不是照抄。

## finding

**不可压测。** 不要派 A4 做 GPU/20K。

压力来源能分开，不是无法分辨：

- 交换区存量是历史残留，测量窗口内没有在增长。02:41:30 与 02:41:46 的 `vm.swapusage` 都是 used 13262.06M、free 1073.94M，`Swapouts` 都是 73343490。随后 02:43:30 used 13246.06M，02:47:17 used 13238.06M，是略降。
- 当前并不处于 normal。`kern.memorystatus_vm_pressure_level` 从 02:41:30 到 02:47:17 一直是 2。按公开的 userspace 映射，这个 sysctl 的 2 是 warn（见 evidence 的出处限制）。空闲页只有约 78–92 MiB。压缩机物理占用约 10.93 GiB。
- PID 1581 的 `ps` RSS 只有 13632 KB（02:45 复读 13712 KB），但 02:43:29 的 `footprint` `phys_footprint` 是 **5154 MB**（peak 9215 MB）。其中 IOAccelerator (graphics) 4879 MB，且该行的 swapped/compressed 列也是 4879 MB。`vmmap -summary` 同一秒写出 Physical footprint 5.0G、writable `swapped_out=5.0G`，DIRTY 合计只有 13.5M，和 RSS 同量级。所以「RSS 约十几 MB」不表示模型账本已卸掉，也**不**表示这 5.1GB 正以未压缩 DRAM 常驻。它仍记在该进程的 phys_footprint 上，而且工具把它标成 swapped/compressed。

因此不是「只剩历史 swap、现在可以压」。把约 5.1GB 账本拉回统一内存再加 20K KV，剩余 swap 只有约 1.07–1.10 GiB，兜不住。进程 argv 还有 `--max-tokens 32768` 和 `--prompt-cache-bytes 4G`，服务端配置不会替这次压测拒绝长上下文。这是 argv，不是实测缓存占用量。

已测集合里 `phys_footprint` 最大的五个：1581 mlx_lm.server 5154 MB，94952 zotero 4483 MB，1429 Finder 1102 MB，20558 Chrome Helper 543 MB，1784 Chrome Helper 518 MB。`footprint -a` 需要 root，未做全机扫描，不能证明没有另一个低 RSS、高 footprint 的进程；RSS 排序会漏掉 1581 本身。

## evidence

机器：`hw.model=Mac16,1`，`hw.memsize=25769803776`（24 GiB），`hw.pagesize=16384`。`vmmap` 报告头：macOS 26.5 (25F71)。PID 1581 由 launchd 拉起，Launch Time 2026-09-11 19:50:33 +0800。

### 未执行的命令

`memory_pressure` 无参数会分配内存并一直等待，本次没有跑，也没有用 `-l` / `-p` / `-S`。

```text
Usage: memory_pressure [options] [<pages>]
  Allocate memory and wait forever.
  -l <level> - allocate memory until a low memory notification is received (warn OR critical)
  -p <percent-free>     - allocate memory until percent free is this (or less)
  -S - simulate the system's memory pressure level without applying any real pressure
```

二进制里有格式串 `System-wide memory free percentage: %d%%`，但帮助文本没有「只打印然后退出」的开关。压力改用下面的 sysctl 和 `vm_stat`。

`sysctl -d`：`vm.memory_pressure` 的说明只有 “Memory pressure indicator”。`kern.memorystatus_vm_pressure_level` 和 `kern.memorystatus_level` 的说明为空。本机没有对照头文件。公开映射（Firefox `AvailableMemoryWatcherMac.cpp`、psutil #2725 对 XNU 的引用）把该 sysctl 定为 1=normal、2=warn、4=critical。XNU `memorystatus_notify.md` 里的内部档（0 normal、1 warning、2 urgent）不是这个 sysctl 的返回值。下文把测到的 2 记为 warn，受这个出处限制。

`kern.memorystatus_level` 在 02:41 为 38、02:47 为 40。Firefox 非正式地把它当成可用内存百分比；同日 `engineering/2026-09-25/agents/A1-hardware.md` 在 02:06 写过它与 memory_pressure 的 free percentage 同为 40。本次没有重跑 memory_pressure，所以这里只记录 sysctl 原值。它不是 `Pages free`（约 78–92 MiB），也不是 swap free（约 1.07 GiB）。

`machdep.xcpm.cpu_thermal_level`：`sysctl: unknown oid`。`sysctl -a` 再滤 `thermal|xcpm|cpu_power|soc_temp` 无输出。到此停止，没有再猜 oid。

`powermetrics -n 1 -i 1000 -s thermal` 只跑了一次：`powermetrics must be invoked as the superuser`。未 sudo，未重试。更早一次 `-s smc` 是 “unrecognized sampler”，没有进入权限检查。

`footprint -a --noCategories --minFootprint 80`：`footprint: Must run as root.` 未 sudo。

### swap 与压力档

官方一对（16 秒，覆盖所要求的约 15 秒）：

```text
=== SAMPLE A 2026-09-25 02:41:30 CST ===
vm.swapusage: total = 14336.00M  used = 13262.06M  free = 1073.94M  (encrypted)
vm.memory_pressure: 231
kern.memorystatus_vm_pressure_level: 2
kern.memorystatus_level: 38

=== SAMPLE B 2026-09-25 02:41:46 CST ===
vm.swapusage: total = 14336.00M  used = 13262.06M  free = 1073.94M  (encrypted)
vm.memory_pressure: 449
kern.memorystatus_vm_pressure_level: 2
kern.memorystatus_level: 38
```

后续读数（不是那一对，用来看方向）：

```text
=== CORRELATE 02:43:30 ===
vm.memory_pressure: 0
vm.page_free_wanted: 0
vm.swapusage: total = 14336.00M  used = 13246.06M  free = 1089.94M  (encrypted)
kern.memorystatus_vm_pressure_level: 2
kern.memorystatus_level: 38

=== 02:47:17 ===
vm.swapusage: total = 14336.00M  used = 13238.06M  free = 1097.94M  (encrypted)
vm.memory_pressure: 0
vm.page_free_wanted: 0
kern.memorystatus_vm_pressure_level: 2
kern.memorystatus_level: 40
```

02:43:30 和 02:47:17，`vm.memory_pressure` 与 `vm.page_free_wanted` 都是 0。02:41 那一对的 231 和 449 没有同时采 `vm.page_free_wanted`，不能把它们写成 wanted pages。离散压力档两次都是 2，这个指标却在动。

相对总控 02:36 的 used 13270.06M，02:41 实测是 13262.06M，低 8.00M。同日 A1-hardware.md 在 02:06 记录 used 12906.12M、level 40；那是另一份文件里的数字，不是本次采样。本次窗口内 used 不升。

### vm_stat

页大小 16384。换算只用于阅读：MiB = pages × 16 / 1024。原始页数以下面两段为准。

```text
=== VM_STAT A 2026-09-25 02:41:30 CST ===
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                     5899.
Pages active:                                 289631.
Pages inactive:                               287954.
Pages speculative:                               919.
Pages throttled:                                   0.
Pages wired down:                             218103.
Pages purgeable:                                 132.
"Translation faults":                    16593161051.
Pages copy-on-write:                      1317540577.
Pages zero filled:                       12283364575.
Pages reactivated:                        1870218356.
Pages purged:                              421401442.
File-backed pages:                            248945.
Anonymous pages:                              329559.
Pages stored in compressor:                  2960652.
Pages occupied by compressor:                 716251.
Decompressions:                           1885320365.
Compressions:                             2278278548.
Pageins:                                   439417159.
Pageouts:                                    4375191.
Swapins:                                    53426454.
Swapouts:                                   73343490.
```

A 的换算：free 92.17 MiB，active 4525.48 MiB，inactive 4499.28 MiB，speculative 14.36 MiB，wired 3407.86 MiB，compressor 逻辑页 46260.19 MiB，compressor 物理占用 11191.42 MiB（10.93 GiB）。anonymous 5149.36 MiB，file-backed 3889.77 MiB。上述 free+active+inactive+speculative+wired+compressor occupied = 1518757 页；24 GiB 对应 1572864 页，差额 54107 页（845.42 MiB）不在这六项里，没有拿别的类别去凑。

```text
=== VM_STAT B 2026-09-25 02:41:46 CST ===
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                     4977.
Pages active:                                 291438.
Pages inactive:                               289804.
Pages speculative:                               513.
Pages throttled:                                   0.
Pages wired down:                             218094.
Pages purgeable:                                   2.
"Translation faults":                    16593365224.
Pages copy-on-write:                      1317573293.
Pages zero filled:                       12283417500.
Pages reactivated:                        1870219478.
Pages purged:                              421403755.
File-backed pages:                            245961.
Anonymous pages:                              335794.
Pages stored in compressor:                  2953242.
Pages occupied by compressor:                 714162.
Decompressions:                           1885327816.
Compressions:                             2278278556.
Pageins:                                   439418434.
Pageouts:                                    4375230.
Swapins:                                    53426490.
Swapouts:                                   73343490.
```

B−A：Swapouts +0，Swapins +36 页（576 KiB），Compressions +8，Decompressions +7451 页，Pageouts +39，Pageins +1275。free 5899→4977 页（92.17→77.77 MiB）。compressor occupied 716251→714162 页（约 −32.6 MiB）。swap 显示值仍是 13262.06M；36 页没有把 used 从 0.01M 分辨率上移开。

### 监听与四个目标进程

`lsof -nP -iTCP -sTCP:LISTEN`：

```text
:8081  Python  1581  TCP 127.0.0.1:8081 (LISTEN)
:8787  Python 15068  TCP 127.0.0.1:8787 (LISTEN)
:7777  node   97771  TCP 127.0.0.1:7777 (LISTEN)
:7777  ClashX 59877  TCP 198.18.0.1:7777 (LISTEN)
:8000  Python 95938  TCP 127.0.0.1:8000 (LISTEN)
```

7777 上 Kiln vite 与 ClashX 不是同一个套接字。

`ps` RSS 单位是 KB。02:41:30：

```text
  PID  PPID USER      ELAPSED      STAT   RSS      VSZ  COMM
 1581     1 rainhuang 13-06:50:57  S     13632 440630304  Python
15068     1 rainhuang 09-13:32:59  S     31120 435401520  Python
95938     1 rainhuang 12-04:48:09  S      9408 435330416  Python
97771 97755 rainhuang 14-07:21:31  S     13312 444661664  node
```

argv 里没有密钥或 `.env` 内容。缩短后的标识：

- 1581：`Python -m mlx_lm.server --model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4 --host 127.0.0.1 --port 8081 --max-tokens 32768 --temp 1.0 --top-p 0.95 --top-k 20 --decode-concurrency 1 --prompt-concurrency 1 --prefill-step-size 1024 --prompt-cache-size 4 --prompt-cache-bytes 4G --chat-template-args {"enable_thinking":false,"reasoning_effort":"medium"}`
- 15068：`Python -m uvicorn app.main:app --host 127.0.0.1 --port 8787`
- 95938：`Python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`（python@3.14）
- 97771：`node .../kiln/web/node_modules/.bin/vite --host 127.0.0.1 --port 7777 --strictPort`
- 子进程 97772 esbuild，02:41:30 RSS 18544 KB，未单独 footprint

02:45 的 mlx 行里 1581 RSS 为 13712 KB。总控快照的约 7616 KB 与本次 13632 KB 不一致，但都是十几 MB，不是数 GB。

`footprint` 帮助：`--swapped` 是 “show swapped/compressed column”。表头印的是 `(Swapped)`，不能把它读成「纯磁盘交换、不含压缩」。

```text
=== FP1581 2026-09-25 02:43:29 CST ===
footprint -p 1581 --swapped --wired
Python [1581]: 64-bit    Footprint: 5154 MB (16384 bytes per page)
  Dirty  (Swapped)      Clean  Reclaimable    (Wired)    Regions    Category
4879 MB    4879 MB        0 B          0 B        0 B       1144    IOAccelerator (graphics)
  91 MB      89 MB        0 B          0 B        0 B         72    MALLOC_SMALL
  86 MB      86 MB        0 B          0 B        0 B          7    MALLOC_LARGE
  85 MB      80 MB        0 B          0 B        0 B         97    untagged (VM_ALLOCATE)
 ...
5154 MB    5141 MB    4272 KB          0 B        0 B       4275    TOTAL
phys_footprint: 5154 MB
phys_footprint_peak: 9215 MB
```

中间类别都小于 3 MB，上表用 `...` 省略；合计行与 graphics 行是原文。graphics 的 Dirty 与 (Swapped) 都是 4879 MB。TOTAL 的 (Swapped) 是 5141 MB，占 5154 MB footprint 的绝大部分。

另外三个，`footprint -p --noCategories`，同一分钟：

```text
Python [15068]: phys_footprint 112 MB, peak 244 MB
node   [97771]: phys_footprint 116 MB, peak 163 MB
Python [95938]: phys_footprint  72 MB, peak  73 MB
```

`vmmap -summary 1581`，Date/Time 2026-09-25 02:43:29.690 +0800：

```text
Physical footprint:         5.0G
Physical footprint (peak):  9.0G
Writable regions: Total=5.3G written=267.1M(5%) resident=4.8G(90%) swapped_out=5.0G(94%) unallocated=16777216.0T(322554494976%)

REGION TYPE                 VIRTUAL RESIDENT DIRTY SWAPPED VOLATILE NONVOL EMPTY COUNT
IOAccelerator (graphics)       4.8G     4.8G    0K    4.8G       0K   4.8G 4496K  1144
TOTAL                          6.4G     5.0G 13.5M    5.0G       0K   4.8G 4496K  3488
```

`ps` RSS 13632 KB ≈ 13.3 MiB，对得上 vmmap TOTAL DIRTY 13.5M，对不上 RESIDENT 5.0G，也对不上 footprint 5154 MB。vmmap 的 RESIDENT 列和 ps RSS 不是同一个量。graphics 行是 resident 列 4.8G、dirty 0K、swapped 4.8G。writable 行同时写 resident=4.8G 和 swapped_out=5.0G。footprint 的列按帮助是 swapped/compressed 合并。两份工具都说明这约 5GB 不在普通 dirty RSS 里；它们没有给出「其中多少字节在磁盘 swap、多少在压缩机」的可加总拆分。系统级 compressor occupied 约 10.93 GiB 是另一本账，不要和 1581 的 4879 MB 相加。

### RSS 前 15 与 footprint

`footprint -a` 失败，下面不是全机 footprint 排名。RSS 在采样期间不稳定：02:41:30 zotero RSS 907472 KB、deja 27408 RSS 468656 KB；02:45:29 zotero 1588496 KB，deja 已降到 88544 KB（footprint 102 MB，peak 448 MB）。swap used 在这段时间没有上升。

02:45:29 `ps -axo pid,rss,etime,comm -m` 前 15。RSS 是这一瞬间的 KB。footprint 在随后逐个 `footprint -p --noCategories` 取得，单位用工具原文 MB。20558 与 10814 的 footprint 在 02:47:17，紧挨着的 `ps` RSS 分别是 105872 KB 和 91184 KB。

```text
pid    rss_KB  phys_footprint     peak     comm
94952  1588496 4483 MB            6215 MB  zotero
95873   354576  440 MB            1044 MB  Cursor Helper (Renderer)
50278   350512  461 MB             647 MB  Google Chrome
12858   221984  292 MB             363 MB  grok
77195   207360  515 MB             694 MB  Codex (Renderer)
76721   189056  308 MB             746 MB  ChatGPT
1429    183920 1102 MB            1270 MB  Finder
10795   174736  177 MB             215 MB  QQ
93459   172032  200 MB             734 MB  Cursor
1784    171488  518 MB             682 MB  Chrome Helper (Renderer)
77788   120272  280 MB             383 MB  Codex (Renderer)
61465   116432  104 MB             133 MB  WeChatAppEx Helper (Renderer)
85502   114832  509 MB            1021 MB  Chrome Helper (Renderer)
20558   111472  543 MB            1896 MB  Chrome Helper (Renderer)
10814   111008  174 MB             213 MB  QQ Helper (Renderer)
```

12858 在 footprint 前一瞬间的 `ps -p` 是 226528 KB，榜单上是 221984 KB。77788 榜单 120272 KB，footprint 前 `ps -p` 是 120320 KB。

已测 `phys_footprint` 前五（含 1581，1581 不在 RSS 前 15）：

```text
1581   mlx_lm.server                 5154 MB   RSS 13632 KB（02:45 为 13712 KB）
94952  zotero                        4483 MB   RSS 1588496 KB
1429   Finder                        1102 MB   RSS 183920 KB
20558  Chrome Helper (Renderer)       543 MB   RSS 105872 KB（02:47:17）
1784   Chrome Helper (Renderer)       518 MB   RSS 171488 KB
```

02:41 RSS 榜上、02:45 已掉出前 15、但仍测了 footprint 的：19105 Chrome Helper，footprint 前 RSS 95216 KB，phys_footprint 183 MB，peak 312 MB。

## proposed change

本次不改代码、配置、launchd 或进程。

建议只给总控：在复测仍看到 swap free 约 1.1GiB、`kern.memorystatus_vm_pressure_level` 为 2、且 1581 的 phys_footprint 仍约 5.1GB 并几乎全在 swapped/compressed 列时，不要派 A4 做 GPU/20K。开跑前要重新采这三项，不要沿用本文件的数字。不要为了这份审计去改 MLX 的 cache 参数。

## risk

本次没有改系统状态。读 footprint / vmmap 会碰到这些进程的地址空间，但没有分配压力、没有生成。

误读风险：把 5154 MB 当成当前未压缩常驻，或把 RSS 13MB 当成权重已卸载。两个判断都和上面的并列数字矛盾。

若忽略本结论仍做 20K/GPU：1581 这约 5.1GB 账本需要回驻，进程还配置了 4G prompt cache；当时剩余 swap 只有约 1.07GiB，空闲页不到 100MiB，压力档为 warn。可能把最后的 swap 打满或触发 jetsam。本任务没有做这个实验，也没有量化回驻后的占用。

测量缺口：无 root，所以没有全机 footprint 排名，也没有 powermetrics / CPU 温度。15 秒窗口只能说明当时 swap 不增长，不能代表 02:06 到 02:36 之间曾经发生过的变化。

## tests

已做：`sysctl`（hw、swap、memory_pressure、memorystatus、page_free_wanted）、`vm_stat` 两次、间隔约 16 秒的 swap 一对、两次后续 swap 读数、`lsof` 四个端口、`ps`、四个目标 PID 加 RSS 前 15 的 `footprint -p`、`vmmap -summary 1581`、一次 `powermetrics`（权限失败）、一次 `footprint -a`（权限失败）。

未做：MLX 生成、GPU 压测、20K 预填充、`memory_pressure` 分配或模拟、`sudo`、purge、重启。

## rollback

没有服务重启，没有内存清除，没有文件删除，没有 git 写操作。没有需要回滚的运行状态。本文件是唯一新增产物；撤销它只会丢掉这份记录，不会改内存或进程。

## status

tested_live

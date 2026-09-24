# A1 macOS / 硬件审计

采样时间：2026-09-24 20:52–20:57 CST。只读，未改 Kiln 源码、plist、launchd，未向生成 API 发请求，未加载模型权重。原始输出在 `kiln/engineering/2026-09-24/raw/A1/`。

结论先说：这是 MacBook Pro（Mac16,1），Apple M4，10 CPU / 10 GPU，统一内存 24 GiB。采样时 jetsam 可用内存百分比约 36–37%，内核压力档为 **2（xnu 文档：Urgent，与 Warning 同义，不是 Critical）**。真正的 free pages 只有约 72–74 MiB。交换分区 16 GiB 里已用约 15.0 GiB。没有读到温度或热降频，不能声称正在热降频。正在服务 MLX 的解释器是 Kiln `.venv` 的 Python 3.12.12，不是 `/opt/homebrew/bin/python3`（3.14.7）。

## 机器摘要

| 项 | 读数 |
| --- | --- |
| 机型 | MacBook Pro，Model Identifier `Mac16,1`，Model Number `Z1JR000F7CH/A` |
| 芯片 | Apple M4；内核 `RELEASE_ARM64_T8132`；`hw.optional.arm64 = 1` |
| CPU | 10 核（4 Performance + 6 Efficiency）；`hw.physicalcpu = hw.logicalcpu = 10`（无超线程） |
| 内存 | `hw.memsize = 25769803776`（正好 24 GiB）；`hw.memsize_usable = 24904433664`（23.194 GiB）；system_profiler 写 `Memory: 24 GB` |
| 页大小 | `hw.pagesize = vm.pagesize = 16384` |
| 系统 | macOS 26.5（Build 25F71）；Darwin 25.5.0；xnu-12377.121.6~2；固件 / OS Loader `18000.120.36` |
| 主机名 | `rainhuangdeMacBook-Pro-7.local` |
| 开机 | `20:56` 时 `up 116 days, 8:19`；load average `3.49 3.37 3.20` |
| `hw.cpufamily` | system_profiler 打到 stderr：`0x6f5129ac` |

```text
ProductName:		macOS
ProductVersion:		26.5
BuildVersion:		25F71
Darwin rainhuangdeMacBook-Pro-7.local 25.5.0 Darwin Kernel Version 25.5.0: Mon Apr 27 20:41:26 PDT 2026; root:xnu-12377.121.6~2/RELEASE_ARM64_T8132 arm64
hw.memsize: 25769803776
hw.memsize_usable: 24904433664
hw.ncpu: 10
hw.physicalcpu: 10
hw.physicalcpu_max: 10
hw.logicalcpu: 10
hw.logicalcpu_max: 10
hw.optional.arm64: 1
machdep.cpu.brand_string: Apple M4
hw.pagesize: 16384
vm.pagesize: 16384
```

`system_profiler SPHardwareDataType`（含序列号 / UUID，原文保留）：

```text
Hardware Overview:

  Model Name: MacBook Pro
  Model Identifier: Mac16,1
  Model Number: Z1JR000F7CH/A
  Chip: Apple M4
  Total Number of Cores: 10 (4 Performance and 6 Efficiency)
  Memory: 24 GB
  System Firmware Version: 18000.120.36
  OS Loader Version: 18000.120.36
  Serial Number (system): [redacted]
  Hardware UUID: [redacted]
  Provisioning UDID: [redacted]
  Activation Lock Status: Disabled
```

## GPU

没有独立显存条。`SPDisplaysDataType` 只报内置 Apple M4 GPU，10 核，Metal 4。统一内存就是上面的 24 GiB，不是另一块 VRAM。

```text
Apple M4:

  Chipset Model: Apple M4
  Type: GPU
  Bus: Built-In
  Total Number of Cores: 10
  Vendor: Apple (0x106b)
  Metal Support: Metal 4
  Displays:
    Color LCD:
      Display Type: Built-in Liquid Retina XDR Display
      Resolution: 3024 x 1964 Retina
      Main Display: Yes
      Mirror: Off
      Online: Yes
      Automatically Adjust Brightness: Yes
      Connection Type: Internal
```

## 内存与交换

两套“空闲”不要混用：

- `kern.memorystatus_level` / `memory_pressure` 的 **System-wide memory free percentage** 是 jetsam 的可用内存百分比。20:53 为 **37%**，约 20:57 为 **36%**。
- `Pages free` 才是未使用页。20:53 `memory_pressure` 为 **4723** 页，紧接着的 `vm_stat` 为 **4639** 页。按 16384 字节/页：4639 页 = **72.48 MiB**，4723 页 = **73.80 MiB**。`Pages purgeable` 只有 2 页（32 KiB）。

`kern.memorystatus_vm_pressure_level` 两次都是 **2**。本机 SDK 头文件里没有搜到 `kVMPressure*`。xnu 文档 `doc/vm/memorystatus_notify.md`（apple-oss-distributions/xnu）把 `memorystatus_vm_pressure_level` 标成：0 Normal、1 Warning、2 Urgent（与 Warning 同义）、3 Critical、4 Jetsam。因此当前档是 **Urgent / Warning，不是 Normal，也不是 Critical**。`memory_pressure` 本身没有打印 `warn` 或 `critical` 这几个词；它的 `-l` 会施加压力，本次没有用。

`vm_stat`（20:53，页大小 16384）换算：

| 计数 | 页 | 约 |
| --- | ---: | --- |
| free | 4639 | 72.48 MiB |
| speculative | 2945 | 46.02 MiB |
| active | 282031 | 4.303 GiB |
| inactive | 278118 | 4.244 GiB |
| wired down | 229773 | 3.506 GiB |
| file-backed | 216497 | 3.289 GiB |
| anonymous | 346597 | 5.263 GiB |
| compressor 占用页 | 720838 | 10.999 GiB（物理） |
| compressor 中存放的页 | 3062918 | 46.736 GiB（压缩前逻辑页，不是物理占用） |
| purgeable | 2 | 32 KiB |
| throttled | 0 | 0 |

交换（加密）：

```text
# 20:53
vm.swapusage: total = 16384.00M  used = 15348.81M  free = 1035.19M  (encrypted)
# 20:56
vm.swapusage: total = 16384.00M  used = 15300.81M  free = 1083.19M  (encrypted)
```

即总共 16 GiB，已用约 14.94–14.99 GiB，剩余约 1.01–1.06 GiB。`Swapins: 52631520` 与 `Swapouts: 72505814` 是开机约 116 天以来的累计页数，不是当前速率。

```text
kern.memorystatus_level: 37
kern.memorystatus_vm_pressure_level: 2
System-wide memory free percentage: 37%
```

稍后 `kern.memorystatus_level` 变为 36，压力档仍为 2。

## 磁盘

`/` 与 `/System/Volumes/Data` 在同一 APFS 容器（926 Gi）。**可用 403 Gi 是同一块空闲，不能相加。**

```text
/dev/disk3s1s1   926Gi    12Gi   403Gi     3%   /
/dev/disk3s5     926Gi   476Gi   403Gi    55%   /System/Volumes/Data
/dev/disk3s6     926Gi    16Gi   403Gi     4%   /System/Volumes/VM
```

Data 已用 476 Gi，容器使用率 55%。另有多块小磁盘镜像挂在 `/Volumes` 与 `/private/tmp`，与系统盘空闲无关。

## 包版本

PID 1581 的 `ps` 命令行是 Homebrew Cellar 里的 Python.app（因为 venv 的 `python` 是指向该框架的符号链接，macOS 会改写 argv0）。环境里有 `__PYVENV_LAUNCHER__=/Users/rainhuang/Desktop/models/kiln/.venv/bin/python`，`XPC_SERVICE_NAME=com.kiln.mlx`，cwd 是 `/Users/rainhuang/Desktop/models/kiln`。已映射的原生库在 `kiln/.venv/lib/python3.12/site-packages/mlx/`（`core.cpython-312-darwin.so`、`libmlx.dylib`、`mlx.metallib`）。进程已运行 `13-01:08:51`。`ps` 当时 RSS 约 6752 KB；这不是 GPU wired 占用，`powermetrics` 没跑成，不能据此判断模型权重大小。

直接用 Cellar Python 3.12（不走 venv）导入失败，且 `/opt/homebrew/lib/python3.12/site-packages` 里没有 mlx：

```text
ModuleNotFoundError: No module named 'mlx'
WARNING: Package(s) not found: huggingface_hub, mlx, mlx-lm, mlx-metal, tokenizers, transformers
```

服务实际用的 venv（`uv = 0.10.0`，`version_info = 3.12.12`，`include-system-site-packages = false`）导入结果：

```text
OK mlx version=NO___version__ file=None
OK mlx.core version=0.32.1 file=/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages/mlx/core.cpython-312-darwin.so
OK mlx_lm version=0.31.3 file=/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages/mlx_lm/__init__.py
FAIL mlx_metal ModuleNotFoundError: No module named 'mlx_metal'
OK transformers version=5.15.1 file=.../transformers/__init__.py
OK tokenizers version=0.22.2 file=.../tokenizers/__init__.py
OK huggingface_hub version=1.28.0 file=.../huggingface_hub/__init__.py
```

`mlx` 包没有 `mlx.__version__`，版本在 `mlx.core.__version__` 和 dist-info 里，都是 **0.32.1**。`mlx-metal` 是发行包名，不是可 `import mlx_metal` 的模块；METADATA 版本 **0.32.1**。`mlx` 依赖 `mlx-metal`。

venv 里没有 `pip` 模块（`No module named pip`）。同环境用 `uv 0.10.0` 的 `uv pip show` 与 `importlib.metadata`：

| 包 | venv（服务所用，已导入或 dist-info） | Homebrew Python 3.14 site-packages（仅元数据） |
| --- | --- | --- |
| mlx | 0.32.1 | 0.32.1 |
| mlx-lm | 0.31.3 | 0.31.3 |
| mlx-metal | 0.32.1（不能 `import mlx_metal`） | 0.32.1 |
| transformers | 5.15.1 | 5.15.0 |
| tokenizers | 0.22.2 | 0.22.2 |
| huggingface_hub | 1.28.0 | 1.27.0 |

解释器：

```text
/opt/homebrew/bin/python3 -> ../Cellar/python@3.14/3.14.7/bin/python3
/opt/homebrew/bin/python3 --version → Python 3.14.7
服务二进制 → Python 3.12.12
kiln/.venv/bin/python -> /opt/homebrew/opt/python@3.12/bin/python3.12
realpath → .../Cellar/python@3.12/3.12.12_2/.../bin/python3.12
```

`mlx_lm` CLI：

- `/opt/homebrew/bin/mlx_lm` 与 `mlx_lm.server` 的 shebang 是 `#!/opt/homebrew/opt/python@3.14/bin/python3.14`。在干净环境里 `mlx_lm --version` 和 `mlx_lm --help` 都因 OpenMP 冲突中止，exit **134**，没有打出版本号。
- 服务 venv 的 `python -m mlx_lm --help` 成功，只列出子命令，没有版本行。版本以导入结果 **mlx_lm 0.31.3** 为准。

Homebrew 3.14 上 `import mlx, mlx_lm` 同样 OMP 失败（下面「未能测量」）。所以 3.14 那列版本是 dist-info / `importlib.metadata`，**不是**一次成功导入。

OMP 原文（3.14 CLI 与 `import` 相同）：

```text
OMP: Error #15: Initializing libomp.dylib, but found libomp.dylib already initialized.
EXIT_VERSION:134
```

没有设置 `KMP_DUPLICATE_LIB_OK`。

## 未能测量

- **热状态 / 热降频：没有读数，不声称正在降频。** `machdep.xcpm.cpu_thermal_level`、`gpu_thermal_level`、`io_thermal_level`、`thermal_level` 均为 `unknown oid`。`sysctl -a` 里名字带 throttle 的是网络 / IO / 页回收（如 `vm.page_throttled_count: 0`、`debug.lowpri_throttle_enabled: 1`），不是 CPU/GPU 温度。
- `sudo -n powermetrics` 失败：`sudo: a password is required`。没有 SMC 温度、功耗、GPU 频率。
- 本机 Command Line Tools / Xcode SDK 头文件中没有搜到 `kVMPressureWarning`。压力档 2 的文字含义来自上述 xnu 文档，不是本机 `memory_pressure` 打印的单词。
- `/opt/homebrew/bin/python3`（3.14.7）不能实际导入 mlx / mlx_lm（OMP abort 134）。
- 裸 Python 3.12 site-packages 没有这些包；venv 没有 `pip`，所以没有 `python -m pip show` 的成功输出，改用 `uv pip show` 与 METADATA。
- 未统计 GPU 占用字节，未加载模型。

## 执行的命令

原始日志：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A1/`。

| 文件 | 内容 |
| --- | --- |
| `01-os-cpu.txt` | `date`，`sw_vers`，`uname -a`，选定 `sysctl`，页大小 |
| `02-hardware-displays.txt` | `system_profiler SPHardwareDataType SPDisplaysDataType` |
| `03-memory-disk.txt` | `memory_pressure`，`vm_stat`，`sysctl vm.swapusage`，`df -h` |
| `04-thermal.txt` | xcpm sysctl 与 `sysctl -a` 中 thermal/throttle 匹配 |
| `05-python-mlx.txt` | Cellar 3.12 导入失败、默认 `python3` OMP 失败、`mlx_lm` 路径 |
| `06-powermetrics.txt` | `sudo -n powermetrics` 需要密码 |
| `07-memory-pressure-level.txt` | `uptime`，`kern.memorystatus_*`，`memory_pressure -Q`，页换算 |
| `08-pid1581-env-filtered.txt` | 过滤后的环境键（当时漏了 `__PYVENV_LAUNCHER__`） |
| `09-pid1581-maps.txt` | `lsof` / `vmmap` 中的 mlx 映射 |
| `10-interpreters.txt` | venv 符号链接、`pyvenv.cfg`、CLI shebang |
| `11-venv-mlx-versions.txt` | venv 导入与 `importlib.metadata` |
| `12-homebrew-import.txt` | Python 3.14 导入 OMP 失败 |
| `13-mlx-lm-cli.txt` | CLI `--version`/`--help` 与 venv `python -m mlx_lm --help` |
| `14-pressure-enum.txt` | 本地头文件未命中；压力档复读 |
| `15-pid1581-venv-link.txt` | 符号链接链、cwd、环境变量名 |
| `16-venv-dist-info.txt` | `mlx.core.__version__` 与 METADATA |
| `17-homebrew-metadata-uv.txt` | 3.14 元数据与 `uv pip show` |
| `18-pressure-man.txt` | `man memory_pressure` |
| `19-launcher.txt` | `__PYVENV_LAUNCHER__`、`XPC_SERVICE_NAME`、3.12 site-packages 无 mlx、etime/RSS |
| `20-venv-imports.txt` | venv 内 mlx / mlx_lm / transformers / tokenizers / huggingface_hub 导入 |

# A1 硬件复测

采样：2026-09-25 02:06:40–02:06:48 CST。只读，无 sudo。未重启服务，未发推理，未删文件。报告不含序列号。

`sw_vers`：macOS 26.5，Build 25F71。

```text
ProductName:		macOS
ProductVersion:		26.5
BuildVersion:		25F71
```

`sysctl hw.memsize`：`25769803776`（正好 24 GiB）。

`memory_pressure` 的空闲百分比与 `sysctl kern.memorystatus_level` 同为 **40%**。`sysctl kern.memorystatus_vm_pressure_level` 为 **2**。本次没有加 `-l`，没有施加压力。

```text
System-wide memory free percentage: 40%
kern.memorystatus_level: 40
kern.memorystatus_vm_pressure_level: 2
```

`sysctl vm.swapusage`：总量 14336.00M（14 GiB），已用 12906.12M，剩余 1429.88M，加密。

```text
vm.swapusage: total = 14336.00M  used = 12906.12M  free = 1429.88M  (encrypted)
```

`df -h /System/Volumes/Data`：`/dev/disk3s5`，926Gi 中已用 474Gi，可用 406Gi，容量 54%。

```text
Filesystem      Size    Used   Avail Capacity iused ifree %iused  Mounted on
/dev/disk3s5   926Gi   474Gi   406Gi    54%    5.4M  4.3G    0%   /System/Volumes/Data
```

`lsof -nP -iTCP:8081 -sTCP:LISTEN`：唯一监听者是 Python，PID **1581**，`127.0.0.1:8081`。

```text
COMMAND  PID      USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  1581 rainhuang    7u  IPv4 0xc78dadaa4d753204      0t0  TCP 127.0.0.1:8081 (LISTEN)
```

`footprint -p 1581`（02:06:48）：`phys_footprint` **5154 MB**，`phys_footprint_peak` **9215 MB**。合计行与 phys 一致；脏页大头是 IOAccelerator（graphics）4879 MB。

```text
Python [1581]: 64-bit    Footprint: 5154 MB (16384 bytes per page)
phys_footprint: 5154 MB
phys_footprint_peak: 9215 MB
```

相对 2026-09-24 约 20:53 的同口径：空闲百分比 37% → 40%，压力档仍是 2；交换从 total 16384.00M / used 15348.81M 变为 total 14336.00M / used 12906.12M；Data 已用 476Gi → 474Gi，可用 403Gi → 406Gi。监听 PID 仍是 1581。`phys_footprint` 5086 MB → 5154 MB，峰值 7944 MB → 9215 MB。

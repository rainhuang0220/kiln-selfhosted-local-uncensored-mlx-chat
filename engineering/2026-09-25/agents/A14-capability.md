# A14 本机命令

`which` 结果与安全读取到的版本。没有安装。

| 命令 | 路径 | 版本 |
| --- | --- | --- |
| `gh` | `/opt/homebrew/bin/gh` | 2.86.0（2026-01-21） |
| `hf` | `/opt/homebrew/bin/hf` | 1.27.0 |
| `deja` | `/Users/rainhuang/.local/bin/deja` | 0.20.1 |
| `python3` | `/opt/homebrew/bin/python3` | 3.14.7 |
| `mlx_lm` | `/opt/homebrew/bin/mlx_lm` | 0.31.3 |

`mlx_lm` 的版本来自 Python 3.14 的包元数据，没有执行该 CLI。直接跑 `mlx_lm --version` 会触发 OpenMP Error #15，不当作安全的版本命令。

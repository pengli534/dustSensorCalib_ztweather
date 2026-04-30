# 开发任务清单

- **Task 1: 基础设施搭建**
  - Python 项目入口为 `main.py`，核心模块位于 `calibration_app/`。
  - 依赖为 `pyserial>=3.5`、`numpy>=1.21,<1.22`，可从 `wheelhouse/` 离线安装。
  - 日志使用 `logging`，同时输出到控制台和日志文件。

- **Task 2: 硬件通信层**
  - `ModbusRTUClient` 封装 Modbus RTU CRC、读写寄存器、原始帧发送和最多 3 次重试。
  - `SensorDevice` 封装陀螺仪水平校准、采样周期配置、积灰污染比读取、原始 CH1/CH2 测量读取和旧版参数写入。
  - 当前校准参数写入仍按 Excel/旧版流程使用 `0x0009` 起始地址写入 `A1/A2`，该方式与 V2.1 地址表不一致，代码和日志必须保留 warning。

- **Task 3: 多点采样与异常剔除**
  - 透光率点位和每点采样次数来自 `calibration_plan.csv`，默认 6 个点位、每点 5 次。
  - 每次采样读取 V2.1 原始测量数据，使用 `CH1/CH2` 作为拟合输入 `x`，标准透光率作为 `y`。
  - 同一透光率下的多次采样先按 `CH1/CH2` 比值做异常值检测。默认使用中位数和 MAD 计算 modified Z-score，阈值为 `3.5`。
  - 被判定偏差过大的样本必须保留在 `calibration_samples.csv` 中，但 `used_for_fit=False`，不参与拟合和参数计算。

- **Task 4: 拟合、绘图和参数编码**
  - 使用未剔除样本做一次函数拟合 `$y = kx + b$`，禁止先按同一透光率求平均后再拟合。
  - 拟合图 `calibration_fit.svg` 中蓝点表示参与拟合样本，红色叉号表示被剔除样本。
  - 参数编码规则保持为 `A1 = round((-k) * 10000)`、`A2 = round(b * 100)`，并输出 4 位十六进制寄存器值。
  - 写入设备前，交互模式允许人工确认或调整 `k/b/A1/A2`。

- **Task 5: 输出归档**
  - 每次运行都在 `--output-dir` 指定目录下创建时间戳子目录，格式为 `YYYYMMDD_HHMMSS`。
  - 本次运行的 `calibration_samples.csv`、`calibration_fit.svg`、`calibration_parameters.csv`、`verification_results.csv` 均写入该时间戳目录。
  - 若同一秒重复运行，目录自动追加 `_01`、`_02` 等后缀，避免覆盖历史结果。

- **Task 6: 终检验证**
  - 默认按 `calibration_plan.csv` 点位逐一终检，也可通过 `--skip-verification` 跳过。
  - 终检读取 `0x10` 积灰污染比，按绝对误差 `±5%` 判定 Pass/Fail。

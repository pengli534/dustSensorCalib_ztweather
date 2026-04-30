# 开发任务清单

- **Task 1: 基础设施**
  - Python 入口为 `main.py`，核心模块位于 `calibration_app/`。
  - 依赖为 `pyserial>=3.5`、`numpy>=1.21,<1.22`，可从 `wheelhouse/` 离线安装。
  - 日志使用 `logging`，同时输出到控制台和日志文件。

- **Task 2: 硬件通信层**
  - `ModbusRTUClient` 封装 Modbus RTU CRC、寄存器读写、原始帧发送和最多 3 次重试。
  - `SensorDevice` 封装陀螺仪水平校准、采样周期配置、原始 CH1/CH2 读取、积灰污染比读取和旧版参数写入。
  - 当前校准参数写入仍按 Excel/旧版流程使用 `0x0009` 起始地址写入 `A1/A2`，该方式与 V2.1 地址表不一致，代码和日志必须保留 warning。

- **Task 3: calibration_plan.csv 配置**
  - `calibration_plan.csv` 必须包含 `transmittance_percent`，可包含 `samples_per_point` 和 `verification_samples_per_point`。
  - `samples_per_point` 控制标定阶段该透光率点位采样次数。
  - `verification_samples_per_point` 控制终检阶段该透光率点位读取次数。
  - 兼容旧列名 `sample_count`，并兼容终检采样列别名 `verification_samples`、`verification_sample_count`。

- **Task 4: 标定采样异常剔除**
  - 每次标定采样读取 V2.1 原始测量数据，使用 `CH1/CH2` 作为拟合输入 `x`，标准透光率作为 `y`。
  - 同一透光率下的多次采样按 `CH1/CH2` 比值做异常值检测。默认使用 median/MAD modified Z-score，阈值为 `3.5`。
  - 被判定偏差过大的样本保留在 `calibration_samples.csv` 中，但 `used_for_fit=False`，不参与拟合和参数计算。

- **Task 5: 拟合、绘图和参数编码**
  - 使用未剔除样本做一次函数拟合 `y = kx + b`，禁止先按同一透光率求平均后再拟合。
  - `calibration_fit.svg` 中蓝点表示参与拟合样本，红色叉号表示被剔除样本。
  - 若执行终检，SVG 还必须用橙色菱形标识每个透光率点位的终检平均结果。
  - 参数编码规则保持为 `A1 = round((-k) * 10000)`、`A2 = round(b * 100)`。

- **Task 6: 终检验证**
  - 默认按 `calibration_plan.csv` 点位逐一终检，也可通过 `--skip-verification` 跳过。
  - 每个终检点读取次数优先来自 CSV 的 `verification_samples_per_point`。
  - CSV 未提供终检采样次数时，使用命令行 `--verification-samples` 的默认值。
  - 终检先剔除偏差过大的读数，再对剩余读数求平均，并按 `±5%` 判定 Pass/Fail。

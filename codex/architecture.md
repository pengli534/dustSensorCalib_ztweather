# 系统架构设计

## 1. 模块划分

- `main.py`
  - 解析命令行参数，加载校准点位，创建串口客户端、设备对象和工作流。
  - 新增 `--outlier-z-threshold`，用于调整异常样本剔除阈值。

- `calibration_app/config.py`
  - 定义串口配置、校准点位、采样等待时间、终检阈值和异常剔除参数。
  - 默认 `sample_outlier_z_threshold=3.5`，`min_samples_for_outlier_rejection=3`。

- `calibration_app/modbus_rtu.py`
  - 负责 Modbus RTU 帧构造、CRC、读写寄存器、原始命令发送和重试。

- `calibration_app/sensor_device.py`
  - 面向设备的业务 API，包括陀螺仪校准、采样周期配置、原始测量读取、积灰污染比读取和旧版参数写入。

- `calibration_app/calibration_math.py`
  - 定义 `CalibrationSample`、拟合结果、参数编码。
  - `filter_sample_outliers()` 按透光率分组剔除偏差过大的 `CH1/CH2` 样本。

- `calibration_app/workflow.py`
  - 串联完整校准流程。
  - 每次运行创建时间戳输出目录。
  - 输出全量样本 CSV，但仅把 `used_for_fit=True` 的样本传入拟合。

- `calibration_app/plotting.py`
  - 输出 SVG 拟合图。
  - 蓝点为参与拟合样本，红色叉号为剔除样本。

## 2. 数据流

`calibration_plan.csv`
-> 陀螺仪校准
-> 配置采样周期
-> 按透光率点位采集原始 CH1/CH2
-> 按点位做异常剔除
-> 写出全量样本 CSV
-> 使用未剔除样本拟合 `k/b`
-> 输出拟合图
-> 编码 `A1/A2`
-> 人工确认或调整
-> 写入设备
-> 可选终检
-> 写出终检 CSV

## 3. 输出目录策略

- `CalibrationWorkflow.run()` 开始时调用 `_create_run_output_dir()`。
- 基础目录来自命令行 `--output-dir`，默认 `output`。
- 实际输出目录形如 `output/20260430_142501/`。
- 若目录已存在，自动生成 `output/20260430_142501_01/`，确保留档不覆盖。

## 4. 异常剔除策略

- 异常判断不直接比较 CH1 或 CH2，而比较用于拟合的 `CH1/CH2`。
- 每个透光率点位独立计算中位数和 MAD。
- modified Z-score 超过阈值的样本标记为剔除。
- 剔除信息写入 `calibration_samples.csv` 的 `used_for_fit` 与 `outlier_reason` 字段。

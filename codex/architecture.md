# 系统架构设计

## 1. 模块划分

- `main.py`
  - 解析命令行参数，加载校准点位，创建串口客户端、设备对象和工作流。
  - 支持 `--outlier-z-threshold`、`--verification-samples`、`--verification-outlier-z-threshold`。

- `calibration_app/config.py`
  - 定义串口配置、校准点位、采样等待时间、终检阈值、标定异常剔除参数和终检异常剔除参数。
  - 默认终检每点读取 5 次。

- `calibration_app/modbus_rtu.py`
  - 负责 Modbus RTU 帧构造、CRC、寄存器读写、原始命令发送和重试。

- `calibration_app/sensor_device.py`
  - 面向设备的业务 API，包括陀螺仪校准、采样周期配置、原始测量读取、积灰污染比读取和旧版参数写入。

- `calibration_app/calibration_math.py`
  - 定义 `CalibrationSample`、拟合结果、参数编码。
  - `filter_sample_outliers()` 按透光率分组剔除偏差过大的 `CH1/CH2` 标定样本。
  - `filter_numeric_outliers()` 用于终检读数剔除偏差过大的数值。

- `calibration_app/workflow.py`
  - 串联完整校准流程。
  - 每次运行创建时间戳输出目录。
  - 标定阶段输出全量样本 CSV，但仅把 `used_for_fit=True` 的样本传入拟合。
  - 终检阶段按点位多次读取、异常剔除、平均后判定。

- `calibration_app/plotting.py`
  - 输出 SVG 拟合图。
  - 蓝点为参与拟合样本，红色叉号为剔除样本，橙色菱形为终检平均结果。

## 2. 数据流

`calibration_plan.csv`
-> 陀螺仪校准
-> 配置采样周期
-> 按透光率点位采集原始 CH1/CH2
-> 标定样本异常剔除
-> 写出全量样本 CSV
-> 使用未剔除样本拟合 `k/b`
-> 输出初始拟合图
-> 编码 `A1/A2`
-> 人工确认或调整
-> 写入设备
-> 终检多次读取 `0x10`
-> 终检读数异常剔除并平均
-> 写出终检 CSV
-> 重写 SVG，追加终检平均结果

## 3. 输出目录策略

- `CalibrationWorkflow.run()` 开始时调用 `_create_run_output_dir()`。
- 基础目录来自命令行 `--output-dir`，默认 `output`。
- 实际输出目录形如 `output/20260430_142501/`。
- 若目录已存在，自动生成 `output/20260430_142501_01/`，确保留档不覆盖。

## 4. 异常剔除策略

- 标定异常判断不直接比较 CH1 或 CH2，而比较用于拟合的 `CH1/CH2`。
- 终检异常判断比较同一透光率点位下多次读取的积灰污染比数值。
- 两类异常剔除都默认使用 median/MAD modified Z-score。
- 剔除信息分别写入 `calibration_samples.csv` 和 `verification_results.csv`。

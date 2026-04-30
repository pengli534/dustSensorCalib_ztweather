# 系统架构设计

## 1. 模块划分

- `main.py`
  - 解析命令行参数，加载校准点位，创建串口客户端、设备对象和工作流。
  - `--verification-samples` 作为 CSV 未配置终检采样次数时的默认值。

- `calibration_app/config.py`
  - `CalibrationPoint` 保存 `transmittance_percent`、`samples_per_point`、`verification_samples_per_point`。
  - `load_calibration_points()` 读取 CSV，并校验标定采样次数和终检采样次数必须为正整数。
  - 缺失计划文件时使用默认点位，并套用命令行传入的默认终检采样次数。

- `calibration_app/calibration_math.py`
  - `filter_sample_outliers()` 按透光率分组剔除偏差过大的 `CH1/CH2` 标定样本。
  - `filter_numeric_outliers()` 用于终检读数剔除偏差过大的数值。

- `calibration_app/workflow.py`
  - 标定阶段使用 `point.samples_per_point` 控制每点标定采样次数。
  - 终检阶段使用 `point.verification_samples_per_point` 控制每点终检读取次数。
  - 终检读数剔除异常后取平均，再写出 `verification_results.csv`。

- `calibration_app/plotting.py`
  - 输出 SVG 拟合图。
  - 蓝点为参与拟合样本，红色叉号为剔除样本，橙色菱形为终检平均结果。

## 2. 数据流

`calibration_plan.csv`
-> 读取每个点位的标定采样次数和终检采样次数
-> 标定采样
-> 标定样本异常剔除
-> 拟合 `k/b`
-> 写入 `A1/A2`
-> 按点位配置执行终检多次读取
-> 终检读数异常剔除并平均
-> 写出终检 CSV
-> 重写 SVG，追加终检平均结果

## 3. CSV 兼容策略

- 新格式推荐使用 `verification_samples_per_point`。
- 旧计划文件如果只有 `transmittance_percent,samples_per_point`，仍可运行。
- 旧计划文件未配置终检次数时，使用 `--verification-samples` 作为全局默认值。

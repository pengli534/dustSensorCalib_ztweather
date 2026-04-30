# 积灰传感器自动化校准程序需求

## 1. 通信与硬件

- 通过 RS485 转 USB 与 ZTD-6 设备通信，协议为 Modbus RTU。
- 标准寄存器读写、原始测量帧读取、CRC 校验和重试逻辑必须封装在通信层。
- 单条 Modbus 操作最多重试 3 次，全部失败后中断当前校准流程。
- V2.1 常规测量数据按 32-bit float、大端、IEEE754 解析。
- 标定采样必须使用 V2.1 原始测量命令读取 `CH1/CH2`。

## 2. 校准计划 CSV

`calibration_plan.csv` 格式：

```csv
transmittance_percent,samples_per_point,verification_samples_per_point
100,5,5
99,5,5
97,5,5
91.4,5,5
85,5,5
72.4,5,5
```

- `transmittance_percent`：必填，标准透光率。
- `samples_per_point`：可选，标定阶段该点位的采样次数，默认 5。
- `verification_samples_per_point`：可选，终检阶段该点位的读取次数，默认来自 `--verification-samples`。
- 兼容旧列名：`sample_count` 等同于 `samples_per_point`。
- 兼容终检列别名：`verification_samples`、`verification_sample_count` 等同于 `verification_samples_per_point`。
- 采样次数必须为正整数。

## 3. 校准流程

1. 读取 `calibration_plan.csv`。
2. 执行陀螺仪水平校准。
3. 配置传感器采样周期为 5s。
4. 按 CSV 点位提示人工放置透光膜，确认后等待 1s。
5. 每次软件采样前等待 8s，然后读取原始测量数据。
6. 对每个透光率点位的多次标定采样做异常值剔除。
7. 使用未剔除样本拟合 `y = kx + b`。
8. 输出拟合图和参数文件，写入设备前允许人工确认或调整。
9. 默认执行终检；终检按 CSV 中每个点位的 `verification_samples_per_point` 多次读取、异常剔除、平均值判定。

## 4. 终检多次平均

- 每个终检点读取次数优先来自 `calibration_plan.csv` 的 `verification_samples_per_point`。
- 如果 CSV 未填写终检采样次数，则使用命令行 `--verification-samples`，默认 5。
- 每次终检读取前等待 `verification_wait_s`，默认 8s。
- 终检读数按同一透光率点位内部做异常值剔除，默认阈值 `3.5`。
- 终检结果使用未剔除读数的平均值参与 `±5%` 判定。

## 5. 输出文件

- 每次运行输出到 `output/YYYYMMDD_HHMMSS/`，不得覆盖上一次测量结果。
- `calibration_samples.csv` 记录全部标定样本，包含 `used_for_fit` 和 `outlier_reason`。
- `calibration_fit.svg` 显示参与拟合样本、剔除样本、拟合直线；终检后追加终检平均结果标识。
- `calibration_parameters.csv` 记录最终写入前确认后的 `k/b/A1/A2`。
- `verification_results.csv` 记录每次终检读数、是否参与平均、剔除原因、平均值、误差和是否通过。

# AI 编程规范与约束

## 1. CSV 规则

- `calibration_plan.csv` 必须支持列 `transmittance_percent,samples_per_point,verification_samples_per_point`。
- `verification_samples_per_point` 是终检阶段每个透光率点位的读取次数。
- 未配置 `verification_samples_per_point` 时，必须回退到命令行 `--verification-samples`。
- 所有采样次数字段必须校验为正整数。
- 修改 CSV 解析时必须保持旧列名 `sample_count` 兼容。

## 2. 采样规范

- 标定采样次数使用 `CalibrationPoint.samples_per_point`。
- 终检采样次数使用 `CalibrationPoint.verification_samples_per_point`。
- 人工换膜确认后必须先等待 1s。
- 每次标定采样和终检读取前必须等待对应配置的等待时间。
- 不得把同一透光率下的多次标定采样先求平均后再拟合。

## 3. 异常剔除规范

- 标定剔除判断以同一透光率点位内的 `CH1/CH2` 比值为准。
- 终检剔除判断以同一透光率点位内的多次 `0x10` 读数为准。
- 默认使用 median/MAD modified Z-score，阈值为 `3.5`。
- 标定样本 CSV 必须包含 `used_for_fit` 和 `outlier_reason`。
- 终检 CSV 必须包含每次读数、是否参与平均、剔除原因、平均值和判定结果。

## 4. 输出归档规范

- 所有测量输出必须按时间分文件夹保存。
- 默认目录为 `output/YYYYMMDD_HHMMSS/`。
- 不得覆盖已有运行结果；同秒冲突时追加数字后缀。
- 执行终检后，`calibration_fit.svg` 必须标识终检平均结果。

## 5. 测试规范

- CSV 新列解析、默认值回退、非法采样次数、终检按点位次数读取都必须有单元测试。
- 修改拟合、剔除、CSV 或终检逻辑后必须运行 `python -m unittest discover -s tests`。

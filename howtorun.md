# 运行程序

```powershell
.\.venv\Scripts\python.exe main.py --port COM6 --address 1
```

如需调整异常样本剔除灵敏度：

```powershell
.\.venv\Scripts\python.exe main.py --port COM6 --address 1 --outlier-z-threshold 3.5
```

## 输出位置

程序会在 `output` 下按时间创建本次运行文件夹，例如：

```text
output/20260430_142501/
```

该目录中会保存：

- `calibration_samples.csv`：全部采样结果，包含 `used_for_fit` 和 `outlier_reason`。
- `calibration_fit.svg`：拟合图，蓝点为参与拟合样本，红色叉号为剔除样本。
- `calibration_parameters.csv`：最终确认后的 `k/b/A1/A2`。
- `verification_results.csv`：终检结果，跳过终检时不会生成。

## 运行条件

- Windows 64 位。
- 串口驱动已安装，例如 CH340/USB 转串口驱动。
- 确认设备实际串口号，若不是 COM6，请改成实际端口，例如 `--port COM3`。
- 命令需在工程根目录执行，因为默认读取当前目录下的 `calibration_plan.csv`。

## 安装虚拟环境

```powershell
cd 积灰标定
py -3.7 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r requirements.txt
.\.venv\Scripts\python.exe main.py --port COM6 --address 1
```

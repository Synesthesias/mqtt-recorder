testdataフォルダ以下にあるのは、RideVisionのMqttLagTestシーンで利用する用です。

- linear_vehicle_pose_*.json: 理想的な直線運動です。
- jitter_vehicle_pose_*.json: 理想的な直線運動にVehicleLocalizerのmqtt_lag_test相当の2D位置ブレを重ねたものです。運動終了後20秒間は停止したままブレだけを再現します。

ブレ再現データを作り直す例:

```powershell
python testdata/generate_jitter_vehicle_pose.py --output-dir testdata --rates 10 90
```

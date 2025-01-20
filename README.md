# MQTT Recorder

メッセージの頻度が高すぎると再生時にpublish時間に遅延が出てしまう問題あり。

Simple tool to record/replay MQTT data.

## 使い方
### インストール(Windows)
#### Python3.9
https://www.python.org/downloads/

#### pythonパッケージ
```
pip3 install paho-mqtt
```

#### MQTTブローカー
* https://mosquitto.org/download/
  * https://mosquitto.org/files/binary/win64/mosquitto-2.0.12-install-windows-x64.exe
  * 参考：https://synesthesias.atlassian.net/wiki/spaces/RIDEVISION/pages/347308129#MQTT%E3%83%96%E3%83%AD%E3%83%BC%E3%82%AB%E3%83%BC%E3%81%AE%E8%A8%AD%E5%AE%9A

### 記録
```
pythonw.exe mqtt_recorder.py --server 192.168.0.1 --mode record --output 2021-08-03-mqtt.json
```

### 再生
```
pythonw.exe mqtt_recorder.py --server localhost --mode replay --input 2021-08-03-mqtt.json --realtime
 ```

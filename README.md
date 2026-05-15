# MQTT Recorder

高頻度メッセージの再生では、`--realtime` と絶対時刻ベースのスケジューリングを使ってpublishします。
短い待ち時間はOSのsleep分解能で遅れやすいため、必要に応じて `--busy-wait-threshold-ms` を調整してください。

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
pythonw.exe mqtt_recorder.py --server 127.0.0.1 --mode replay --input 2021-08-03-mqtt.json --realtime
 ```

900Hzなど高頻度の再生でタイミング精度を優先する場合:
```
pythonw.exe mqtt_recorder.py --server 127.0.0.1 --mode replay --input 2021-08-03-mqtt.json --realtime --busy-wait-threshold-ms 1
```

# 通信ラグを計測したい時の留意事項
- ログを出すためにpythonw.exeではなくpython.exeを利用してください。
- MQTTブローカーへの接続に要した時間はログで「Connected to MQTT broker in Xms」と表示されます。
  - 接続先をlocalhostにすると、この接続時間が1000ms以上に膨れ上がります。127.0.0.1にすると5ms程度になります。
  - この理由は、ホスト名解決でまずIPv6での接続を試みる → 失敗するのでIPv4での接続を試みる というフォールバック処理が働いているためではないかと推測されます。
- realtimeでのreplayモード時、MQTT発出タイミングが最大どのくらいずれたかはログで「max replay lateness: Xms」と表示されます。

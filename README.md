# TQUIC Datagram Example

基于 [TQUIC](https://github.com/tencent/tquic) 的简单 **Client/Server** 程序，用于测试 **QUIC Datagram vs Stream** 在不同网络条件下的性能表现（丢包率、端到端延迟、优先级调度等）。

---

## 1. 环境依赖

### 系统环境

- Ubuntu 20.04+ / Debian / 其他类 Unix 系统  
- 已安装 `build-essential`、`cmake`、`python3`、`git`  

### Rust 工具链

```bash
curl https://sh.rustup.rs -sSf | sh
rustc --version    # 确认 >= 1.70
```

### Mahimahi 网络仿真工具

```bash
sudo apt-get install mahimahi
```

### Python 脚本依赖（用于生成 trace 和分析结果）

```bash
pip install matplotlib pandas
```

---

## 2. 编译

```bash
cargo build --debug
```

生成的二进制位于：

- `target/debug/server`
- `target/debug/client`

---

## 3. 生成测试文件与 trace

### 测试输入文件

```bash
mkdir -p testdata
dd if=/dev/urandom of=testdata/test.bin bs=1M count=50
```

---

## 4. 启动服务端

在宿主机运行：

```bash
mkdir -p results/raw_csv results/recv

./target/debug/server \
  --listen 0.0.0.0:4433 \
  --cert src/cert.crt \
  --key src/cert.key \
  --out-dir testdata/recv \
  --csv-recv results/raw_csv/server_recv.csv
```

---

## 5. 启动客户端（Mahimahi 仿真）

在 Mahimahi shell 内运行客户端，让流量经过模拟链路。

### 丢包测试

```bash
export RUN=smoke_$(date +%Y%m%d_%H%M%S)

mm-delay 25 mm-link  "trace/12Mbps.log" "trace/12Mbps.log" -- sh -c '
            mm-loss uplink 0.0 \
            ./target/debug/client --connect-to $MAHIMAHI_BASE:4433 \
            --mode stream \
            --in-file testdata/send/test.txt \
            --rate-mbps 0.1 --chunk-bytes 1200 \
            --csv-send results/raw_csv/client_send_datagram.csv \
            --log-level debug' > client_send.log 2>&1
```

### 拥塞 + 优先级测试

并发两条流：低优先级 **stream** 400 Mbps，和高优先级 **datagram** 10 Mbps。

```bash
export RUN=prio_$(date +%Y%m%d_%H%M%S)

mm-delay 25 mm-link trace/500Mbps.log trace/500Mbps.log -- \
sh -c "./target/release/client --connect-to \\$MAHIMAHI_BASE:4433 \
  --mode stream --rate-mbps 400 --in-file testdata/test.bin \
  --csv-send results/raw_csv/${RUN}/client_stream.csv & \
sleep 1; \
./target/release/client --connect-to \\$MAHIMAHI_BASE:4433 \
  --mode datagram --rate-mbps 10 --in-file testdata/test.bin \
  --csv-send results/raw_csv/${RUN}/client_dgram.csv"
```

---

## 6. 数据分析

在 `results/raw_csv/` 下会生成：

- `client_send_*.csv`
- `server_recv.csv`

使用分析脚本：

```bash
python3 scripts/analyze.py --input results/raw_csv/${RUN} --out-dir results/figures/${RUN}
```

---

## 7. 常见问题

- **错误：`downlink: No such file or directory`**  
  → 说明 `mm-loss` 参数没加 `--` 分隔。  

- **错误：`error opening for reading`**  
  → 说明 `trace/500Mbps.log` 文件不存在或格式不对。  

- **证书问题**  
  → 可用以下命令生成：

  ```bash
  mkdir -p certs
  openssl req -new -x509 -nodes -out certs/server.crt -keyout certs/server.key -days 365
  ```

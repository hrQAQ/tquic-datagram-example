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
mm-delay 25
mm-link trace/96Mbps.log trace/96Mbps.log

[delay 25 ms] [link] $  scripts/run_loss.sh
```

### 拥塞 + 优先级测试

TODO

---

## 6. 数据分析

在 `results/raw_csv/` 下会生成多个 CSV 文件，包含发送和接收的详细日志，根据这些日志可以计算丢包率、端到端延迟等指标。

使用分析脚本：

```bash
python scripts/analyze_loss.py --run-dir results/raw_csv/loss_20250910_114931 --out-root results/analysis             
```
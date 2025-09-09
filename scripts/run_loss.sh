#!/usr/bin/env bash
set -euo pipefail

# ========== 可调参数 ==========
FILE="testdata/test.bin"
RATE_MBPS=10
CHUNK=1200
LOSSES=("0.0" "0.5" "1.0" "2.0")    # 单位：百分数（Mahimahi 语义中 1.0 表示 1%）
BW="500Mbit"
RTT_MS=50
CCA_LIST=("bbr" "cubic")            # 你的 fork 如果支持 --cca
RUN_TAG="loss_$(date +%Y%m%d_%H%M%S)"

# 计算 BDP 队列（近似）
MSS=${CHUNK}
BW_bps=$(echo $BW | sed 's/Mbit/*1000000/;s/Kbit/*1000/;s/bit//;s/Mbps/*1000000/;s/Kbps/*1000/' | bc -l)
RTT_S=$(echo "$RTT_MS/1000" | bc -l)
BDP_PKTS=$(printf "%.0f" "$(echo "$BW_bps * $RTT_S / (8 * $MSS)" | bc -l)")

echo "[INFO] RUN_TAG=$RUN_TAG  BDP_PKTS=$BDP_PKTS"

mkdir -p "results/raw_csv/${RUN_TAG}"

for cca in "${CCA_LIST[@]}"; do
  for loss in "${LOSSES[@]}"; do
    for mode in datagram stream; do
      echo "[INFO] ==> CCA=$cca LOSS=${loss}% MODE=$mode"

      # 每次运行前，设置输出文件（避免互相覆盖）
      SEND_CSV="results/raw_csv/${RUN_TAG}/client_send_${mode}_loss${loss}_cca${cca}.csv"
      RECV_CSV="results/raw_csv/server_recv.csv" # server 端已固定；建议跑完及时备份归档

      # Mahimahi 客户端侧运行
      mm-delay $((RTT_MS/2)) \
      mm-link --downlink-trace "$BW" --uplink-trace "$BW" \
      -- sh -c "mm-loss uplink ${loss} downlink ${loss} mm-queue ${BDP_PKTS} \
        ./client \
          --connect-to \$MAHIMAHI_BASE:4433 \
          --mode $mode \
          --in-file $FILE \
          --rate-mbps $RATE_MBPS \
          --chunk-bytes $CHUNK \
          --csv-send $SEND_CSV \
          --cca $cca"

      # 备份服务端 CSV（按运行 tag+参数重命名）
      cp "$RECV_CSV" "results/raw_csv/${RUN_TAG}/server_recv_${mode}_loss${loss}_cca${cca}.csv"
      : > "$RECV_CSV"  # 清空 server 的 CSV，方便下一轮
    done
  done
done

echo "[INFO] Finished run_loss. All CSV in results/raw_csv/${RUN_TAG}"
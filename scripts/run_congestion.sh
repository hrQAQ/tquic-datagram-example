#!/usr/bin/env bash
set -euo pipefail

FILE_BG="testdata/test.bin"   # 背景 stream 文件
FILE_HI="testdata/test.bin"   # 前景 datagram 文件

RATE_BG=400     # Mbps，背景 stream
RATE_HI=10      # Mbps，高优 datagram
CHUNK=1200
BW="500Mbit"
RTT_MS=50
CCA_LIST=("Cubic", "Bbr", "Copa")
RUN_TAG="prio_$(date +%Y%m%d_%H%M%S)"

MSS=${CHUNK}
BW_bps=$(echo $BW | sed 's/Mbit/*1000000/;s/Kbit/*1000/;s/bit//;s/Mbps/*1000000/;s/Kbps/*1000/' | bc -l)
RTT_S=$(echo "$RTT_MS/1000" | bc -l)
BDP_PKTS=$(printf "%.0f" "$(echo "$BW_bps * $RTT_S / (8 * $MSS)" | bc -l)")

echo "[INFO] RUN_TAG=$RUN_TAG  BDP_PKTS=$BDP_PKTS"
mkdir -p "results/raw_csv/${RUN_TAG}"

for cca in "${CCA_LIST[@]}"; do
  echo "[INFO] ==> CCA=$cca (stream background vs datagram high-prio)"

  SEND_CSV_BG="results/raw_csv/${RUN_TAG}/client_send_stream_bg_cca${cca}.csv"
  SEND_CSV_HI="results/raw_csv/${RUN_TAG}/client_send_datagram_hi_cca${cca}.csv"
  RECV_CSV="results/raw_csv/server_recv.csv"

  mm-delay $((RTT_MS/2)) \
  mm-link --downlink-trace "$BW" --uplink-trace "$BW" \
  -- sh -c "mm-queue ${BDP_PKTS} \
     ( ./client --connect-to \$MAHIMAHI_BASE:4433 --mode stream   --in-file $FILE_BG --rate-mbps $RATE_BG --chunk-bytes $CHUNK --csv-send $SEND_CSV_BG --cca $cca ) & \
     sleep 1; \
     ( ./client --connect-to \$MAHIMAHI_BASE:4433 --mode datagram --in-file $FILE_HI --rate-mbps $RATE_HI --chunk-bytes $CHUNK --csv-send $SEND_CSV_HI --cca $cca ) ; \
     wait"

  cp "$RECV_CSV" "results/raw_csv/${RUN_TAG}/server_recv_prio_cca${cca}.csv"
  : > "$RECV_CSV"
done

echo "[INFO] Finished run_prio. All CSV in results/raw_csv/${RUN_TAG}"

#!/usr/bin/env bash
# Loss-sweep under Mahimahi, comparing QUIC Datagram vs Stream
# - Uses mm-delay + mm-link + mm-loss
# - Loss 'rate' is PROBABILITY in [0,1] (e.g., 0.01 == 1%)
# - Ensures MTU fairness by fixing UDP payload budget (DEFAULT_UDP_PAYLOAD_B=1200)
set -euo pipefail

# ===== User knobs =====
TRACE_UP="trace/96Mbps.log"
TRACE_DN="trace/96Mbps.log"
ONE_WAY_DELAY_MS=25                  # RTT ~= 2 * 25ms
LOSSES=("0.0" "0.005" "0.01" "0.02" "0.05") # 0%, 0.5%, 1%, 2%, 5%
CHUNKS=(1200)     # app chunk sizes to sweep
CCA_LIST=("Bbr")      # different congestion control algorithms
RATE_MBPS=95
MODES=("datagram" "stream")
MAX_DATAGRAM_FRAME_SIZE=65535       # max datagram frame size allowed by QUIC spec

CLIENT="./target/debug/client"
SERVER_CSV="results/raw_csv/server_recv.csv"
OUT_ROOT="results/raw_csv"
RUN_TAG="loss_$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUT_ROOT}/${RUN_TAG}"

mkdir -p "${OUT_DIR}"

# Basic checks
[[ -f "${TRACE_UP}" ]] || { echo "[ERR] missing ${TRACE_UP}"; exit 1; }
[[ -f "${TRACE_DN}" ]] || { echo "[ERR] missing ${TRACE_DN}"; exit 1; }
[[ -x "${CLIENT}" ]]   || { echo "[ERR] missing client at ${CLIENT}"; exit 1; }

echo "[INFO] RUN_TAG=${RUN_TAG}  OUT_DIR=${OUT_DIR}"
echo "[INFO] Using loss rates (probabilities): ${LOSSES[*]}"

for cca in "${CCA_LIST[@]}"; do
  for loss in "${LOSSES[@]}"; do
    for mode in "${MODES[@]}"; do
      for chunk in "${CHUNKS[@]}"; do
        tag="mode(${mode})_loss(${loss})_cca(${cca})_chunk(${chunk})"
        send_csv="${OUT_DIR}/client_send_${tag}.csv"
        echo "[INFO] ==> ${tag}"


        # mm-delay 25 mm-link  "trace/12Mbps.log" "trace/12Mbps.log" -- sh -c '
            # mm-loss uplink 0.2 \
            # ./target/debug/client --connect-to $MAHIMAHI_BASE:4433 \
            # --mode stream \
            # --in-file testdata/send/test.txt \
            # --rate-mbps 1 --chunk-bytes 8192 \
            # --csv-send results/raw_csv/stream.csv \
            # --log-level debug' > client_send.log 2>&1
        # NOTE: mm-loss takes probabilities in [0,1]. Use single mm-loss with both directions.
        mm-loss uplink "${loss}" \
        "${CLIENT}" \
          --connect-to "$MAHIMAHI_BASE:4433" \
          --mode "${mode}" \
          --in-file "testdata/send/syslog.log" \
          --rate-mbps "${RATE_MBPS}" \
          --chunk-bytes "${chunk}" \
          --csv-send "${send_csv}" \
          --cca "${cca}" \
          --max-datagram-frame-size "${MAX_DATAGRAM_FRAME_SIZE}"
        # archive server csv with same tag; server must be running persistently
        if [[ -f "${SERVER_CSV}" ]]; then
          cp "${SERVER_CSV}" "${OUT_DIR}/server_recv_${tag}.csv"
          : > "${SERVER_CSV}" # truncate for next run
        else
          echo "[WARN] server CSV not found at ${SERVER_CSV}"
        fi
      done
    done
  done
done

echo "[INFO] Finished. CSV at ${OUT_DIR}"

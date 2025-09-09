#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 client/server CSV，计算：
- Datagram: 丢包率、E2E 延迟(P50/P90/P99)、goodput
- Stream  : 完成时间、goodput
并绘制：
- Datagram 延迟CDF
- 对比条形图（丢包率、goodput）
使用方法：
  python3 scripts/analyze.py --run-dir results/raw_csv/loss_2025... --out-dir results/figures/loss_2025...
"""
import argparse, os, glob, math, csv, collections
from statistics import median
import matplotlib.pyplot as plt

def load_csv(path):
    rows=[]
    with open(path, newline='') as f:
        r=csv.reader(f)
        for row in r:
            # expect: phase, ts_ns, file_id_hex/off-seq, offset_or_seq, size, mode
            # server: recv, ts, fileid_hex, offset, size, mode
            # client: send, ts, fileid_hex, offset, size, mode
            if len(row)<5: continue
            phase=row[0]
            ts=int(row[1])
            id_or_hex=row[2]
            off=int(row[3])
            size=int(row[4])
            mode=row[5] if len(row)>5 else ""
            rows.append((phase,ts,id_or_hex,off,size,mode))
    return rows

def analyze_datagram(send_rows, recv_rows):
    # key: (file_id_hex, offset)
    s_map={(r[2],r[3]): r for r in send_rows if r[0]=="send" and r[5].startswith("datagram")}
    r_map={(r[2],r[3]): r for r in recv_rows if r[0]=="recv" and r[5].startswith("datagram")}
    total_bytes = sum(r[4] for r in send_rows if r[0]=="send" and r[5].startswith("datagram"))
    recv_bytes  = sum(r[4] for r in recv_rows if r[0]=="recv" and r[5].startswith("datagram"))

    # latency list
    lat=[]
    matched_bytes=0
    for k, sr in s_map.items():
        rr = r_map.get(k)
        if rr:
            # ns->ms
            lat.append( (rr[1]-sr[1]) / 1e6 )
            matched_bytes += rr[4]

    loss = 0.0
    if total_bytes>0:
        loss = 1.0 - matched_bytes/total_bytes

    # percentiles
    lat_sorted=sorted(lat)
    def pct(p):
        if not lat_sorted: return None
        idx=min(len(lat_sorted)-1, max(0,int(round((p/100.0)*(len(lat_sorted)-1)))))
        return lat_sorted[idx]
    p50, p90, p99 = pct(50), pct(90), pct(99)

    # goodput（以接收端总字节 / 时间跨度）
    if r_map:
        start_ts=min(sr[1] for sr in s_map.values())
        end_ts  =max(rr[1] for rr in r_map.values())
        dur_s   =max(1e-9,(end_ts-start_ts)/1e9)
        goodput_mbps = (recv_bytes*8/1e6)/dur_s
    else:
        goodput_mbps = 0.0

    return {
        "loss": loss,
        "p50_ms": p50, "p90_ms": p90, "p99_ms": p99,
        "goodput_mbps": goodput_mbps,
        "lat_list_ms": lat_sorted
    }

def analyze_stream(send_rows, recv_rows):
    s = [r for r in send_rows if r[0]=="send" and r[5].startswith("stream")]
    r = [r for r in recv_rows if r[0]=="recv" and r[5].startswith("stream")]
    if not s or not r:
        return {"goodput_mbps":0.0,"duration_s":0.0,"recv_bytes":0}

    total_send = sum(x[4] for x in s)
    total_recv = sum(x[4] for x in r)

    t0=min(x[1] for x in s)
    t1=max(x[1] for x in r)
    dur_s=max(1e-9,(t1-t0)/1e9)
    goodput_mbps=(total_recv*8/1e6)/dur_s
    return {
        "duration_s": dur_s,
        "goodput_mbps": goodput_mbps,
        "recv_bytes": total_recv,
        "send_bytes": total_send
    }

def plot_latency_cdf(lat_ms, title, out_png):
    if not lat_ms:
        return
    xs=sorted(lat_ms)
    ys=[i/(len(xs)-1) if len(xs)>1 else 1.0 for i in range(len(xs))]
    plt.figure()
    plt.plot(xs, ys)
    plt.xlabel("Datagram E2E latency (ms)")
    plt.ylabel("CDF")
    plt.title(title)
    plt.grid(True, ls='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(out_png, dpi=160)
    plt.close()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="results/raw_csv/<RUN_TAG>")
    ap.add_argument("--out-dir", required=True, help="results/figures/<RUN_TAG>")
    args=ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # 自动匹配成对的 client/server CSV（通过文件名约定）
    client_files=sorted(glob.glob(os.path.join(args.run_dir, "client_send_*.csv")))
    for cpath in client_files:
        # 猜测对应的 server 文件（同参数命名）
        base=os.path.basename(cpath).replace("client_send_","server_recv_")
        spath=os.path.join(args.run_dir, base)
        if not os.path.exists(spath):
            # 或者合并大文件，例如 prio 场景只有一个 server 文件
            # 这里尝试匹配 run 目录里唯一 server 文件
            s_candidates=sorted(glob.glob(os.path.join(args.run_dir, "server_recv*.csv")))
            spath = s_candidates[0] if s_candidates else None

        if not spath: 
            print(f"[WARN] no matching server csv for {cpath}")
            continue

        send_rows=load_csv(cpath)
        recv_rows=load_csv(spath)

        # 区分 datagram/stream
        mode="unknown"
        if "datagram" in cpath: mode="datagram"
        elif "stream" in cpath: mode="stream"

        if mode=="datagram":
            res=analyze_datagram(send_rows, recv_rows)
            # 输出摘要
            tag=os.path.splitext(os.path.basename(cpath))[0]
            print(f"[DGRAM] {tag}: loss={res['loss']*100:.2f}%, "
                  f"p50={res['p50_ms'] and f'{res['p50_ms']:.2f}ms'}, "
                  f"p90={res['p90_ms'] and f'{res['p90_ms']:.2f}ms'}, "
                  f"p99={res['p99_ms'] and f'{res['p99_ms']:.2f}ms'}, "
                  f"goodput={res['goodput_mbps']:.2f}Mbps")

            # CDF 图
            out_png=os.path.join(args.out_dir, f"{tag}_latency_cdf.png")
            plot_latency_cdf(res["lat_list_ms"], f"{tag} latency CDF", out_png)

        elif mode=="stream":
            res=analyze_stream(send_rows, recv_rows)
            tag=os.path.splitext(os.path.basename(cpath))[0]
            print(f"[STREAM] {tag}: duration={res['duration_s']:.3f}s, "
                  f"goodput={res['goodput_mbps']:.2f}Mbps, "
                  f"recv={res['recv_bytes']}B")

    print(f"[INFO] Figures saved to {args.out_dir}")

if __name__=="__main__":
    main()

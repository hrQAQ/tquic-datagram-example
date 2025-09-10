#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze QUIC Datagram vs Stream under different loss settings.

功能：
1. 对比 Datagram 和 Stream 的整体传输完成时间。
2. 统计 Datagram 的单条消息端到端延迟（P50/P90/P95/P99）。
3. 计算 Datagram 和 Stream 的 Goodput。
4. 计算 Datagram 的文件损失率。

输入目录结构 (run_dir):
  results/raw_csv/<RUN_TAG>/
    client_send_mode(<mode>)_loss(<loss>)_cca(<cca>)_chunk(<chunk>).csv
    server_recv_mode(<mode>)_loss(<loss>)_cca(<cca>)_chunk(<chunk>).csv

输出:
  results/analysis/<RUN_TAG>/
    summary/summary.csv
    figures/completion_time_bar.png
    figures/goodput_bar.png
    figures/dgram_latency_boxplot.png
    figures/dgram_loss_curve.png
    reports/report.md
"""
import argparse, os, glob, csv, re
from collections import defaultdict
import matplotlib.pyplot as plt

TAG_RE = re.compile(r"mode\((?P<mode>[^)]+)\)_loss\((?P<loss>[^)]+)\)_cca\((?P<cca>[^)]+)\)_chunk\((?P<chunk>[^)]+)\)")

def load_csv(path):
    rows=[]
    with open(path, newline='') as f:
        r=csv.reader(f)
        for row in r:
            if len(row) < 5: continue
            try:
                phase=row[0].strip()
                ts=int(row[1])
                fid=row[2]
                off=int(row[3])
                sz=int(row[4])
                mode=row[5] if len(row)>5 else ""
                rows.append((phase, ts, fid, off, sz, mode))
            except: 
                continue
    return rows

def parse_tag(path_or_tag):
    base=os.path.basename(path_or_tag)
    m=TAG_RE.search(base)
    return m.groupdict() if m else {}

def build_send_map(rows):
    mp={}
    for (ph, ts, fid, off, sz, md) in rows:
        if ph!="send": continue
        mp[(fid,off)] = (ts, sz)
    return mp

def build_recv_agg(rows):
    agg={}
    for (ph, ts, fid, off, sz, md) in rows:
        if ph!="recv": continue
        key=(fid, off)
        last, total = agg.get(key, (0,0))
        total += sz
        if ts > last: last = ts
        agg[key] = (last, total)
    return agg

def datagram_metrics(send_rows, recv_rows):
    S=build_send_map(send_rows)
    R=build_recv_agg(recv_rows)
    lat_ms=[]
    matched_bytes=0
    total_bytes=sum(sz for (_,sz) in S.values())
    t0=min((ts for (ts,_) in S.values()), default=None)
    t1=None
    recv_bytes=0
    for key,(ts_s, sz_s) in S.items():
        if key in R:
            ts_r, sz_r = R[key]
            if sz_r >= sz_s:
                lat_ms.append((ts_r - ts_s) / 1e6)
                if (t1 is None) or (ts_r>t1): t1=ts_r
                recv_bytes += sz_s
                matched_bytes += sz_s
    gp=0.0; dur_s=0.0
    if t0 is not None and t1 is not None and t1>t0:
        dur_s = (t1 - t0)/1e9
        gp = (recv_bytes*8/1e6)/dur_s
    loss_rate = (1.0 - matched_bytes/total_bytes) if total_bytes>0 else None
    def pct(v, p):
        if not v: return None
        xs=sorted(v); idx=int(round((p/100.0)*(len(xs)-1)))
        idx=max(0, min(len(xs)-1, idx)); return xs[idx]
    return {
        "dur_s": dur_s, "goodput_mbps": gp, "lat_list_ms": lat_ms,
        "p50":pct(lat_ms,50),"p90":pct(lat_ms,90),"p95":pct(lat_ms,95),"p99":pct(lat_ms,99),
        "loss_rate": loss_rate
    }

def stream_metrics(send_rows, recv_rows):
    sends=[(ts,sz) for (ph,ts,_,_,sz,md) in send_rows if ph=="send"]
    recvs=[(ts,sz) for (ph,ts,_,_,sz,md) in recv_rows if ph=="recv"]
    if not sends or not recvs:
        return {"dur_s":0.0,"goodput_mbps":0.0}
    t0=min(ts for (ts,_) in sends)
    t1=max(ts for (ts,_) in recvs)
    dur_s=max(0.0,(t1-t0)/1e9)
    recv_bytes=sum(sz for (_,sz) in recvs)
    gp=(recv_bytes*8/1e6)/dur_s if dur_s>0 else 0.0
    return {"dur_s":dur_s,"goodput_mbps":gp}

def plot_completion_bar(by_loss_comp, out_png):
    if not by_loss_comp: return
    losses=sorted(by_loss_comp.keys())
    d=[by_loss_comp[L].get("datagram",0.0) for L in losses]
    s=[by_loss_comp[L].get("stream",0.0) for L in losses]
    import numpy as np
    x=np.arange(len(losses)); w=0.35
    plt.figure()
    plt.bar(x - w/2, d, width=w, label="Datagram")
    plt.bar(x + w/2, s, width=w, label="Stream")
    plt.xticks(x, [f"{L*100:.1f}%" for L in losses])
    plt.xlabel("Configured loss")
    plt.ylabel("Completion time (s)")
    plt.title("Completion time by loss")
    plt.legend(); plt.grid(True, axis="y", ls="--", alpha=0.4)
    plt.tight_layout(); plt.savefig(out_png, dpi=170); plt.close()

def plot_goodput_bar(by_loss_gp, out_png):
    if not by_loss_gp: return
    losses=sorted(by_loss_gp.keys())
    d=[by_loss_gp[L].get("datagram",0.0) for L in losses]
    s=[by_loss_gp[L].get("stream",0.0) for L in losses]
    import numpy as np
    x=np.arange(len(losses)); w=0.35
    plt.figure()
    plt.bar(x - w/2, d, width=w, label="Datagram")
    plt.bar(x + w/2, s, width=w, label="Stream")
    plt.xticks(x, [f"{L*100:.1f}%" for L in losses])
    plt.xlabel("Configured loss")
    plt.ylabel("Goodput (Mbps)")
    plt.title("Goodput by loss")
    plt.legend(); plt.grid(True, axis="y", ls="--", alpha=0.4)
    plt.tight_layout(); plt.savefig(out_png, dpi=170); plt.close()

def plot_dgram_latency_box(lat_by_loss, out_png):
    if not lat_by_loss: return
    losses=sorted(lat_by_loss.keys())
    data=[lat_by_loss[L] for L in losses]
    pos=list(range(len(losses)))
    plt.figure()
    plt.boxplot(data, positions=pos, widths=0.5)
    plt.xticks(pos, [f"{L*100:.1f}%" for L in losses])
    plt.xlabel("Configured loss")
    plt.ylabel("Datagram latency (ms)")
    plt.title("Datagram per-message latency")
    plt.grid(True, ls="--", alpha=0.4)
    plt.tight_layout(); plt.savefig(out_png, dpi=170); plt.close()

def plot_dgram_loss_curve(lossrate_by_loss, out_png):
    if not lossrate_by_loss: return
    losses=sorted(lossrate_by_loss.keys())
    ys=[lossrate_by_loss[L] for L in losses]
    plt.figure()
    plt.plot([L*100 for L in losses], [y*100 for y in ys], marker="o")
    plt.xlabel("Configured loss (%)")
    plt.ylabel("File loss rate (%)")
    plt.title("Datagram file loss vs loss setting")
    plt.grid(True, ls="--", alpha=0.4)
    plt.tight_layout(); plt.savefig(out_png, dpi=170); plt.close()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="results/raw_csv/<RUN_TAG>")
    ap.add_argument("--out-root", default="results/analysis", help="output root dir")
    args=ap.parse_args()
    run_tag=os.path.basename(os.path.normpath(args.run_dir))
    out_dir=os.path.join(args.out_root, run_tag)
    fig_dir=os.path.join(out_dir,"figures"); sum_dir=os.path.join(out_dir,"summary"); rep_dir=os.path.join(out_dir,"reports")
    os.makedirs(fig_dir,exist_ok=True); os.makedirs(sum_dir,exist_ok=True); os.makedirs(rep_dir,exist_ok=True)
    completion_by_loss=defaultdict(lambda:{"datagram":None,"stream":None})
    goodput_by_loss=defaultdict(lambda:{"datagram":0.0,"stream":0.0})
    dgram_lat_by_loss=defaultdict(list); dgram_lossrate_by_loss={}
    summary=[["mode","loss","duration_s","goodput_mbps","p50_ms","p90_ms","p95_ms","p99_ms","file_loss_rate"]]
    client_files=sorted(glob.glob(os.path.join(args.run_dir,"client_send_*.csv")))
    for cpath in client_files:
        tag=os.path.splitext(os.path.basename(cpath))[0].replace("client_send_","")
        meta=parse_tag(tag)
        if not meta: continue
        mode=meta["mode"].lower()
        try: loss=float(meta["loss"])
        except: continue
        spath=os.path.join(args.run_dir,f"server_recv_{tag}.csv")
        if not os.path.exists(spath): continue
        S=load_csv(cpath); R=load_csv(spath)
        if mode=="datagram":
            m=datagram_metrics(S,R)
            completion_by_loss[loss]["datagram"]=m["dur_s"]
            goodput_by_loss[loss]["datagram"]=m["goodput_mbps"]
            dgram_lat_by_loss[loss].extend(m["lat_list_ms"])
            if m["loss_rate"] is not None: dgram_lossrate_by_loss[loss]=m["loss_rate"]
            summary.append(["datagram",loss,m["dur_s"],m["goodput_mbps"],m["p50"],m["p90"],m["p95"],m["p99"],m["loss_rate"]])
        elif mode=="stream":
            m=stream_metrics(S,R)
            completion_by_loss[loss]["stream"]=m["dur_s"]
            goodput_by_loss[loss]["stream"]=m["goodput_mbps"]
            summary.append(["stream",loss,m["dur_s"],m["goodput_mbps"],"","","","",""])
    with open(os.path.join(sum_dir,"summary.csv"),"w",newline="") as f:
        csv.writer(f).writerows(summary)
    plot_completion_bar(completion_by_loss,os.path.join(fig_dir,"completion_time_bar.png"))
    plot_goodput_bar(goodput_by_loss,os.path.join(fig_dir,"goodput_bar.png"))
    plot_dgram_latency_box(dgram_lat_by_loss,os.path.join(fig_dir,"dgram_latency_boxplot.png"))
    plot_dgram_loss_curve(dgram_lossrate_by_loss,os.path.join(fig_dir,"dgram_loss_curve.png"))
    report=os.path.join(rep_dir,"report.md")
    with open(report,"w") as f:
        f.write("# Loss Analysis Report\n\n")
        f.write(f"- Run dir: `{args.run_dir}`\n\n")
        f.write("## Figures\n\n")
        for name in ["completion_time_bar.png","goodput_bar.png","dgram_latency_boxplot.png","dgram_loss_curve.png"]:
            p=os.path.join(fig_dir,name)
            if os.path.exists(p): f.write(f"![{name}]({os.path.relpath(p,rep_dir)})\n\n")

if __name__=="__main__": 
    main()
# 
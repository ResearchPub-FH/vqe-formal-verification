#!/usr/bin/env python3
"""Draw a conceptual, publication-scale VQE verification overview.

Run with Python 3 and matplotlib. All artwork is native vector geometry.
This figure contains symbolic examples, not experimental measurements.
"""
from pathlib import Path
import argparse
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Arc
from matplotlib.path import Path as MplPath

REV = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT = 7.16, 4.55
INK = "#253542"
FLOW = "#466174"
MUTED = "#526472"
EDGE = "#BDCAD3"
LOGICAL = "#285EAD"
NUMERIC = "#B85C16"
PROB = "#8351AD"
RUNTIME = "#087E77"
COLORS = [LOGICAL, NUMERIC, PROB, RUNTIME]


def make_figure(output_dir):
    plt.rcParams.update({
        "font.family": "STIXGeneral", "font.size": 8.6,
        "mathtext.fontset": "stix", "pdf.fonttype": 42,
        "svg.fonttype": "none", "axes.unicode_minus": False,
        "savefig.facecolor": "white", "figure.facecolor": "white",
    })
    fig = plt.figure(figsize=(WIDTH, HEIGHT))
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, WIDTH), ylim=(0, HEIGHT))
    ax.set_axis_off()
    labels = []

    def label(x, y, value, size=8.6, color=INK, bold=False, ha="left", **kw):
        artist = ax.text(x, y, value, fontsize=size, color=color,
                         weight="bold" if bold else "normal", ha=ha,
                         va="center", zorder=8, **kw)
        labels.append(artist)
        return artist

    def box(x, y, w, h, fill="white", edge=EDGE, radius=.065,
            lw=.75, dashed=False, zorder=3):
        artist = FancyBboxPatch((x,y),w,h,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            facecolor=fill, edgecolor=edge, linewidth=lw,
            linestyle=(0,(3,2)) if dashed else "solid", zorder=zorder)
        ax.add_patch(artist)
        return artist

    def line(points, color=FLOW, lw=1, dashed=False, zorder=4):
        xs,ys=zip(*points)
        ax.plot(xs,ys,color=color,lw=lw,solid_capstyle="round",
                linestyle=(0,(2.6,2.3)) if dashed else "solid",zorder=zorder)

    def dot(x,y,color):
        ax.add_patch(Circle((x,y),.022,facecolor=color,edgecolor="white",lw=.4,zorder=6))

    def arrow(vertices,codes):
        ax.add_patch(FancyArrowPatch(path=MplPath(vertices,codes),
                     arrowstyle="-|>",mutation_scale=10.5,lw=1.45,
                     color=FLOW,zorder=4))

    def callout(x,y,w,h,name,initial,color,fill,items):
        box(x,y,w,h,fill,color,lw=.8,radius=.07)
        box(x+.12,y+h-.34,.23,.23,fill="white",edge=color,radius=.045,lw=.75)
        label(x+.235,y+h-.225,initial,8.5,color,True,ha="center")
        label(x+.44,y+h-.225,name,10.5,color,True)
        for offset,item in enumerate(items):
            label(x+.14,y+h-.53-.22*offset,item,8.6)

    # Verification concerns frame the workflow, with distinct leader links.
    callout(.12,3.10,1.56,1.20,"Logical","L",LOGICAL,"#F2F6FD",
            ["Ordering", "Readiness", "State consistency"])
    callout(5.48,3.10,1.56,1.20,"Numeric","N",NUMERIC,"#FDF5EE",
            ["Arithmetic validity", "Coefficient alignment", "Shot accounting"])
    callout(.12,1.04,1.56,1.23,"Probabilistic","P",PROB,"#F7F2FB",
            ["Bounded success", "Convergence", "Resource prediction"])
    callout(5.48,1.04,1.56,1.23,"Runtime","R",RUNTIME,"#EFF8F6",
            ["Trace conformance", "Observed evidence", "Cross-stage comparison"])

    # Main nodes preserve the clockwise geometry of the structural reference.
    box(1.94,2.14,1.26,.94,fill="#F8FAFC")
    label(2.57,2.96,"Quantum execution",9.5,bold=True,ha="center")
    # Generic parameterized two-wire circuit, followed by measurement meters.
    for yy in [2.68,2.47]:
        label(2.055,yy,r"$|0\rangle$",7.8,ha="center")
        line([(2.14,yy),(3.065,yy)],FLOW,.8)
    box(2.29,2.38,.43,.39,fill="#E8EFF8",edge=LOGICAL,radius=.025,lw=.8,zorder=5)
    label(2.505,2.575,r"$U(\boldsymbol{\theta}_k)$",9.3,LOGICAL,ha="center")
    for yy in [2.68,2.47]:
        box(2.88,yy-.077,.16,.154,fill="white",edge=FLOW,radius=.015,lw=.65,zorder=5)
        ax.add_patch(Arc((2.96,yy-.024),.105,.105,theta1=15,theta2=165,
                         color=FLOW,lw=.7,zorder=6))
        line([(2.96,yy-.024),(2.993,yy+.033)],FLOW,.8,zorder=7)
    label(2.57,2.255,r"Measure $N$ shots",8.6,MUTED,ha="center")

    box(3.00,3.23,1.16,1.07,fill="#F8FAFC")
    label(3.58,4.18,"Program output",9.5,bold=True,ha="center")
    # Symbolic records avoid implying that these are measured result values.
    box(3.22,3.45,.72,.60,edge=EDGE,radius=.018,lw=.65)
    line([(3.58,3.45),(3.58,4.05)],EDGE,.55)
    for yy in [3.60,3.75,3.90]:
        line([(3.22,yy),(3.94,yy)],EDGE,.55)
    for row,bits in enumerate(["00","01","10","11"]):
        yy=3.975-.15*row
        label(3.40,yy,bits,8.5,ha="center")
        label(3.76,yy,rf"$n_{{{bits}}}$",8.5,ha="center")
    label(3.58,3.35,"Measurement records",8.1,MUTED,ha="center")

    box(3.96,2.14,1.26,.94,fill="#F8FAFC")
    label(4.59,2.96,"Classical processing",9.2,bold=True,ha="center")
    label(4.59,2.615,r"$\widehat E=\sum_i c_i\widehat e_i$",12,NUMERIC,ha="center")
    label(4.59,2.255,"Optimizer decision",8.6,MUTED,ha="center")

    box(2.93,1.15,1.30,.64,fill="#F8FAFC")
    label(3.58,1.645,"Updated parameters",9.2,bold=True,ha="center")
    label(3.58,1.355,r"$\boldsymbol{\theta}_{k+1}$",15,LOGICAL,ha="center")

    M,L,Q=MplPath.MOVETO,MplPath.LINETO,MplPath.CURVE3
    arrow([(2.57,3.08),(2.57,3.62),(2.57,3.80),(2.75,3.80),(3.00,3.80)], [M,L,Q,Q,L])
    arrow([(4.16,3.80),(4.41,3.80),(4.59,3.80),(4.59,3.62),(4.59,3.08)], [M,L,Q,Q,L])
    arrow([(4.59,2.14),(4.59,1.65),(4.59,1.47),(4.41,1.47),(4.23,1.47)], [M,L,Q,Q,L])
    arrow([(2.93,1.47),(2.75,1.47),(2.57,1.47),(2.57,1.65),(2.57,2.14)], [M,L,Q,Q,L])
    label(3.58,2.79,"Hybrid",9.6,MUTED,ha="center")
    label(3.58,2.585,"VQE",13,INK,True,ha="center")
    label(3.58,2.38,"feedback loop",8.6,MUTED,ha="center")
    label(3.58,1.975,"Finite-shot uncertainty",8.3,PROB,ha="center",style="italic")

    # Leaders connect motivations to relevant parts of the hybrid loop.
    line([(1.68,3.58),(2.14,3.58),(2.14,3.46),(2.57,3.46)],LOGICAL,.85,True)
    dot(2.57,3.46,LOGICAL)
    line([(5.48,3.58),(5.03,3.58),(5.03,3.08)],NUMERIC,.85,True)
    dot(5.03,3.08,NUMERIC)
    line([(1.68,1.73),(2.57,1.73)],PROB,.85,True)
    dot(2.57,1.73,PROB)

    # Dashed observation taps are visually distinct from VQE control/data flow.
    for x in [2.075,5.085]:
        end=2.38 if x<3.58 else 4.78
        line([(x,2.14),(x,.82),(end,.82)],RUNTIME,.8,True,zorder=2)
        dot(x,2.14,RUNTIME)
    line([(3.58,1.15),(3.58,1.03)],RUNTIME,.8,True,zorder=2)
    dot(3.58,1.15,RUNTIME)
    box(2.38,.61,2.40,.42,fill="#EFF8F6",edge=RUNTIME,radius=.055,lw=.8,dashed=True)
    label(3.58,.82,r"Observed trace: $e_1\;\rightarrow\;e_2\;\rightarrow\;\cdots$",9,RUNTIME,ha="center")
    line([(5.48,1.42),(5.32,1.42),(5.32,.82),(4.78,.82)],RUNTIME,.85,True)
    dot(4.78,.82,RUNTIME)

    # Positive synthesis: the four dimensions jointly motivate the architecture.
    for i,color in enumerate(COLORS):
        x=.40+i*1.59
        line([(x,.44),(x+1.46,.44)],color,1.55)
    label(3.58,.225,"Four complementary verification layers across one hybrid workflow",
          10.5,INK,True,ha="center")

    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    canvas=fig.bbox
    outside=[]
    overlaps=[]
    for i,item in enumerate(labels):
        bb=item.get_window_extent(renderer)
        if not (bb.x0>=canvas.x0 and bb.x1<=canvas.x1 and bb.y0>=canvas.y0 and bb.y1<=canvas.y1):
            outside.append(item.get_text())
        for other in labels[i+1:]:
            if bb.overlaps(other.get_window_extent(renderer)):
                overlaps.append([item.get_text(),other.get_text()])
    assert not outside, outside
    assert not overlaps, overlaps
    output_dir.mkdir(parents=True,exist_ok=True)
    for suffix in ["pdf","png","svg"]:
        fig.savefig(output_dir/f"introduction-overview.{suffix}",dpi=400,
                    metadata={"Title":"Hybrid VQE and complementary verification concerns"} if suffix=="pdf" else None)
    plt.close(fig)
    return {"size_inches":[WIDTH,HEIGHT],"intended_placement":"double-column Introduction figure",
            "font_family":"STIXGeneral; STIX mathematics","png_dpi":400,
            "text_labels":len(labels),"text_overlap_count":len(overlaps),
            "out_of_canvas_labels":outside,"quantitative_results":"None; conceptual schematic"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=REV/"figures")
    args=parser.parse_args()
    print(json.dumps(make_figure(args.output_dir),indent=2))

#!/usr/bin/env python3
"""Online enforcement and offline replay: shared semantics, distinct paths.

Conceptual figure only. Event symbols and verification paths are schematic, not
measured results. Run with Python 3 and Matplotlib to export PDF, PNG, and SVG.
"""
from pathlib import Path
import argparse
import hashlib
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon

REV = Path(__file__).resolve().parents[2]
STEM = "runtime_verification_online_offline"
WIDTH, HEIGHT = 7.16, 3.80
# Shared-path foregrounds use black consistently; lane colors retain their roles.
INK = "#000000"
NEUTRAL = INK
GREEN = "#087E56"
BLUE = "#2369A5"
GREEN_FILL = "#F0F8F4"
BLUE_FILL = "#F0F5FB"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draw(output_dir):
    plt.rcParams.update({
        "font.family": "STIXGeneral", "mathtext.fontset": "stix",
        "font.size": 9, "pdf.fonttype": 42, "svg.fonttype": "none",
        "savefig.facecolor": "white", "figure.facecolor": "white",
    })
    fig = plt.figure(figsize=(WIDTH, HEIGHT))
    ax = fig.add_axes([0,0,1,1], xlim=(0,WIDTH), ylim=(.80,4.60))
    ax.set_axis_off()
    labels=[]

    def text(x,y,value,size=9,color=INK,bold=False,ha="left",**kwargs):
        obj=ax.text(x,y,value,fontsize=size,color=color,
                    weight="bold" if bold else "normal",ha=ha,va="center",
                    linespacing=1.30,zorder=8,**kwargs)
        labels.append(obj)
        return obj

    def box(x,y,w,h,fill="white",edge=NEUTRAL,radius=.07,lw=.8,zorder=3):
        p=FancyBboxPatch((x,y),w,h,
              boxstyle=f"round,pad=0,rounding_size={radius}",
              facecolor=fill,edgecolor=edge,lw=lw,zorder=zorder)
        ax.add_patch(p)
        return p

    def line(points,color=NEUTRAL,lw=.9,style="solid",zorder=4):
        xs,ys=zip(*points)
        ax.plot(xs,ys,color=color,lw=lw,linestyle=style,
                solid_capstyle="round",zorder=zorder)

    def arrow(points,color=NEUTRAL,lw=1.0,style="solid",zorder=4):
        if len(points)>2:
            line(points[:-1],color,lw,style,zorder)
        ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                     arrowstyle="-|>",mutation_scale=8.5,lw=lw,
                     linestyle=style,color=color,zorder=zorder,
                     shrinkA=0,shrinkB=0))

    def document(x,y):
        # Two vector sheets, with an explicit folded corner.
        box(x-.035,y+.035,.22,.27,edge=NEUTRAL,radius=.012,lw=.65,zorder=5)
        p=Polygon([(x,y),(x+.22,y),(x+.22,y+.20),(x+.15,y+.27),(x,y+.27)],
                  closed=True,facecolor="white",edgecolor=NEUTRAL,lw=.75,zorder=6)
        ax.add_patch(p)
        line([(x+.15,y+.27),(x+.15,y+.20),(x+.22,y+.20)],NEUTRAL,.65,zorder=7)
        for yy in [y+.065,y+.12]:
            line([(x+.045,yy),(x+.175,yy)],NEUTRAL,.6,zorder=7)

    preserved=[REV/"manuscript_review3.tex",REV/"manuscript_review3.pdf",
               REV/"figures/introduction-overview.pdf",REV/"figures/architecture.pdf"]
    before={str(p.relative_to(REV)):sha(p) for p in preserved if p.is_file()}

    # Center the compact shared panel on the two verification-path containers.
    lane_left, lane_width = .18, 5.63
    lane_center = lane_left + lane_width / 2
    shared_width = 3.90
    shared_left = lane_center - shared_width / 2
    box(shared_left,4.02,shared_width,.48,fill="#F6F7F9",edge=NEUTRAL,lw=.85)
    shared_heading_size = 13
    text(lane_center,4.26,"Shared specifications and event semantics",shared_heading_size,INK,True,ha="center")
    line([(shared_left,4.26),(.07,4.26),(.07,1.34)],NEUTRAL,.85)
    arrow([(.07,3.38),(.18,3.38)],NEUTRAL,.85)
    arrow([(.07,1.34),(.18,1.34)],NEUTRAL,.85)

    # Shared event labels and aligned positions convey event correspondence.
    event_x=[1.68,2.33,2.98,3.63,4.28]
    event_symbols=[r"$a_1$",r"$a_2$",r"$a_3$",r"$\cdots$",r"$a_m$"]

    lanes=[
        {"bottom":2.99,"row":3.30,"color":GREEN,"fill":GREEN_FILL,
         "mode":"ONLINE","action":"Enforcement",
         "sequence":"Live event stream","verdict":"Online verdict"},
        {"bottom":.95,"row":1.26,"color":BLUE,"fill":BLUE_FILL,
         "mode":"OFFLINE","action":"Replay",
         "sequence":"Recorded event sequence","verdict":"Replay verdict"},
    ]
    for lane in lanes:
        b,y,c=lane["bottom"],lane["row"],lane["color"]
        box(lane_left,b,lane_width,.78,fill=lane["fill"],edge=c,lw=.8)
        line([(1.34,b+.12),(1.34,b+.66)],c,.55,zorder=5)
        # Center the two-line label after removing timing subtitles in both modes.
        text(.78,b+.50,lane["mode"],10.7,c,True,ha="center")
        text(.78,b+.27,lane["action"],9.1,c,True,ha="center")
        text(2.98,b+.64,lane["sequence"],9.5,c,True,ha="center")
        for j,(x,label) in enumerate(zip(event_x,event_symbols)):
            if j!=3:
                box(x-.17,y-.14,.34,.28,edge=c,radius=.045,lw=.8,zorder=5)
            text(x,y,label,11.0,c,ha="center")
            if j<len(event_x)-1:
                arrow([(x+.18,y),(event_x[j+1]-.18,y)],c,1.05,zorder=6)
        arrow([(event_x[-1]+.18,y),(4.74,y)],c,1.05,zorder=6)
        # Both verdict boxes contain only a centered descriptive label.
        box(4.74,y-.18,.95,.36,edge=c,radius=.055,lw=.9,zorder=5)
        text(5.215,y,lane["verdict"],8.7,c,True,ha="center")

    # The control return belongs to the online mode and targets the mode's
    # execution boundary, not an earlier event in the observed trace.
    arrow([(5.215,3.48),(5.215,3.90),(.78,3.90),(.78,3.77)],GREEN,1.05)
    text(3.12,3.90,"Continue / block the next instrumented operation",8.8,GREEN,True,ha="center",
         bbox={"facecolor":"white","edgecolor":"none","pad":2})

    # Recording preserves the observed execution; replay consumes that record.
    box(2.08,2.13,2.04,.48,fill="#F7F8FA",edge=NEUTRAL,lw=.8,zorder=5)
    document(2.23,2.215)
    text(3.30,2.47,"Saved execution trace",9.5,INK,True,ha="center")
    text(3.30,2.27,r"$\tau=\langle a_1,a_2,\ldots,a_m\rangle$",9.5,NEUTRAL,ha="center")
    arrow([(3.10,2.99),(3.10,2.61)],NEUTRAL,1.0,zorder=6)
    text(3.25,2.80,"Record",8.8,NEUTRAL,True)
    arrow([(3.10,2.13),(3.10,1.73)],NEUTRAL,1.0,zorder=6)
    text(3.25,1.93,"Replay",8.8,NEUTRAL,True)

    # A comparison, not an assertion that the verdicts are automatically equal.
    box(5.95,2.08,1.10,.58,fill="#F6F7F9",edge=NEUTRAL,lw=.9)
    text(6.50,2.37,"Check verdict\nconsistency",10.2,INK,True,ha="center")
    arrow([(5.69,3.30),(6.50,3.30),(6.50,2.66)],GREEN,1.05)
    arrow([(5.69,1.26),(6.50,1.26),(6.50,2.08)],BLUE,1.05)

    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    outside=[]
    overlaps=[]
    for i,label in enumerate(labels):
        bb=label.get_window_extent(renderer)
        if not (bb.x0>=fig.bbox.x0 and bb.x1<=fig.bbox.x1 and bb.y0>=fig.bbox.y0 and bb.y1<=fig.bbox.y1):
            outside.append(label.get_text())
        for other in labels[i+1:]:
            if bb.overlaps(other.get_window_extent(renderer)):
                overlaps.append([label.get_text(),other.get_text()])
    assert not outside, outside
    assert not overlaps, overlaps
    output_dir.mkdir(parents=True,exist_ok=True)
    for ext in ["pdf","png","svg"]:
        fig.savefig(output_dir/f"{STEM}.{ext}",dpi=400,
                    metadata={"Title":"Shared semantics for online enforcement and offline replay"} if ext=="pdf" else None)
    plt.close(fig)
    unchanged={name:sha(REV/name)==digest for name,digest in before.items()}
    assert all(unchanged.values()),unchanged
    return {"figure":STEM,"size_inches":[WIDTH,HEIGHT],"placement":"double-column",
            "fonts":"STIX serif text and mathematics","png_dpi":400,
            "shared_panel_center_x":lane_center,"lane_center_x":lane_center,
            "shared_panel_width_inches":shared_width,
            "shared_heading_size_pt":shared_heading_size,
            "verdict_symbols_present":False,
            "verdict_labels_centered":True,
            "feedback_operation_term":"instrumented",
            "mode_action_labels_bold":True,"timing_labels_present":False,
            "transition_labels_bold":True,"neutral_foreground_color":NEUTRAL,
            "correspondence_guides":0,
            "text_overlap_count":len(overlaps),"outside_canvas":outside,
            "preserved_sha256":before,"unchanged":unchanged,
            "scientific_content":"Conceptual paths and symbolic events; no measured results"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=REV/"figures")
    args=parser.parse_args()
    result=draw(args.output_dir)
    report=REV/"data/runtime_paths_layout.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
